"""Read-only Sprint 6 smoke test against a deployed Pilotage API."""

from __future__ import annotations

import argparse
import os

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--anchor", required=True, help="Business date in YYYY-MM-DD")
    args = parser.parse_args()
    token = os.getenv("PILOTAGE_RECIPE_TOKEN", "").strip()
    if not token:
        raise SystemExit("PILOTAGE_RECIPE_TOKEN is required")
    headers = {"Authorization": f"Bearer {token}"}
    checks = [
        ("objectives", "/api/pilotage/objectives", "application/json"),
        ("alerts", "/api/pilotage/alerts", "application/json"),
        ("daily report", f"/api/pilotage/reports/day?anchor={args.anchor}", "application/json"),
        ("weekly CSV", f"/api/pilotage/reports/week?anchor={args.anchor}&format=csv", "text/csv"),
        ("monthly PDF", f"/api/pilotage/reports/month?anchor={args.anchor}&format=pdf", "application/pdf"),
    ]
    failures = 0
    with httpx.Client(base_url=args.base_url.rstrip("/"), headers=headers, timeout=20.0, follow_redirects=False) as client:
        health = client.get("/health")
        print(f"health: {health.status_code}")
        failures += health.status_code != 200
        for label, path, media_type in checks:
            response = client.get(path)
            content_type = response.headers.get("content-type", "")
            passed = response.status_code == 200 and media_type in content_type
            if media_type == "application/pdf":
                passed = passed and response.content.startswith(b"%PDF-")
            print(f"{label}: {response.status_code} {'OK' if passed else 'FAILED'}")
            failures += not passed
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
