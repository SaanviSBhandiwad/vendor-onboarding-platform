# Intelligent Vendor Onboarding & Compliance Platform

An asynchronous vendor onboarding platform: registration, duplicate detection, compliance
verification (RAG + LLM), SLA-risk prediction (CatBoost + SHAP), human review and notifications.

**Current phase: 1 – Backend foundation** (Days 1–2 of the plan)

## Quick start

```bash
cp backend/.env.example backend/.env
make up                      # Postgres (pgvector), Redis, API; runs migrations on start
open http://localhost:8000/docs
```

Local development without Docker for the API:

```bash
docker compose up -d db redis
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
pytest -q
```

## API (v1)

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/vendors` | Register a vendor (201, 409 duplicate, 422 invalid) |
| GET | `/api/v1/vendors` | List with `status`, `region`, `limit`, `offset` |
| GET | `/api/v1/vendors/{id}` | Vendor details and current status |
| POST | `/api/v1/vendors/{id}/status` | State transition (409 if not allowed) |
| GET | `/api/v1/vendors/{id}/audit-logs` | Decision trail |
| GET | `/health`, `/health/ready` | Liveness / readiness (checks DB) |

All errors share one envelope:
`{"error": {"code", "message", "details", "request_id"}}`

## Onboarding state machine

```
PENDING ──► DOCUMENTS_SUBMITTED ──► UNDER_REVIEW ──► APPROVED
   │              │                    │    │
   │              └──► PENDING ◄───────┘    └──► MANUAL_REVIEW ──► APPROVED / REJECTED / PENDING
   └──► REJECTED                       └──► REJECTED
```

Defined in one place (`app/services/state_machine.py`). APPROVED and REJECTED are terminal.

## Design decisions

- **Duplicate safety in two layers.** A pre-check returns a helpful 409 naming the colliding
  field; `UNIQUE` constraints on `email` and `gstin` guarantee correctness when concurrent
  requests both pass the pre-check. Inputs are normalized (lowercase email, uppercase GSTIN)
  before storage so the constraint is meaningful. `test_database_constraint_catches_race`
  bypasses the pre-check to prove the constraint alone holds.
- **Row locks on transitions.** `SELECT ... FOR UPDATE` serializes concurrent status changes
  so two reviewers cannot both act on the same stale state.
- **Audit in the same transaction.** Status changes and their audit entries commit together;
  there is never a change without a record, or a record without a change.
- **Correlation IDs.** Every request gets an `X-Request-ID` (or reuses the caller's), which
  appears in JSON logs, error responses and audit rows.
- **Versioned schema.** Alembic migrations with deterministic constraint names; CI runs
  `alembic check` to fail the build if models and migrations drift.

## Verifying concurrency yourself

With the stack running, fire 20 identical registrations at once and confirm exactly one row:

```bash
P='{"legal_name":"Race Co","email":"race@co.in","gstin":"29AABCU9603R1ZM","region":"south","service_type":"consumables"}'
for i in $(seq 20); do curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/api/v1/vendors \
  -H 'content-type: application/json' -d "$P" & done | sort | uniq -c
```

## Roadmap

- [x] Days 1–2: FastAPI structure, schema + migrations, REST APIs, validation, state machine, audit log
- [ ] Days 3–4: JWT auth, users table, RBAC (vendor / operations / admin), ownership checks
- [ ] Days 5–6: Document upload, Celery + Redis workers, jobs table and job status API
- [ ] Days 7–8: Retries with backoff, dead-letter queue, idempotency keys
- [ ] Days 9–10: RAG compliance (pgvector + Gemini), CatBoost SLA risk + SHAP, human review queue
- [ ] Day 11: Postgres integration tests, failure tests
- [ ] Day 12: Worker containers, CD
- [ ] Day 13: Metrics, Locust load tests
- [ ] Day 14: React dashboard, architecture diagram, demo
