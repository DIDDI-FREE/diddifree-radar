from __future__ import annotations

import csv
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.alerts import list_alerts
from app.collector import store
from app.collector.collector import DAILY_KIND
from app.collector.rollups import aggregate_periods
from app.planning import list_objectives
from app.sources.catalog import get_source


def build_report(*, period: str, anchor: date, modules: list[str], include_finance: bool) -> dict:
    blocks = []
    for module in modules:
        if period == "day":
            record = store.latest_summary(module, DAILY_KIND, summary_date=anchor.isoformat())
            metrics = record["payload"].get("metrics", []) if record else []
            coverage = {"days_with_data": int(bool(record)), "expected_days": 1, "is_complete": bool(record and record["is_final"])}
            start = end = anchor.isoformat()
        else:
            bucket = aggregate_periods(module, period=period, count=1, today=anchor)[0]
            metrics = bucket["metrics"]
            coverage = {key: bucket[key] for key in ("days_with_data", "expected_days", "is_complete")}
            start, end = bucket["start"], bucket["end"]
        if not include_finance:
            metrics = [metric for metric in metrics if str(metric.get("unit", "")).upper() != "XOF"]
        freshness = store.compute_freshness(module, DAILY_KIND).model_dump(mode="json")
        blocks.append({"module": module, "display_name": get_source(module).display_name, "from": start, "to": end, "coverage": coverage, "freshness": freshness, "metrics": metrics})
    objectives = [item for item in list_objectives() if item["module"] in modules and (include_finance or item["unit"].upper() != "XOF")]
    alerts = [item for item in list_alerts(status="open") if item["module"] in modules]
    return {
        "contract_version": "pilotage.report.v1",
        "period": period,
        "anchor": anchor.isoformat(),
        "modules": blocks,
        "objectives": objectives,
        "open_alerts": alerts,
    }


def report_csv(report: dict) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["period", "from", "to", "module", "metric", "label", "value", "unit", "days_with_data", "expected_days", "is_complete"])
    for block in report["modules"]:
        for metric in block["metrics"]:
            writer.writerow([
                report["period"], block["from"], block["to"], block["module"], metric.get("name"), metric.get("label") or metric.get("name"),
                metric.get("value"), metric.get("unit"), block["coverage"]["days_with_data"], block["coverage"]["expected_days"], block["coverage"]["is_complete"],
            ])
    return output.getvalue()


def report_pdf(report: dict) -> bytes:
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title=f"DiddiFree Pilotage - {report['period']}")
    story = [Paragraph("DiddiFree Pilotage", styles["Title"]), Paragraph(f"Rapport {report['period']} - ancrage {report['anchor']}", styles["Heading2"]), Spacer(1, 5 * mm)]
    for index, block in enumerate(report["modules"]):
        if index:
            story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(block["display_name"], styles["Heading2"]))
        coverage = block["coverage"]
        freshness = block["freshness"].get("status", "unavailable")
        story.append(Paragraph(f"Periode: {block['from']} au {block['to']} - couverture: {coverage['days_with_data']}/{coverage['expected_days']} jours - source: {freshness}", styles["BodyText"]))
        data = [["Indicateur", "Valeur", "Unite"]]
        data.extend([[metric.get("label") or metric.get("name"), str(metric.get("value", "")), metric.get("unit", "")] for metric in block["metrics"]])
        if len(data) == 1:
            data.append(["Aucune donnee", "", ""])
        table = Table(data, colWidths=[105 * mm, 35 * mm, 22 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e2530")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa4b2")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f5f7")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)
    if report["open_alerts"]:
        story.extend([PageBreak(), Paragraph("Alertes ouvertes", styles["Heading1"])])
        for alert in report["open_alerts"]:
            story.append(Paragraph(f"[{alert['severity'].upper()}] {alert['title']} - {alert['message']}", styles["BodyText"]))
            story.append(Spacer(1, 2 * mm))
    document.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return output.getvalue()


def _page_footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#667085"))
    canvas.drawString(16 * mm, 9 * mm, "DiddiFree Pilotage")
    canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Page {document.page}")
    canvas.restoreState()
