"""DiddiFreeID OTP login proxy for the Pilotage dashboard.

The browser never talks to DiddiFreeID directly and never sees service
credentials. After a successful OTP verification the browser holds the
human identity JWT, which every Pilotage API route re-validates via JWKS.
"""

from __future__ import annotations

import base64
import json
import os

import httpx
from fastapi import APIRouter, HTTPException
from jose.exceptions import JWTError

from app.core.auth import _local_principal

router = APIRouter(prefix="/pilotage/auth", tags=["pilotage-auth"])

OTP_CHANNELS = {"email", "telegram", "whatsapp"}


def _identity_url(path: str) -> str:
    base_url = os.getenv("DIDDIFREEID_SERVICE_URL", "https://auth-staging.diddifree.com/identity/v1").rstrip("/")
    return f"{base_url}{path}"


async def _post_identity(path: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        response = await client.post(_identity_url(path), json=body)
        response.raise_for_status()
        return response.json()


def _jwt_claims_unverified(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return claims if isinstance(claims, dict) else {}
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _error_detail(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


@router.get("/config")
async def auth_config() -> dict:
    return {
        "provider": "diddifreeid",
        "mode": "diddifreeid_otp",
        "environment": os.getenv("PILOTAGE_ENV", "local").strip().lower(),
        "otp_channels": sorted(OTP_CHANNELS),
    }


@router.post("/otp/request")
async def request_otp(payload: dict) -> dict:
    channel = str(payload.get("channel", "email")).strip().lower()
    email = str(payload.get("email", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    if channel not in OTP_CHANNELS:
        raise HTTPException(status_code=400, detail=_error_detail("invalid_channel", "OTP channel must be email, telegram or whatsapp"))
    if channel == "email" and not email:
        raise HTTPException(status_code=400, detail=_error_detail("email_required", "Email channel requires an email address"))
    if channel in {"telegram", "whatsapp"} and not phone:
        raise HTTPException(status_code=400, detail=_error_detail("phone_required", "This channel requires a phone number"))
    body = {key: value for key, value in {"email": email or None, "phone": phone or None, "channel": channel}.items() if value}
    try:
        return await _post_identity("/auth/otp/request", body)
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=error.response.status_code, detail=_error_detail("otp_request_rejected", "DiddiFreeID rejected the OTP request")) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=_error_detail("identity_unavailable", "DiddiFreeID OTP request failed")) from error


@router.post("/otp/verify")
async def verify_otp(payload: dict) -> dict:
    code = str(payload.get("code", "")).strip()
    email = str(payload.get("email", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    if (not email and not phone) or not code:
        raise HTTPException(status_code=400, detail=_error_detail("invalid_request", "Email/phone and code are required"))
    body = {
        key: value
        for key, value in {"email": email or None, "phone": phone or None, "code": code, "device_info": "diddifree-pilotage"}.items()
        if value
    }
    try:
        result = await _post_identity("/auth/otp/verify", body)
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=error.response.status_code, detail=_error_detail("otp_rejected", "DiddiFreeID rejected the OTP verification")) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=_error_detail("identity_unavailable", "DiddiFreeID OTP verification failed")) from error
    access_token = result.get("access_token", "")
    if not access_token:
        raise HTTPException(status_code=502, detail=_error_detail("identity_unavailable", "DiddiFreeID returned no access token"))
    claims = _jwt_claims_unverified(access_token)
    user_id = claims.get("user_id") or claims.get("sub")
    if not user_id or claims.get("status") != "active":
        raise HTTPException(status_code=403, detail=_error_detail("identity_inactive", "DiddiFreeID identity is not active"))
    try:
        # The OTP code was delivered to this email, so it is proven and may
        # drive first-login bootstrap provisioning.
        principal = _local_principal(str(user_id), email)
    except JWTError:
        raise HTTPException(status_code=403, detail=_error_detail("not_provisioned", "This user is not provisioned in Pilotage")) from None
    return {
        "access_token": access_token,
        "expires_in": result.get("expires_in"),
        "token_type": result.get("token_type", "Bearer"),
        "session": {"user_id": principal.user_id, "role": principal.role, "modules": list(principal.modules)},
    }
