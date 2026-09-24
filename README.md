# DiddiFree Pilotage (DiddiRadar backend)

Read-model service for management visibility: module KPIs, freshness, and
deep links back to the Backoffice. It observes; it never mutates DiddiGo,
DiddiSend, DiddiPay, DiddiMap, DiddiFood, DiddiFiles or DiddiFreeID records.

Protocol references:

- `backend/docs/pilotage-read-model-protocol-v1.md`
- `backend/docs/diddifree-internal-integration-guide-v1.md`
- `DIDDIFREE_PILOTAGE_BRIEF.md`

## How it works

```text
collector (scripts/run_collector.py, every PILOTAGE_COLLECT_INTERVAL_SECONDS)
  -> PilotageSourceClient per module
       GET {module}/internal/pilotage/daily-summary?date=YYYY-MM-DD
       Authorization: Bearer <S2S token, client_id=pilotage-staging, scope=<module>:pilotage-summary:read>
  -> validate against pilotage.v1 (app/contracts/pilotage.py)
  -> store in pilotage_summaries; state in pilotage_source_state

api (uvicorn app.main:app)
  GET  /api/pilotage/overview                          all visible module blocks + freshness
  GET  /api/pilotage/modules/{module}/daily-summary    one stored summary
  GET  /api/pilotage/sources                           collection state per source
  POST /api/pilotage/sources/{module}/collect          manual collection trigger
  GET  /api/pilotage/health, /health                   health probes
```

Failure rule (protocol): a failed source never becomes a zero KPI. Failures
only update `pilotage_source_state`; the last valid summary keeps being
served with freshness `stale`. A module that has never answered reports
`unavailable`. Default window: fresh <= 60s since the last success.

No upstream module exposes `/internal/pilotage/*` yet — until each one
ships its route, its source reports `unavailable` with
`last_error.code = "route_missing"`. Nothing breaks; the day the route
appears, collection starts working with zero changes here.

## Auth

- Humans: DiddiFreeID OIDC bearer tokens (same JWKS as the Backoffice),
  then Pilotage-local roles in `pilotage_users`:
  `dg_global`, `finance_admin`, `operations_manager`, `module_manager`
  (restricted via the `modules` CSV column), `audit_read`.
  First login provisioning: emails in `PILOTAGE_BOOTSTRAP_DG_EMAILS`
  become `dg_global`.
- Outbound: short-lived S2S tokens via the shared client
  (`PILOTAGE_SERVICE_CLIENT_ID`, default audience = module key). Static
  per-module tokens are migration/emergency fallback only.
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
