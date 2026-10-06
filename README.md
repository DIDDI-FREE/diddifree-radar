# DiddiFree Pilotage (DiddiRadar backend)

Implementation roadmap: [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).

Read-model service for management visibility: module KPIs, freshness, and
deep links back to the Backoffice. It observes; it never mutates DiddiGo,
DiddiSend, DiddiPay, DiddiMap, DiddiFood, DiddiFiles or DiddiFreeID records.

Protocol references:

- `backend/docs/pilotage-read-model-protocol-v1.md`
- `backend/docs/diddifree-internal-integration-guide-v1.md`
- `DIDDIFREE_PILOTAGE_BRIEF.md`

## How it works

```text
collector (scripts/run_collector.py)
  -> PilotageSourceClient per module
       GET {module-specific daily summary path}?date=YYYY-MM-DD
       Authorization: Bearer <S2S token, client_id=pilotage-staging, scope=<module>:pilotage-summary:read>
  -> validate against pilotage.v1 (app/contracts/pilotage.py)
  -> store in pilotage_summaries; state in pilotage_source_state
  -> refresh daily summaries, finance and supported breakdowns independently
     (60 seconds by default for each stream)

api (uvicorn app.main:app)
  GET  /api/pilotage/overview                          summaries, finance, breakdown highlights and coverage
  GET  /api/pilotage/modules/{module}/daily-summary    one stored summary
  GET  /api/pilotage/modules/{module}/breakdown        one stored operational breakdown
  GET  /api/pilotage/modules/{module}/breakdown-aggregates weekly/monthly breakdowns
  GET  /api/pilotage/modules/{module}/finance-summary  protected financial view
  GET  /api/pilotage/accounting/daily-export           consolidated daily export for Odoo
  GET  /api/pilotage/sources                           collection state per source
  POST /api/pilotage/sources/{module}/collect          manual collection trigger
  GET  /api/pilotage/objectives                        objectives and progress
  PUT  /api/pilotage/objectives/{module}/{metric}      create a new objective revision
  GET  /api/pilotage/alerts                            deduplicated operational alerts
  PATCH /api/pilotage/alerts/{id}                      assign or change alert status
  GET  /api/pilotage/reports/{day|week|month}          JSON or CSV management report
  GET  /api/pilotage/health, /health                   health probes
  GET  /ready                                          database readiness probe
```

## API et frontend séparés

En staging et production, lancer l'API avec `PILOTAGE_SERVE_FRONTEND=0`.
La racine `/` répond alors `404`, tandis que `/api/*`, `/docs`, `/openapi.json`
et `/health` restent disponibles. Le frontend peut être déployé sur un autre
domaine et autorisé explicitement par `PILOTAGE_CORS_ORIGINS`.

Le frontend actuel reste servi par l'API en développement avec
`PILOTAGE_SERVE_FRONTEND=1`. Cette option facilite le développement local sans
créer de dépendance fonctionnelle entre les deux composants.

Un consommateur comme Odoo doit utiliser les routes JSON sous `/api/pilotage`
et le contrat OpenAPI publié par `/openapi.json`. Il ne doit pas dépendre du
HTML ni appeler directement les bases des modules sources.

Les `deep_links` relatifs fournis par les modules sont convertis par l'API en
URL absolues avec `PILOTAGE_BACKOFFICE_BASE_URL`. En staging, la valeur par
défaut est `https://admin-staging.diddifree.com`. Le frontend ouvre ces liens
dans un nouvel onglet, car Pilotage et Backoffice utilisent des domaines distincts.

Failure rule (protocol): a failed source never becomes a zero KPI. Failures
only update `pilotage_source_state`; the last valid summary keeps being
served with freshness `stale`. A module that has never answered reports
`unavailable`. Default window: fresh <= 60s since the last success.

The current DiddiGo, DiddiSend and DiddiPay contracts expose
`/internal/pilotage/daily-summary`; DiddiFreeID exposes
`/internal/pilotage/identity-summary`. Paths, audiences and scopes remain
overridable per module so a contract migration does not require browser changes.

## Auth

- Humans: DiddiFreeID OIDC bearer tokens (same JWKS as the Backoffice),
  with `sub` as the stable identifier and `iss=diddifree-id`; no human
  audience is required. The current profile is read from `/users/me`.
  then Pilotage-local roles in `pilotage_users`:
  `dg_global`, `finance_admin`, `operations_manager`, `module_manager`
  (restricted via the `modules` CSV column), `audit_read`.
  First login provisioning: emails in `PILOTAGE_BOOTSTRAP_DG_EMAILS`
  become `dg_global`.
- Outbound: short-lived S2S tokens via the shared client
  (`PILOTAGE_SERVICE_CLIENT_ID`, default audience = module key). Static
  per-module tokens are migration/emergency fallback only.
- Inbound services: `aud=pilotage`, `pilotage:read`, `role=service`,
  `token_type=service`, matching `client_id`/`X-Client-ID`; module access is
  assigned locally through `PILOTAGE_TRUSTED_SERVICE_MODULES_JSON`.
- `PILOTAGE_ALLOW_INSECURE_HEADERS=1` enables the `X-User-Id`/`X-Role`
  header path for local development and tests only.

## Contracts

`app/contracts/` is the consumer-side copy of
`backend/app/internal_contracts/` — same fields, but tolerant to additive
upstream fields (`extra="ignore"`). Both copies are meant to move into the
`diddifree-internal-kit` package once the protocol settles.

## Run locally

```bash
cd pilotage
pip install -e .
PILOTAGE_ALLOW_INSECURE_HEADERS=1 uvicorn app.main:app --reload --port 8090
python scripts/run_collector.py          # separate terminal
python -m unittest discover tests        # tests
```

SQLite is the default store (`pilotage/data/pilotage.sqlite3`); set
`PILOTAGE_DATABASE_URL` for Postgres. Staging runs through
`docker-compose.staging.yml` (postgres + api + collector), mirroring the
Backoffice deployment layout.

Operational deployment, backup, restore and rollback steps are documented in
[`docs/STAGING_RUNBOOK.md`](docs/STAGING_RUNBOOK.md).

The Odoo accounting contract and authenticated staging recipe are documented
in [`docs/DIDDIPAY_ODOO_DAILY_EXPORT_BRIEF.md`](docs/DIDDIPAY_ODOO_DAILY_EXPORT_BRIEF.md).
