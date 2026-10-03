from __future__ import annotations

import json
import os
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

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
            critical_failures = max(1, int(os.getenv("PILOTAGE_ALERT_SOURCE_FAILURES_CRITICAL", "3")))
            severity = "critical" if freshness.status == "unavailable" or int(state.get("consecutive_failures") or 0) >= critical_failures else "warning"
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


def _number(value) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _metrics(record: dict | None) -> dict[str, Decimal]:
    result = {}
    for metric in (record or {}).get("payload", {}).get("metrics", []):
        value = _number(metric.get("value"))
        if metric.get("name") and value is not None:
            result[metric["name"]] = value
    return result


def _resolve_inactive(alert_types: tuple[str, ...], active: set[str]) -> None:
    placeholders = ",".join("?" for _ in alert_types)
    existing = rows(f"SELECT id, fingerprint FROM pilotage_alerts WHERE alert_type IN ({placeholders}) AND status != 'resolved'", alert_types)
    now = utc_now_iso()
    for alert in existing:
        if alert["fingerprint"] not in active:
            execute("UPDATE pilotage_alerts SET status='resolved', resolved_at=?, updated_at=? WHERE id=?", (now, now, alert["id"]))
            _event(alert["id"], "auto_resolved", "system")


def reconcile_business_alerts(anchor: date) -> list[dict]:
    active: set[str] = set()
    drop_threshold = Decimal(os.getenv("PILOTAGE_ALERT_ACTIVITY_DROP_PERCENT", "30"))
    cancellation_threshold = Decimal(os.getenv("PILOTAGE_ALERT_CANCELLATION_RATE_PERCENT", "20"))
    financial_threshold = Decimal(os.getenv("PILOTAGE_ALERT_FINANCIAL_GAP_XOF", "1000"))
    overdue_threshold = Decimal(os.getenv("PILOTAGE_ALERT_OVERDUE_FUNDS_XOF", "1"))
    activity_metrics = {"diddigo": "rides_requested", "diddisend": "deliveries_requested", "diddifood": "orders_placed", "identity": "daily_active_users", "diddipay": "confirmed_payments_count"}

    for module, metric_name in activity_metrics.items():
        current = _metrics(store.latest_summary(module, "daily", anchor.isoformat())).get(metric_name)
        previous_records = store.summaries_range(module, "daily", (anchor - timedelta(days=7)).isoformat(), (anchor - timedelta(days=1)).isoformat())
        previous = [_metrics(record).get(metric_name) for record in previous_records]
        previous = [value for value in previous if value is not None]
        if current is not None and previous:
            average = sum(previous, Decimal("0")) / len(previous)
            drop = (average - current) / average * 100 if average > 0 else Decimal("0")
            if drop >= drop_threshold:
                fingerprint = f"activity_drop:{module}:{metric_name}"
                active.add(fingerprint)
                upsert_alert(fingerprint=fingerprint, alert_type="activity_drop", module=module, severity="warning", title=f"Baisse d'activité {module}", message=f"{metric_name} baisse de {drop.quantize(Decimal('0.1'))}% par rapport à la moyenne des 7 jours disponibles.")

    cancellation_specs = {"diddifood": ("orders_cancelled", "orders_placed")}
    for module, (cancelled_name, requested_name) in cancellation_specs.items():
        values = _metrics(store.latest_summary(module, "daily", anchor.isoformat()))
        cancelled, requested = values.get(cancelled_name), values.get(requested_name)
        if cancelled is not None and requested and requested > 0:
            rate = cancelled / requested * 100
            if rate >= cancellation_threshold:
                fingerprint = f"cancellation_rate:{module}"
                active.add(fingerprint)
                upsert_alert(fingerprint=fingerprint, alert_type="cancellation_rate", module=module, severity="warning", title=f"Taux d'annulation élevé {module}", message=f"Le taux d'annulation atteint {rate.quantize(Decimal('0.1'))}%.")

    for module, requested_metric in (("diddigo", "rides_requested"), ("diddisend", "deliveries_requested")):
        record = store.latest_summary(module, f"breakdown:final_status:{requested_metric}", anchor.isoformat())
        if not record:
            continue
        total = _number(record["payload"].get("total"))
        cancelled = sum((_number(item.get("value")) or Decimal("0") for item in record["payload"].get("items", []) if "cancel" in str(item.get("key", "")).lower()), Decimal("0"))
        if total and total > 0:
            rate = cancelled / total * 100
            if rate >= cancellation_threshold:
                fingerprint = f"cancellation_rate:{module}"
                active.add(fingerprint)
                upsert_alert(fingerprint=fingerprint, alert_type="cancellation_rate", module=module, severity="warning", title=f"Taux d'annulation élevé {module}", message=f"Le taux d'annulation atteint {rate.quantize(Decimal('0.1'))}%.")

    send_finance = _metrics(store.latest_summary("diddisend", "finance", anchor.isoformat()))
    overdue = send_finance.get("overdue_cash_to_remit")
    if overdue is not None and overdue >= overdue_threshold:
        fingerprint = "overdue_funds:diddisend"
        active.add(fingerprint)
        upsert_alert(fingerprint=fingerprint, alert_type="overdue_funds", module="diddisend", severity="critical", title="Reversements DiddiSend en retard", message=f"{overdue} XOF restent en retard de reversement.")

    pay = _metrics(store.latest_summary("diddipay", "daily", anchor.isoformat()))
    expected, settled = pay.get("net_expected_delta_xof"), pay.get("settlements_amount_xof")
    if expected is not None and settled is not None and abs(expected - settled) >= financial_threshold:
        fingerprint = "financial_gap:diddipay"
        active.add(fingerprint)
        upsert_alert(fingerprint=fingerprint, alert_type="financial_gap", module="diddipay", severity="critical", title="Écart entre flux attendus et règlements", message=f"L'écart global DiddiPay atteint {abs(expected - settled)} XOF.")

    _resolve_inactive(("activity_drop", "cancellation_rate", "overdue_funds", "financial_gap"), active)
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
