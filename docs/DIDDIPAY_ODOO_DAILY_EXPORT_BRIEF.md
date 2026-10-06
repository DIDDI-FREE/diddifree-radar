# Contrat quotidien Pilotage vers Odoo

Date : 2026-10-06

## Route appelée par Odoo

```http
GET /api/pilotage/accounting/daily-export?date=2026-10-05
Authorization: Bearer <service token>
X-Client-ID: <client_id présent dans le token>
```

Sur staging :

```text
https://supervision.diddifree.com/api/pilotage/accounting/daily-export?date=2026-10-05
```

Le jeton DiddiFreeID doit avoir `aud=pilotage`, `sub=service:odoo`, les scopes
`pilotage:read pilotage:finance:read`, et un `client_id` strictement égal à
`X-Client-ID`. Pilotage doit autoriser localement `service:odoo` et lui donner
le module `global`.

## Sources regroupées

- `business_summaries` conserve sans renommage les métriques financières de
  DiddiGo, DiddiSend et DiddiFood. Ces services restent propriétaires des
  montants métier, dont la part chauffeur, livreur ou restaurant.
- `payment_entries` provient de
  `GET /payfund/v1/internal/pilotage/accounting-summary` de DiddiPay. DiddiPay
  reste propriétaire des frais processeur, settlements, payouts et
  remboursements partiels exacts.
- `reconciliation.blockers` liste une source absente. Une absence ne devient
  jamais un zéro comptable.

Les écritures DiddiPay sont ventilées par `service`, `processor`, `flow_type`
et `status`. `flow_type` permet notamment de séparer `wallet_topup` de
`service_payment`, ainsi que `refund`, `settlement` et `payout`.

## Idempotence

Odoo enregistre `contract_version + date + revision`. Il doit rejouer une date
si sa révision augmente. `is_final=true` signifie que toutes les sources
attendues sont présentes et finales. `reconciliation.status=partial` interdit
de considérer les sections absentes comme nulles.

Le collecteur relit au démarrage les sept dernières journées fermées, puis la
veille à chaque changement de date en heure d'Abidjan. Cela permet de remplacer
les instantanés provisoires collectés pendant la journée par la version finale
publiée après minuit. La fenêtre est réglable avec
`PILOTAGE_FINALIZATION_LOOKBACK_DAYS`.

## Recette authentifiée

Le script ne journalise jamais le secret ni le jeton :

```bash
export PILOTAGE_ODOO_CLIENT_ID=odoo-staging-pilotage
export PILOTAGE_ODOO_CLIENT_SECRET='...'
python scripts/verify_odoo_export_staging.py --date 2026-10-05
```

La sortie standard est la réponse JSON réelle de Pilotage. Elle confirme aussi
les noms exacts des métriques reçues de DiddiGo dans `business_summaries`.
