from __future__ import annotations

import json

from app.collector import store
from app.core.db import execute, row, rows, utc_now_iso
from app.sources.catalog import enabled_modules


def _event(alert_id: int, action: str, actor_id: str, details: dict | None = None) -> None:
    execute(
        "INSERT INTO pilotage_alert_events (alert_id, action, actor_id, details, created_at) VALUES (?, ?, ?, ?, ?)",
        (alert_id, action, actor_id, json.dumps(details or {}, sort_keys=True), utc_now_iso()),
    )


def upsert_alert(*, fingerprint: str, alert_type: str, module: str | None, severity: str, title: str, message: str) -> dict:
    current = row("SELECT * FROM pilotage_alerts WHERE fingerprint = ?", (fingerprint,))
    now = utc_now_iso()
    if current:
        reopened = current["status"] == "resolved"
        execute(
            "UPDATE pilotage_alerts SET alert_type=?, module=?, severity=?, title=?, message=?, status=?, updated_at=?, resolved_at=NULL WHERE fingerprint=?",
            (alert_type, module, severity, title, message, "open" if reopened else current["status"], now, fingerprint),
        )
        updated = row("SELECT * FROM pilotage_alerts WHERE fingerprint = ?", (fingerprint,))
        if reopened:
            _event(updated["id"], "reopened", "system")
        return updated
    execute(
        "INSERT INTO pilotage_alerts (fingerprint, alert_type, module, severity, title, message, status, opened_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)",
        (fingerprint, alert_type, module, severity, title, message, now, now),
    )
    created = row("SELECT * FROM pilotage_alerts WHERE fingerprint = ?", (fingerprint,))
    _event(created["id"], "opened", "system")
    return created


def reconcile_source_alerts() -> list[dict]:
    active: set[str] = set()
    for module in enabled_modules():
        freshness = store.compute_freshness(module, "daily")
        state = store.source_state(module, "daily") or {}
        if freshness.status in {"stale", "unavailable"}:
            fingerprint = f"source:{module}:{freshness.status}"
            active.add(fingerprint)
            severity = "critical" if freshness.status == "unavailable" or int(state.get("consecutive_failures") or 0) >= 3 else "warning"
            upsert_alert(
                fingerprint=fingerprint,
                alert_type="source_health",
                module=module,
                severity=severity,
                title=f"Source {module} {freshness.status}",
                message=f"La synthèse quotidienne {module} est {freshness.status}.",
            )
    existing = rows("SELECT id, fingerprint FROM pilotage_alerts WHERE alert_type = 'source_health' AND status != 'resolved'")
    now = utc_now_iso()
    for alert in existing:
        if alert["fingerprint"] not in active:
            execute("UPDATE pilotage_alerts SET status='resolved', resolved_at=?, updated_at=? WHERE id=?", (now, now, alert["id"]))
            _event(alert["id"], "auto_resolved", "system")
    return list_alerts()


def list_alerts(*, status: str | None = None, module: str | None = None) -> list[dict]:
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if module:
        clauses.append("module = ?")
        params.append(module)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return rows("SELECT * FROM pilotage_alerts" + where + " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, updated_at DESC", tuple(params))


def update_alert(alert_id: int, *, actor_id: str, status: str | None = None, owner_id: str | None = None, due_at: str | None = None) -> dict | None:
    current = row("SELECT * FROM pilotage_alerts WHERE id = ?", (alert_id,))
    if not current:
        return None
    new_status = status or current["status"]
    resolved_at = utc_now_iso() if new_status == "resolved" else None
    execute(
        "UPDATE pilotage_alerts SET status=?, owner_id=?, due_at=?, resolved_at=?, updated_at=? WHERE id=?",
        (new_status, owner_id if owner_id is not None else current["owner_id"], due_at if due_at is not None else current["due_at"], resolved_at, utc_now_iso(), alert_id),
    )
    _event(alert_id, "updated", actor_id, {"status": status, "owner_id": owner_id, "due_at": due_at})
    return row("SELECT * FROM pilotage_alerts WHERE id = ?", (alert_id,))


def alert_history(alert_id: int) -> list[dict]:
    events = rows("SELECT action, actor_id, details, created_at FROM pilotage_alert_events WHERE alert_id = ? ORDER BY id", (alert_id,))
    for event in events:
        event["details"] = json.loads(event["details"])
    return events
