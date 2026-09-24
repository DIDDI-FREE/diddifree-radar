"""Persistence for collected summaries and per-source collection state.

The store implements the protocol's core failure rule: a failed source never
becomes a zero KPI. Failures only touch ``pilotage_source_state``; the last
valid summary stays in ``pilotage_summaries`` and is served with a stale or
unavailable freshness status.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from app.contracts.common import Freshness
from app.core.db import execute, row, rows, utc_now_iso


def freshness_window_seconds() -> int:
    return int(os.getenv("PILOTAGE_FRESHNESS_WINDOW_SECONDS", "60"))


def save_summary(module: str, kind: str, summary_date: str, payload: dict, calculated_at: str, is_final: bool) -> None:
    now = utc_now_iso()
    execute(
        """
        INSERT INTO pilotage_summaries (module, kind, summary_date, payload, calculated_at, is_final, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (module, kind, summary_date) DO UPDATE SET
          payload = excluded.payload,
          calculated_at = excluded.calculated_at,
          is_final = excluded.is_final,
          collected_at = excluded.collected_at
        """,
        (module, kind, summary_date, json.dumps(payload, default=str), calculated_at, int(is_final), now),
    )


def latest_summary(module: str, kind: str, summary_date: str | None = None) -> dict | None:
    if summary_date:
        record = row(
            "SELECT * FROM pilotage_summaries WHERE module = ? AND kind = ? AND summary_date = ?",
            (module, kind, summary_date),
        )
    else:
        record = row(
            "SELECT * FROM pilotage_summaries WHERE module = ? AND kind = ? ORDER BY summary_date DESC LIMIT 1",
            (module, kind),
        )
    if not record:
        return None
    record["payload"] = json.loads(record["payload"])
    return record


def summaries_range(module: str, kind: str, from_date: str, to_date: str) -> list[dict]:
    records = rows(
        "SELECT * FROM pilotage_summaries WHERE module = ? AND kind = ? AND summary_date >= ? AND summary_date <= ? ORDER BY summary_date",
        (module, kind, from_date, to_date),
    )
    for record in records:
        record["payload"] = json.loads(record["payload"])
    return records


def record_success(module: str, kind: str) -> None:
    now = utc_now_iso()
    execute(
        """
        INSERT INTO pilotage_source_state (module, kind, last_attempt_at, last_success_at, consecutive_failures, last_error_code, last_error_message)
        VALUES (?, ?, ?, ?, 0, NULL, NULL)
        ON CONFLICT (module, kind) DO UPDATE SET
          last_attempt_at = excluded.last_attempt_at,
          last_success_at = excluded.last_success_at,
          consecutive_failures = 0,
          last_error_code = NULL,
          last_error_message = NULL
        """,
        (module, kind, now, now),
    )


def record_failure(module: str, kind: str, code: str, message: str) -> None:
    now = utc_now_iso()
    execute(
        """
        INSERT INTO pilotage_source_state (module, kind, last_attempt_at, last_success_at, consecutive_failures, last_error_code, last_error_message)
        VALUES (?, ?, ?, NULL, 1, ?, ?)
        ON CONFLICT (module, kind) DO UPDATE SET
          last_attempt_at = excluded.last_attempt_at,
          consecutive_failures = pilotage_source_state.consecutive_failures + 1,
          last_error_code = excluded.last_error_code,
          last_error_message = excluded.last_error_message
        """,
        (module, kind, now, code, message),
    )


def source_state(module: str, kind: str) -> dict | None:
    return row("SELECT * FROM pilotage_source_state WHERE module = ? AND kind = ?", (module, kind))


def all_source_states() -> list[dict]:
    return rows("SELECT * FROM pilotage_source_state ORDER BY module, kind")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def compute_freshness(module: str, kind: str, *, source_updated_at: str | None = None) -> Freshness:
    state = source_state(module, kind)
    now = datetime.now(timezone.utc)
    last_success = _parse_iso(state["last_success_at"]) if state else None
    if not last_success:
        return Freshness(
            status="unavailable",
            synchronized_at=_parse_iso(state["last_attempt_at"]) or now if state else now,
        )
    age_seconds = (now - last_success).total_seconds()
    return Freshness(
        status="fresh" if age_seconds <= freshness_window_seconds() else "stale",
        synchronized_at=last_success,
        source_updated_at=_parse_iso(source_updated_at),
        last_success_at=last_success,
    )
