"""Create a PostgreSQL custom-format backup through Docker Compose."""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="backups")
    parser.add_argument("--compose-file", default="docker-compose.staging.yml")
    args = parser.parse_args()
    database = os.environ.get("POSTGRES_DB", "").strip()
    user = os.environ.get("POSTGRES_USER", "").strip()
    if not database or not user:
        raise SystemExit("POSTGRES_DB and POSTGRES_USER are required")
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = output_dir / f"pilotage-{timestamp}.dump"
    command = ["docker", "compose", "-f", args.compose_file, "exec", "-T", "postgres", "pg_dump", "-U", user, "-d", database, "-Fc"]
    with destination.open("wb") as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        destination.unlink(missing_ok=True)
        raise SystemExit(f"Backup failed with exit code {result.returncode}: {result.stderr.decode(errors='replace')}")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
