from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

SCHEMA_VERSION = "001_initial"
SUMMARY_REVISION_MIGRATION = "002_summary_revisions"
PLANNING_MIGRATION = "003_planning"
ALERTS_MIGRATION = "004_alerts"

SCHEMA = """
CREATE TABLE IF NOT EXISTS pilotage_users (
  id TEXT PRIMARY KEY,
  full_name TEXT NOT NULL DEFAULT '',
  email TEXT,
  role TEXT NOT NULL CHECK (role IN ('dg_global', 'finance_admin', 'operations_manager', 'module_manager', 'audit_read')),
  modules TEXT NOT NULL DEFAULT 'global',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pilotage_summaries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  module TEXT NOT NULL,
  kind TEXT NOT NULL,
  summary_date TEXT NOT NULL DEFAULT '',
  payload TEXT NOT NULL,
  calculated_at TEXT NOT NULL,
  is_final INTEGER NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 1,
  first_collected_at TEXT,
  collected_at TEXT NOT NULL,
  UNIQUE (module, kind, summary_date)
);
CREATE TABLE IF NOT EXISTS pilotage_source_state (
  module TEXT NOT NULL,
  kind TEXT NOT NULL,
  last_attempt_at TEXT,
  last_success_at TEXT,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  last_error_code TEXT,
  last_error_message TEXT,
  PRIMARY KEY (module, kind)
);
CREATE TABLE IF NOT EXISTS pilotage_financial_access_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  role TEXT NOT NULL,
  resource TEXT NOT NULL,
  module TEXT,
  accessed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pilotage_objectives (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  module TEXT NOT NULL,
  metric TEXT NOT NULL,
  period TEXT NOT NULL CHECK (period IN ('day', 'month')),
  period_start TEXT NOT NULL,
  target_value TEXT NOT NULL,
  unit TEXT NOT NULL,
  revision INTEGER NOT NULL,
  changed_by TEXT NOT NULL,
  changed_at TEXT NOT NULL,
  UNIQUE (module, metric, period, period_start, revision)
);
CREATE TABLE IF NOT EXISTS pilotage_alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fingerprint TEXT NOT NULL UNIQUE,
  alert_type TEXT NOT NULL,
  module TEXT,
  severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  owner_id TEXT,
  status TEXT NOT NULL CHECK (status IN ('open', 'acknowledged', 'resolved')),
  due_at TEXT,
  opened_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS pilotage_alert_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  alert_id INTEGER NOT NULL,
  action TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  details TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS schema_migrations (
  id TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pilotage_summaries_module_kind ON pilotage_summaries(module, kind, summary_date);
CREATE INDEX IF NOT EXISTS idx_pilotage_objectives_lookup ON pilotage_objectives(module, metric, period, period_start, revision);
CREATE INDEX IF NOT EXISTS idx_pilotage_alerts_status ON pilotage_alerts(status, severity, updated_at);
CREATE INDEX IF NOT EXISTS idx_pilotage_alert_events_alert ON pilotage_alert_events(alert_id, created_at);
"""
POSTGRES_SCHEMA = SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def database_url() -> str:
    return os.getenv("PILOTAGE_DATABASE_URL") or os.getenv("DATABASE_URL", "")


def db_path() -> Path:
    default = Path(__file__).resolve().parents[2] / "data" / "pilotage.sqlite3"
    return Path(os.getenv("PILOTAGE_DB_PATH", default))


class _PostgresConnection:
    """Minimal shim so raw SQL written for SQLite runs on psycopg."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def execute(self, query: str, params: tuple = ()):
        return self._connection.execute(query.replace("?", "%s"), params)

    def executescript(self, script: str) -> None:
        for statement in (part.strip() for part in script.split(";")):
            if statement:
                self._connection.execute(statement)


@contextmanager
def db() -> Iterator:
    url = database_url()
    if url:
        with psycopg.connect(url, row_factory=dict_row) as connection:
            yield _PostgresConnection(connection)
            connection.commit()
        return
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def rows(query: str, params: tuple = ()) -> list[dict]:
    with db() as connection:
        cursor = connection.execute(query, params)
        return [dict(record) for record in cursor.fetchall()]


def row(query: str, params: tuple = ()) -> dict | None:
    result = rows(query, params)
    return result[0] if result else None


def execute(query: str, params: tuple = ()) -> None:
    with db() as connection:
        connection.execute(query, params)


def is_ready() -> bool:
    try:
        return bool(row("SELECT 1 AS ready")["ready"])
    except Exception:
        return False


def init_db() -> None:
    schema = POSTGRES_SCHEMA if database_url() else SCHEMA
    with db() as connection:
        connection.executescript(schema)
        connection.execute(
            "INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?) ON CONFLICT (id) DO NOTHING",
            (SCHEMA_VERSION, utc_now_iso()),
        )
        if database_url():
            connection.execute("ALTER TABLE pilotage_summaries ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1")
            connection.execute("ALTER TABLE pilotage_summaries ADD COLUMN IF NOT EXISTS first_collected_at TEXT")
        else:
            columns = {record[1] for record in connection.execute("PRAGMA table_info(pilotage_summaries)").fetchall()}
            if "revision" not in columns:
                connection.execute("ALTER TABLE pilotage_summaries ADD COLUMN revision INTEGER NOT NULL DEFAULT 1")
            if "first_collected_at" not in columns:
                connection.execute("ALTER TABLE pilotage_summaries ADD COLUMN first_collected_at TEXT")
        connection.execute("UPDATE pilotage_summaries SET first_collected_at = collected_at WHERE first_collected_at IS NULL")
        connection.execute(
            "INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?) ON CONFLICT (id) DO NOTHING",
            (SUMMARY_REVISION_MIGRATION, utc_now_iso()),
        )
        connection.execute(
            "INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?) ON CONFLICT (id) DO NOTHING",
            (PLANNING_MIGRATION, utc_now_iso()),
        )
        connection.execute(
            "INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?) ON CONFLICT (id) DO NOTHING",
            (ALERTS_MIGRATION, utc_now_iso()),
        )
