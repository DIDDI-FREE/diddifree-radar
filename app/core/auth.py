from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx
from fastapi import HTTPException, Request
from jose import jwk, jwt
from jose.exceptions import JWTError

from app.core.db import row, execute, utc_now_iso

ALLOWED_ROLES = {"dg_global", "finance_admin", "operations_manager", "module_manager", "audit_read"}
FINANCE_ROLES = {"dg_global", "finance_admin"}
COLLECT_ROLES = {"dg_global", "operations_manager"}

_jwks_cache: tuple[float, dict] | None = None


@dataclass(frozen=True)
class PilotagePrincipal:
    user_id: str
    role: str
    modules: tuple[str, ...]

    def can_view(self, module: str) -> bool:
        return "global" in self.modules or module in self.modules


def _parse_modules(value: str) -> tuple[str, ...]:
    parts = tuple(part.strip() for part in value.split(",") if part.strip())
    return parts or ("global",)


def _bootstrap_role_for(email: str) -> str | None:
    if not email:
        return None
    bootstrap = os.getenv("PILOTAGE_BOOTSTRAP_DG_EMAILS", "")
    allowed = {part.strip().lower() for part in bootstrap.split(",") if part.strip()}
    return "dg_global" if email.lower() in allowed else None


def _local_principal(user_id: str, email: str) -> PilotagePrincipal:
    """Identity proves who the person is; the local table decides what they see."""
    local = row("SELECT role, modules, status FROM pilotage_users WHERE id = ?", (user_id,))
    if not local:
        bootstrap_role = _bootstrap_role_for(email)
        if not bootstrap_role:
            raise JWTError("User is not provisioned in Pilotage")
        execute(
            "INSERT INTO pilotage_users (id, email, role, modules, status, created_at) VALUES (?, ?, ?, 'global', 'active', ?)",
            (user_id, email, bootstrap_role, utc_now_iso()),
        )
        return PilotagePrincipal(user_id=user_id, role=bootstrap_role, modules=("global",))
    if local["status"] != "active" or local["role"] not in ALLOWED_ROLES:
        raise JWTError("User is not an active Pilotage user")
    return PilotagePrincipal(user_id=user_id, role=local["role"], modules=_parse_modules(local["modules"]))


def principal_from_oidc(token: str) -> PilotagePrincipal:
    global _jwks_cache
    jwks_url = os.getenv("PILOTAGE_OIDC_JWKS_URL", "https://auth-staging.diddifree.com/identity/v1/.well-known/jwks.json")
    issuer = os.getenv("PILOTAGE_OIDC_ISSUER")
    audience = os.getenv("PILOTAGE_OIDC_AUDIENCE")
    environment = os.getenv("PILOTAGE_ENV", "local").strip().lower()
    strict_token_validation = environment in {"staging", "production"} or os.getenv("PILOTAGE_ALLOW_INSECURE_HEADERS", "0") != "1"
    try:
        if strict_token_validation and not issuer:
            raise JWTError("OIDC issuer is required outside local development")
        header = jwt.get_unverified_header(token)
        if header.get("alg") not in {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}:
            raise JWTError("Unsupported OIDC algorithm")
        if not _jwks_cache or _jwks_cache[0] <= time.time():
            with httpx.Client(timeout=5.0) as client:
                response = client.get(jwks_url)
                response.raise_for_status()
                _jwks_cache = (time.time() + 300, response.json())
        key_data = next(key for key in _jwks_cache[1].get("keys", []) if key.get("kid") == header.get("kid"))
        key = jwk.construct(key_data)
        options = {"verify_aud": bool(audience), "verify_iss": bool(issuer)}
        claims = jwt.decode(token, key, algorithms=[header["alg"]], audience=audience, issuer=issuer, options=options)
        user_id = claims.get("user_id") or claims.get("sub")
        if not user_id or claims.get("status") != "active":
            raise JWTError("OIDC identity is not active")
        return _local_principal(user_id, claims.get("email", ""))
    except (JWTError, KeyError, httpx.HTTPError, ValueError) as error:
        raise ValueError("Invalid OIDC token") from error


def get_principal(request: Request) -> PilotagePrincipal:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        try:
            return principal_from_oidc(authorization.removeprefix("Bearer ").strip())
        except ValueError:
            raise HTTPException(status_code=401, detail={"error": {"code": "invalid_token", "message": "OIDC token was rejected"}})
    if os.getenv("PILOTAGE_ALLOW_INSECURE_HEADERS", "0") == "1":
        user_id = request.headers.get("X-User-Id", "")
        role = request.headers.get("X-Role", "")
        if user_id and role in ALLOWED_ROLES:
            return PilotagePrincipal(
                user_id=user_id,
                role=role,
                modules=_parse_modules(request.headers.get("X-Modules", "global")),
            )
    raise HTTPException(status_code=401, detail={"error": {"code": "unauthenticated", "message": "A DiddiFreeID bearer token is required"}})


def require_role(principal: PilotagePrincipal, allowed: set[str]) -> None:
    if principal.role not in allowed:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "permission_denied", "message": "Role is not allowed for this operation", "details": {"required_roles": sorted(allowed)}}},
        )


def require_module_access(principal: PilotagePrincipal, module: str) -> None:
    if not principal.can_view(module):
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "permission_denied", "message": "Module is outside this user's Pilotage scope", "details": {"module": module}}},
        )
