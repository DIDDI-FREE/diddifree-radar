"""Restore a Pilotage backup after explicit database-name confirmation."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup")
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--compose-file", default="docker-compose.staging.yml")
    args = parser.parse_args()
    database = os.environ.get("POSTGRES_DB", "").strip()
    user = os.environ.get("POSTGRES_USER", "").strip()
    if not database or not user:
        raise SystemExit("POSTGRES_DB and POSTGRES_USER are required")
    if args.confirm_database != database:
        raise SystemExit("--confirm-database must exactly match POSTGRES_DB")
    backup = Path(args.backup).resolve()
    if not backup.is_file():
        raise SystemExit("Backup file does not exist")
    command = ["docker", "compose", "-f", args.compose_file, "exec", "-T", "postgres", "pg_restore", "-U", user, "-d", database, "--clean", "--if-exists", "--no-owner"]
    with backup.open("rb") as stream:
        result = subprocess.run(command, stdin=stream, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
