# Intelligent Vendor Onboarding & Compliance Platform

An asynchronous vendor onboarding platform: registration, duplicate detection, compliance
verification (RAG + LLM), SLA-risk prediction (CatBoost + SHAP), human review and notifications.

**Current phase: 3 – Document upload and background workers** (Days 5–6 of the plan)

## Quick start

```bash
cp backend/.env.example backend/.env
make up                      # Postgres (pgvector), Redis, API, Celery worker; migrations run on start
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

To run the worker outside Docker, start it in a second terminal (Windows needs `--pool=solo`):

```bash
celery -A app.workers.celery_app worker --loglevel=INFO --pool=solo
```

## Services

| Service | Role |
|---|---|
| `api` | FastAPI app. Runs migrations on start, then serves requests |
| `worker` | Celery worker. Picks jobs from Redis and processes documents |
| `db` | PostgreSQL 16 with pgvector |
| `redis` | Message broker between the API and the worker |

`api` and `worker` are the same image started in different modes (`entrypoint.sh api|worker`),
and share the `uploads` volume.

## Roles

| Role | Created by | Can do |
|---|---|---|
| VENDOR | Self-registration (`/auth/register`) | Create one application, upload its documents, track it |
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
| PATCH | `/api/v1/users/{id}` | admin | Change name, role, active flag, or reset password |
| POST | `/api/v1/vendors` | vendor | Submit an application (one per account) |
| GET | `/api/v1/vendors` | any | Staff: all; vendors: only their own |
| GET | `/api/v1/vendors/me` | vendor | The caller's own application |
| GET | `/api/v1/vendors/{id}` | owner or staff | Application details |
| POST | `/api/v1/vendors/{id}/status` | staff | Manual state transition |
| GET | `/api/v1/vendors/{id}/audit-logs` | staff | Decision trail |
| POST | `/api/v1/vendors/{id}/documents` | owner or staff | Upload a PDF/PNG/JPEG; returns **202** with a job |
| GET | `/api/v1/vendors/{id}/documents` | owner or staff | Documents plus `missing_types` |
| GET | `/api/v1/documents/{id}` | owner or staff | Document metadata and processing status |
| GET | `/api/v1/documents/{id}/file` | owner or staff | Download the original file |
| GET | `/api/v1/jobs/{id}` | owner or staff | Poll background job status |
| GET | `/api/v1/jobs` | staff | All jobs, filter e.g. `?status=FAILED` |
| GET | `/health`, `/health/ready` | public | Liveness / readiness (checks DB) |

All errors share one envelope:
`{"error": {"code", "message", "details", "request_id"}}`

## Document flow

```
POST /documents ──► check type (bytes), size, duplicate ──► save file ──► insert document + job ──► commit
       │                                                                                              │
       └──── 202 {document, job: QUEUED} ◄──────────────────────── enqueue job id to Redis ◄─────────┘
                                                                           │
                          Celery worker ◄──────────────────────────────────┘
                              │  lock job row, QUEUED → RUNNING
                              │  read file, verify SHA-256, extract text (pypdf)
                              ▼
                   job SUCCEEDED / FAILED, document PROCESSED / FAILED, audit entry
```

Uploading both GST_CERTIFICATE and BUSINESS_LICENSE moves the application from PENDING to
DOCUMENTS_SUBMITTED automatically. Uploads are locked once review starts.

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
- **The API never waits for processing.** Uploads return 202 with a job id; a Celery worker
  does the slow work, and clients poll `/jobs/{id}`. Job state lives in PostgreSQL, not in Celery,
  so it survives broker restarts and can be queried and audited.
- **Enqueue after commit.** The job is sent to Redis only after the database commit, so a
  worker can never receive a job whose rows don't exist yet. The Celery task id *is* the job id.
- **Safe redelivery.** Tasks are acknowledged only after they finish (`acks_late`), so a worker
  crash puts the message back. The worker locks the job row and only starts from QUEUED, so a
  message delivered twice is processed once (`test_duplicate_delivery_is_a_no_op`).
- **Upload hardening.** File type is detected from the file's first bytes, not from its name or
  Content-Type header. Size is enforced while reading, not trusted from headers. Files are stored
  under generated names, with a path-traversal guard. The same file can't be uploaded twice per
  vendor (unique `vendor_id + sha256`), and the worker re-checks the checksum before processing.
- **No orphaned files.** If the database insert fails after the file is saved, the file is
  deleted. If Redis is down, the API answers 503 quickly and marks the job FAILED.
- **Text extraction.** PDFs use their text layer; PNG/JPEG images are OCR'd with Tesseract
  (bounded by a timeout and a decompression-bomb pixel limit). Corrupt images fail the job. If
  Tesseract isn't installed, images are kept and flagged `needs_ocr` rather than failing. Scanned
  PDFs with no text layer are flagged the same way. OCR is approximate (e.g. `0` read as `O`), so
  compliance checks must not expect exact identifiers from OCR text.
- **One id across processes.** The upload request's `X-Request-ID` is passed into the Celery
  task, so the API logs, worker logs and audit entries for one upload share an id.
- **Versioned schema.** Alembic migrations with deterministic constraint names; CI runs
  `alembic check` to fail the build if models and migrations drift.

## Roadmap

- [x] Days 1–2: FastAPI structure, schema + migrations, REST APIs, validation, state machine, audit log
- [x] Days 3–4: JWT auth, users table, RBAC (vendor / operations / admin), ownership checks
- [x] Days 5–6: Document upload, Celery + Redis workers, jobs table and job status API
- [ ] Days 7–8: Retries with backoff, dead-letter queue, idempotency keys. Known gaps this closes:
      failed jobs are not retried yet; a job whose worker dies mid-task stays RUNNING; a job that
      failed to enqueue is not re-sent automatically
- [ ] Days 9–10: RAG compliance (pgvector + Gemini), CatBoost SLA risk + SHAP, human review queue
- [ ] Day 11: Postgres integration tests, failure tests
- [ ] Day 12: Worker containers, CD
- [ ] Day 13: Metrics, Locust load tests
- [ ] Day 14: React dashboard, architecture diagram, demo
