"""Fetch a real authenticated Pilotage daily export without printing credentials."""

from __future__ import annotations

import argparse
import json
import os

import httpx


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing environment variable: {name}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Africa/Abidjan business date (YYYY-MM-DD)")
    args = parser.parse_args()

    base_url = os.getenv("PILOTAGE_PUBLIC_BASE_URL", "https://supervision.diddifree.com").rstrip("/")
    token_url = os.getenv(
        "PILOTAGE_CONSUMER_TOKEN_URL",
        "https://auth-staging.diddifree.com/identity/v1/auth/service/token",
    )
    client_id = required("PILOTAGE_ODOO_CLIENT_ID")
    client_secret = required("PILOTAGE_ODOO_CLIENT_SECRET")

    with httpx.Client(timeout=20.0) as client:
        token_response = client.post(
            token_url,
            headers={"X-Client-ID": client_id},
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "audience": "pilotage",
                "scope": "pilotage:read pilotage:finance:read",
            },
        )
        token_response.raise_for_status()
        token = token_response.json()["access_token"]
        response = client.get(
            f"{base_url}/api/pilotage/accounting/daily-export",
            params={"date": args.date},
            headers={"Authorization": f"Bearer {token}", "X-Client-ID": client_id},
        )
        response.raise_for_status()
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
