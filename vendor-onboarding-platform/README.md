# Intelligent Vendor Onboarding & Compliance Platform

An asynchronous vendor onboarding platform: registration, duplicate detection, compliance
verification (RAG + LLM), SLA-risk prediction (CatBoost + SHAP), human review and notifications.

**Current phase: 2 – Authentication and RBAC** (Days 3–4 of the plan)

## Quick start

```bash
cp backend/.env.example backend/.env
make up                      # Postgres (pgvector), Redis, API; runs migrations on start
make create-admin email=admin@example.com   # or: docker compose exec api python -m app.scripts.create_admin --email admin@example.com
open http://localhost:8000/docs
```

In Swagger, click **Authorize** and log in with the account **email** in the `username` field.
The token is remembered across page reloads.

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

## Roles

| Role | Created by | Can do |
|---|---|---|
| VENDOR | Self-registration (`/auth/register`) | Create one application, view it, move it to DOCUMENTS_SUBMITTED |
| OPERATIONS | Admin | View all applications, make review decisions |
| ADMIN | `create_admin` script or another admin | Everything operations can, plus manage users |

## API (v1)

| Method | Path | Who | Description |
|---|---|---|---|
| POST | `/api/v1/auth/register` | public | Create a vendor account |
| POST | `/api/v1/auth/login` | public | OAuth2 password flow, returns a JWT |
| GET | `/api/v1/auth/me` | any | Current user |
| POST | `/api/v1/users` | admin | Create a user of any role |
| GET | `/api/v1/users` | admin | List users, filter by `role` |
| PATCH | `/api/v1/users/{id}` | admin | Change name, role or active flag |
| POST | `/api/v1/vendors` | vendor | Submit an application (one per account) |
| GET | `/api/v1/vendors` | any | Staff: all; vendors: only their own |
| GET | `/api/v1/vendors/me` | vendor | The caller's own application |
| GET | `/api/v1/vendors/{id}` | owner or staff | Application details |
| POST | `/api/v1/vendors/{id}/status` | owner or staff | State transition (role-restricted) |
| GET | `/api/v1/vendors/{id}/audit-logs` | staff | Decision trail |
| GET | `/health`, `/health/ready` | public | Liveness / readiness (checks DB) |

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
- **Authorization order: 401 → 404 → 403 → 409.** Unauthenticated requests fail first. A vendor
  asking for someone else's application gets 404, not 403, so application IDs are not revealed.
  Then the role is checked, and only then the state machine. Rules live in `app/services/permissions.py`.
- **The database is the source of truth for roles.** The user is reloaded on every request, so
  deactivating an account or changing a role takes effect immediately, and a token that claims a
  different role changes nothing (`test_role_in_token_is_not_trusted`).
- **Hardened login.** Argon2id password hashing; one generic message for unknown email, wrong
  password and inactive account; a dummy hash check when the email doesn't exist so response
  time doesn't reveal which emails are registered; JWT algorithm pinned on decode.
- **No privilege escalation at signup.** Registration schemas forbid unknown fields, so
  `{"role": "ADMIN"}` in a signup is rejected rather than ignored. Admins cannot deactivate or
  demote themselves.
- **Safe secrets.** The app refuses to start outside local/test with the default `SECRET_KEY`.
- **Versioned schema.** Alembic migrations with deterministic constraint names; CI runs
  `alembic check` to fail the build if models and migrations drift.

## Roadmap

- [x] Days 1–2: FastAPI structure, schema + migrations, REST APIs, validation, state machine, audit log
- [x] Days 3–4: JWT auth, users table, RBAC (vendor / operations / admin), ownership checks
- [ ] Days 5–6: Document upload, Celery + Redis workers, jobs table and job status API
- [ ] Days 7–8: Retries with backoff, dead-letter queue, idempotency keys
- [ ] Days 9–10: RAG compliance (pgvector + Gemini), CatBoost SLA risk + SHAP, human review queue
- [ ] Day 11: Postgres integration tests, failure tests
- [ ] Day 12: Worker containers, CD
- [ ] Day 13: Metrics, Locust load tests
- [ ] Day 14: React dashboard, architecture diagram, demo
