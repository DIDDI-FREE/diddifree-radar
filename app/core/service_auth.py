from __future__ import annotations

import os
import time

import httpx

_token_cache: dict[str, tuple[str, float]] = {}


def _env(module: str, suffix: str) -> str:
    return os.getenv(f"PILOTAGE_{module.upper()}_{suffix}", "").strip()


def _shared(suffix: str) -> str:
    return os.getenv(f"PILOTAGE_SERVICE_{suffix}", "").strip()


def service_token_url(module: str) -> str:
    configured = _env(module, "SERVICE_TOKEN_URL") or _shared("TOKEN_URL")
    if configured:
        return configured
    identity_base_url = os.getenv("DIDDIFREEID_SERVICE_URL", "").rstrip("/")
    return f"{identity_base_url}/auth/service/token" if identity_base_url else ""


def service_client_id(module: str) -> str:
    return _env(module, "SERVICE_CLIENT_ID") or _shared("CLIENT_ID")


def get_service_token(module: str, *, scope: str | None = None) -> str:
    """Return a short-lived S2S token for one module audience and scope.

    A per-module static token wins during migration; otherwise the shared
    Pilotage client (client_id such as ``pilotage-staging``) exchanges
    client credentials against the module token URL or the central
    DiddiFreeID service-token endpoint.
    """
    static_token = _env(module, "SERVICE_TOKEN")
    if static_token:
        return static_token
    cache_key = f"{module}:{scope or ''}"
    cached = _token_cache.get(cache_key)
    if cached and cached[1] > time.time():
        return cached[0]
    token_url = service_token_url(module)
    client_id = service_client_id(module)
    client_secret = _env(module, "SERVICE_CLIENT_SECRET") or _shared("CLIENT_SECRET")
    if not token_url or not client_id or not client_secret:
        return ""
    data = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
    audience = _env(module, "SERVICE_AUDIENCE") or module
    data["audience"] = audience
    if scope:
        data["scope"] = scope
    with httpx.Client(timeout=10.0) as client:
        response = client.post(token_url, data=data, headers={"X-Client-ID": client_id})
        response.raise_for_status()
        payload = response.json()
    token = payload.get("access_token", "")
    if token:
        _token_cache[cache_key] = (token, time.time() + max(int(payload.get("expires_in", 300)) - 30, 30))
    return token


def service_request_headers(module: str) -> dict[str, str]:
    """Headers required by an upstream's service-to-service trust boundary."""
    headers: dict[str, str] = {}
    client_id = service_client_id(module)
    service_key = _env(module, "SERVICE_KEY") or _shared("KEY")
    if client_id:
        headers["X-Client-ID"] = client_id
    if service_key:
        headers["X-Service-Key"] = service_key
    return headers
