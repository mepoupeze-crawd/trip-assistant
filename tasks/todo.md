# Build: Luxury Europe Trip Planner — Telegram Bot MVP

## Contracts (Lead-Authored — DO NOT deviate without lead approval)

### C1: Database Schema (PostgreSQL)
```sql
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  telegram_id BIGINT UNIQUE NOT NULL,
  name TEXT,
  email TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE trips (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) NOT NULL,
  origin TEXT NOT NULL,               -- IATA code e.g. "GRU"
  country TEXT NOT NULL,              -- e.g. "Italy"
  dates_or_month TEXT NOT NULL,       -- e.g. "09/2026"
  days INTEGER NOT NULL,
  party_size TEXT NOT NULL,           -- "solo" | "couple"
  budget_per_person_brl INTEGER NOT NULL,
  preferences_json JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE trip_outputs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  trip_id UUID REFERENCES trips(id) UNIQUE NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued', -- queued|running|done|failed
  pdf_url TEXT,
  docx_url TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE recommendations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  trip_id UUID REFERENCES trips(id) NOT NULL,
  city TEXT NOT NULL,
  type TEXT NOT NULL,                 -- hotel|attraction|activity|restaurant|bar
  name TEXT NOT NULL,
  rating DECIMAL(3,1),
  review_count INTEGER,
  price_hint TEXT,
  source_name TEXT NOT NULL,
  source_url TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE payments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  trip_id UUID REFERENCES trips(id) NOT NULL,
  provider TEXT NOT NULL,             -- "stripe" | "mercadopago"
  amount_cents INTEGER NOT NULL,      -- 10000 = R$100
  currency TEXT NOT NULL DEFAULT 'BRL',
  status TEXT NOT NULL DEFAULT 'pending', -- pending|paid|failed|refunded
  external_id TEXT,                   -- provider checkout/payment ID
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### C2: preferences_json schema
```json
{
  "pace": "light | medium | intense",
  "focus": ["food", "culture", "nature"],
  "crowds": "low | medium | high",
  "hotel": "5star | boutique | mixed",
  "restrictions": ["mobility:wheelchair", "diet:vegan"]
}
```

### C3: REST API Contracts

**Error envelope**: All error responses use FastAPI's `{"detail": {"error": "..."}}` format (not flat).
- 404 body: `{"detail": {"error": "trip_not_found"}}`
- 409 body: `{"detail": {"error": "payment_not_confirmed"}}`
- 425 body: `{"detail": {"error": "output_not_ready", "status": "queued|running"}}`
- 400 body: `{"detail": {"error": "invalid_signature"}}`
- 403 body: FastAPI default (missing or wrong X-API-Key)

**POST /api/trips** — Create trip from briefing
- Auth: `X-API-Key: {INTERNAL_API_KEY}` header required
- Request:
```json
{
  "telegram_user_id": 123456789,
  "telegram_name": "João",
  "origin": "GRU",
  "country": "Italy",
  "dates_or_month": "09/2026",
  "days": 10,
  "party_size": "couple",
  "budget_per_person_brl": 30000,
  "preferences": {
    "pace": "medium",
    "focus": ["food", "culture", "nature"],
    "crowds": "high",
    "hotel": "mixed",
    "restrictions": []
  }
}
```
- Response 201: `{ "trip_id": "<uuid>" }`
- Response 422: `{ "error": "validation_error", "details": "<string>" }`

**POST /api/payments/create** — Initiate Stripe checkout
- Auth: `X-API-Key`
- Request: `{ "trip_id": "<uuid>" }`
- Response 200: `{ "payment_url": "<stripe_checkout_url>", "payment_id": "<uuid>", "amount_brl": 100 }`
- Response 404: `{ "error": "trip_not_found" }`

**POST /api/payments/webhook** — Stripe webhook
- Auth: `Stripe-Signature` header (Stripe HMAC)
- Response 200: `{ "received": true }`
- Response 400: `{ "error": "invalid_signature" }`

**POST /api/trips/:id/generate** — Enqueue generation job
- Auth: `X-API-Key`
- Response 202: `{ "trip_id": "<uuid>", "output_id": "<uuid>", "status": "queued" }`
- Response 404: `{ "error": "trip_not_found" }`
- Response 409: `{ "error": "payment_not_confirmed" }`

**GET /api/trips/:id/status** — Poll generation status
- Auth: `X-API-Key`
- Response 200: `{ "trip_id": "<uuid>", "output_id": "<uuid>", "status": "queued|running|done|failed", "error_message": null }`

**GET /api/trips/:id/output** — Get document links
- Auth: `X-API-Key`
- Response 200: `{ "trip_id": "<uuid>", "pdf_url": "<presigned_url>", "docx_url": "<presigned_url>" }`
- Response 404: `{ "error": "output_not_found" }`
- Response 425: `{ "error": "output_not_ready", "status": "queued|running" }`

### C4: Queue Job Format (Celery/Redis)
- Queue name: `"trip_generation"`
- Task name: `"worker.tasks.generate_trip"`
- Payload: `{ "trip_id": "<uuid>", "output_id": "<uuid>" }`
- Retry: 3 attempts, exponential backoff (1s, 5s, 30s)
- On failure: `trip_outputs.status = "failed"`, set `error_message`

### C5: Storage Object Key Convention (S3/R2)
- PDF: `trips/{trip_id}/itinerary.pdf`
- DOCX: `trips/{trip_id}/itinerary.docx`
- URLs: presigned, valid 7 days

### C6: Quality Thresholds (Rules Engine)
- hotel: `rating >= 4.0 AND review_count >= 100`
- attraction/activity: `rating >= 4.0 AND review_count >= 500`
- restaurant/bar: `rating >= 4.2 AND review_count >= 200`
- If < 10 items pass: expand radius → swap city → reduce list (log justification in output)

### C7: Internal Auth
- All bot→API calls: `X-API-Key: {INTERNAL_API_KEY}` in header
- Webhook: Stripe-Signature HMAC verification only
- No user JWT needed for MVP

---

## File Ownership

| Agent | Owns |
|-------|------|
| backend | `src/api/`, `src/bot/`, `src/worker/`, `src/db/`, `src/lib/` |
| architect | `docs/adr/`, `docs/architecture.md` |
| security | `docs/threat-model.md`, reviews backend auth/webhook code |
| qa | `tests/`, CI test steps |
| devops | `Dockerfile`, `docker-compose.yml`, `.github/workflows/`, `infra/` |

---

## Parallel Tasks (no dependencies)

- [ ] @backend: Set up Python monorepo — FastAPI app, SQLAlchemy models, Alembic migrations, bot integration (python-telegram-bot), Celery worker skeleton
- [ ] @architect: Write ADR-001 (Python monorepo vs polyglot), ADR-002 (Celery vs BullMQ), ADR-003 (Stripe vs Mercado Pago), C4 architecture diagram
- [ ] @security: Threat model (Stripe webhook verification, internal API key rotation, bot token security, LGPD/GDPR considerations, Telegram user data handling)
- [ ] @devops: docker-compose (Postgres, Redis, API, Bot, Worker), .env.example, GitHub Actions CI pipeline skeleton

## Sequential Tasks (blocked by parallel tasks)

- [ ] @backend: Implement all REST endpoints with exact contracts from C3 (blocked by: backend skeleton)
- [ ] @backend: Implement Celery worker — Rules Engine + Trip Composer + Document Generator (PDF/DOCX) + S3 upload (blocked by: REST endpoints)
- [ ] @backend: Integrate Stripe webhook + payment flow (blocked by: REST endpoints, security review)
- [ ] @qa: Write API integration tests for all C3 endpoints (blocked by: backend REST endpoints)
- [ ] @qa: Write E2E bot flow test (briefing → payment mock → generation → delivery) (blocked by: full backend implementation)
- [ ] @devops: Production deploy config — Docker build, CI/CD full pipeline, Sentry DSN, secrets management (blocked by: devops skeleton + qa tests green)
- [ ] @security: Review backend auth implementation, webhook signature verification, secrets in env (blocked by: backend REST endpoints)

## Final

- [ ] @tech-lead: Contract diff — verify API curl matches exact C3 contracts
- [ ] @tech-lead: End-to-end validation against acceptance criteria
- [ ] @tech-lead: Cross-review assignments
- [ ] All agents: Record lessons in `tasks/lessons.md`
