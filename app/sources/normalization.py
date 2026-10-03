"""Consumer-side enrichment for module-owned Pilotage summaries."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation


IDENTITY_AGGREGATIONS = {
    "users_total": "last",
    "users_registered": "sum",
    "users_verified": "last",
    "users_active": "last",
    "daily_active_users": "last",
    "monthly_active_users": "last",
}

METRIC_METADATA = {
    "users_total": ("Utilisateurs totaux", "Nombre total de comptes créés."),
    "users_registered": ("Nouveaux utilisateurs", "Comptes créés pendant la journée."),
    "users_verified": ("Utilisateurs vérifiés", "Comptes vérifiés."),
    "users_active": ("Utilisateurs actifs", "Comptes considérés actifs par DiddiFreeID."),
    "daily_active_users": ("Utilisateurs actifs du jour", "Utilisateurs distincts actifs pendant la journée."),
    "monthly_active_users": ("Utilisateurs actifs sur 30 jours", "Utilisateurs distincts actifs sur la fenêtre mensuelle."),
    "rides_requested": ("Courses demandées", "Demandes de course créées pendant la journée."),
    "rides_completed": ("Courses terminées", "Courses terminées pendant la journée."),
    "completed_fare_total_xof": ("Montant des courses terminées", "Somme finale des courses terminées."),
    "deliveries_requested": ("Livraisons demandées", "Demandes de livraison créées pendant la journée."),
    "deliveries_completed": ("Livraisons terminées", "Livraisons terminées pendant la journée."),
    "completed_delivery_value": ("Valeur des livraisons terminées", "Valeur finale des livraisons terminées."),
    "confirmed_payments_count": ("Paiements confirmés", "Nombre de paiements confirmés par DiddiPay."),
    "confirmed_payments_amount_xof": ("Montant des paiements confirmés", "Montant confirmé par DiddiPay."),
    "confirmed_refunds_count": ("Remboursements confirmés", "Nombre de remboursements confirmés."),
    "confirmed_refunds_amount_xof": ("Montant remboursé", "Montant des remboursements confirmés."),
    "processor_fees_amount_xof": ("Frais processeur", "Frais du processeur de paiement."),
    "net_expected_delta_xof": ("Net attendu", "Variation nette attendue après remboursements et frais."),
    "settlements_count": ("Règlements reçus", "Nombre de règlements processeur enregistrés."),
    "settlements_amount_xof": ("Montant réglé", "Montant des règlements processeur."),
    "payouts_count": ("Versements participants", "Nombre de versements aux participants."),
    "payouts_amount_xof": ("Montant versé aux participants", "Montant versé aux participants."),
    "gross_delivery_value": ("Valeur brute des livraisons", "Valeur brute comptabilisée par DiddiSend."),
    "digital_paid_value": ("Livraisons payées en ligne", "Valeur DiddiSend réglée par paiement numérique."),
    "cash_collected": ("Espèces collectées", "Espèces déclarées comme collectées par les coursiers."),
    "cash_to_remit": ("Espèces à reverser", "Montant attendu des reversements en espèces."),
    "cash_remitted": ("Espèces reversées", "Montant effectivement reversé."),
    "cash_outstanding": ("Espèces restant à reverser", "Montant encore dû à la plateforme."),
    "platform_commission": ("Commission DiddiFree", "Commission attribuée à la plateforme."),
    "courier_earnings": ("Revenus coursiers", "Revenus attribués aux coursiers."),
    "partner_share": ("Part partenaires", "Revenus attribués aux partenaires de flotte."),
    "collection_anomalies": ("Anomalies d'encaissement", "Nombre d'anomalies de collecte détectées."),
    "overdue_cash_to_remit": ("Reversements en retard", "Montant dont l'échéance de reversement est dépassée."),
}

DERIVED_METRICS = {
    "identity": [
        {
            "name": "verification_rate",
            "label": "Taux de comptes vérifiés",
            "unit": "percent",
            "aggregation": "ratio",
            "numerator": "users_verified",
            "denominator": "users_total",
            "scale": 100,
        }
    ],
    "diddigo": [
        {
            "name": "ride_completion_rate",
            "label": "Taux de courses terminées",
            "unit": "percent",
            "aggregation": "ratio",
            "numerator": "rides_completed",
            "denominator": "rides_requested",
            "scale": 100,
        },
        {
            "name": "average_completed_fare_xof",
            "label": "Montant moyen par course terminée",
            "unit": "XOF",
            "aggregation": "weighted_average",
            "numerator": "completed_fare_total_xof",
            "denominator": "rides_completed",
        },
    ],
    "diddisend": [
        {
            "name": "delivery_completion_rate",
            "label": "Taux de livraisons terminées",
            "unit": "percent",
            "aggregation": "ratio",
            "numerator": "deliveries_completed",
            "denominator": "deliveries_requested",
            "scale": 100,
        },
        {
            "name": "average_completed_delivery_value_xof",
            "label": "Valeur moyenne par livraison terminée",
            "unit": "XOF",
            "aggregation": "weighted_average",
            "numerator": "completed_delivery_value",
            "denominator": "deliveries_completed",
        },
    ],
    "diddipay": [
        {
            "name": "refund_event_rate",
            "label": "Taux d'événements de remboursement",
            "unit": "percent",
            "aggregation": "ratio",
            "numerator": "confirmed_refunds_count",
            "denominator": "confirmed_payments_count",
            "scale": 100,
        }
    ],
}


def _decimal(value) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _derived_metric(spec: dict, values: dict[str, object]) -> dict | None:
    numerator = _decimal(values.get(spec["numerator"]))
    denominator = _decimal(values.get(spec["denominator"]))
    if numerator is None or denominator is None or denominator == 0:
        return None
    value = numerator / denominator * Decimal(str(spec.get("scale", 1)))
    serialized_value: float | str
    if spec["unit"] == "XOF":
        serialized_value = format(value.quantize(Decimal("0.01")), "f")
    else:
        serialized_value = float(value.quantize(Decimal("0.01")))
    return {**spec, "value": serialized_value}


def normalize_daily_summary(module: str, payload: dict) -> dict:
    """Add consumer metadata without changing a module's business values."""
    normalized = deepcopy(payload)
    metrics = normalized.get("metrics")
    if not isinstance(metrics, list):
        return normalized

    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        name = metric.get("name")
        metadata = METRIC_METADATA.get(name)
        if metadata:
            metric.setdefault("label", metadata[0])
            metric.setdefault("description", metadata[1])
        if module == "identity":
            metric.setdefault("aggregation", IDENTITY_AGGREGATIONS.get(name, "last"))
        else:
            metric.setdefault("aggregation", "sum")
    values = {metric.get("name"): metric.get("value") for metric in metrics if isinstance(metric, dict)}
    existing_names = set(values)
    for spec in DERIVED_METRICS.get(module, []):
        if spec["name"] in existing_names:
            continue
        derived = _derived_metric(spec, values)
        if derived is not None:
            metrics.append(derived)
    return normalized
