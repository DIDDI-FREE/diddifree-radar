"""Check Pilotage service-token configuration without printing secrets or tokens."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.service_auth import service_client_id, service_token_url
from app.sources.catalog import enabled_modules, get_source


def main() -> int:
    failures = 0
    for module in enabled_modules():
        source = get_source(module)
        client_id = service_client_id(module)
        secret = os.getenv(f"PILOTAGE_{module.upper()}_SERVICE_CLIENT_SECRET", "").strip() or os.getenv("PILOTAGE_SERVICE_CLIENT_SECRET", "").strip()
        token_url = service_token_url(module)
        print(f"{module}: client_id={client_id or 'MISSING'} secret={'configured' if secret else 'MISSING'} token_host={urlsplit(token_url).netloc or 'MISSING'}")
        if not client_id or not secret or not token_url:
            failures += 1
            continue
        data = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret, "audience": source.audience(), "scope": source.scope()}
        try:
            response = httpx.post(token_url, data=data, headers={"X-Client-ID": client_id}, timeout=10.0)
            print(f"{module}: token_status={response.status_code}")
            failures += response.status_code != 200
        except httpx.HTTPError as error:
            print(f"{module}: token_status=UNAVAILABLE error_type={type(error).__name__}")
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
