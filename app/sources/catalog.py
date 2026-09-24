"""Single source of truth for the modules Pilotage reads from.

Base URLs reuse the same environment variables as the Backoffice deployment
so one staging env file can feed both applications. The summary base path
and scope are Pilotage-specific and overridable per module because upstream
API prefixes differ (DiddiPay mounts everything under ``/payfund/v1``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PilotageSource:
    key: str
    display_name: str
    base_url_env: str
    default_base_url: str
    default_summary_base: str
    requires_token: bool
    default_scope: str

    def base_url(self) -> str:
        return (os.getenv(self.base_url_env) or self.default_base_url).rstrip("/")

    def summary_base(self) -> str:
        return (os.getenv(f"PILOTAGE_{self.key.upper()}_SUMMARY_BASE") or self.default_summary_base).rstrip("/")

    def scope(self) -> str:
        return os.getenv(f"PILOTAGE_{self.key.upper()}_SCOPE") or self.default_scope


# Default scopes are each module's registered convention in DiddiFreeID
# (identity.service_clients), not a Pilotage invention.
PILOTAGE_SOURCES: dict[str, PilotageSource] = {
    "diddigo": PilotageSource(
        "diddigo", "DiddiGo", "DIDDIGO_SERVICE_URL",
        "https://go-staging.diddifree.com", "/internal/pilotage", True,
        "diddigo:ride-summary:read",
    ),
    "diddisend": PilotageSource(
        "diddisend", "DiddiSend", "DIDDISEND_SERVICE_URL",
        "https://diddisend-api-staging.diddifree.com", "/internal/pilotage", True,
        "diddisend:pilotage:daily-summary:read",
    ),
    "diddipay": PilotageSource(
        "diddipay", "DiddiPay", "DIDDIPAY_SERVICE_URL",
        "https://pay-api-staging.diddifree.com", "/payfund/v1/internal/pilotage", True,
        "diddipay:payment-summary:read",
    ),
    "diddimap": PilotageSource(
        "diddimap", "DiddiMap", "DIDDIMAP_SERVICE_URL",
        "http://abidjanmaps-backend-staging.diddifree.com", "/internal/pilotage", False,
        "diddimap:pilotage-summary:read",
    ),
    "diddifood": PilotageSource(
        "diddifood", "DiddiFood", "DIDDIFOOD_SERVICE_URL",
        "https://diddifood-backend-staging.diddifree.com", "/internal/pilotage", True,
        "food:pilotage:read",
    ),
    "diddifiles": PilotageSource(
        "diddifiles", "DiddiFiles", "DIDDIFILES_SERVICE_URL",
        "https://diddifiles.diddifree.com", "/internal/pilotage", True,
        "diddifiles:pilotage-summary:read",
    ),
}


def get_source(key: str) -> PilotageSource:
    try:
        return PILOTAGE_SOURCES[key]
    except KeyError as error:
        raise ValueError(f"Unknown Pilotage source: {key}") from error


def enabled_modules() -> list[str]:
    configured = os.getenv("PILOTAGE_MODULES", "diddigo,diddisend,diddipay,diddimap")
    modules = [part.strip() for part in configured.split(",") if part.strip()]
    return [module for module in modules if module in PILOTAGE_SOURCES]
