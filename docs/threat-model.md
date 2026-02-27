# Threat Model — Luxury Europe Trip Planner Telegram Bot

**Version:** 1.0
**Date:** 2026-02-26
**Author:** Security Agent (Senior Security Engineer, 20+ years)
**Methodology:** STRIDE (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege)
**Scope:** MVP — Python monorepo (FastAPI + python-telegram-bot + Celery), PostgreSQL, Redis, S3/R2, Stripe

---

## System Overview

```
[Telegram User]
     |
     | (Telegram API — TLS)
     v
[Bot Process — python-telegram-bot]
     |
     | X-API-Key (internal auth)
     v
[FastAPI API — src/api/]
     |
     +---> [PostgreSQL DB]
     |
     +---> [Redis / Celery Queue]
     |          |
     |          v
     |     [Worker Process — src/worker/]
     |          |
     |          +---> [External APIs: web scraping / enrichment]
     |          |
     |          +---> [S3 / R2 — PDF/DOCX storage]
     |
     +---> [Stripe API (outbound)] <--- [Stripe Webhooks (inbound)]
```

**Trust boundaries:**
- Telegram API → Bot: external, TLS, bot token auth (Telegram side)
- Bot → Internal API: internal network, X-API-Key
- API → Stripe: external, TLS, Stripe secret key
- Stripe → API (webhook): public internet, HMAC signature
- API → S3/R2: external, TLS, AWS credentials
- API → PostgreSQL: internal network, DATABASE_URL credentials
- API → Redis: internal network, REDIS_URL credentials

**Sensitive assets:**
- User PII: telegram_id, name, email (optional)
- Payment data: external_id (Stripe), amount, status
- Travel briefing: preferences_json with restrictions (mobility, diet)
- Generated documents: PDF/DOCX itineraries (presigned URLs)
- Secrets: INTERNAL_API_KEY, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, TELEGRAM_BOT_TOKEN, DATABASE_URL, AWS credentials

---

## Attack Surface 1: Stripe Webhook Endpoint (POST /api/payments/webhook)

### Data Flow
```
Stripe Cloud --> POST /api/payments/webhook
                 Headers: Stripe-Signature: t=...,v1=...,v0=...
                 Body: raw JSON payload (event object)
```

### STRIDE Analysis

| Threat | Category | Description | Impact | Likelihood |
|--------|----------|-------------|--------|------------|
| Forged webhook events | Spoofing | Attacker sends crafted webhook claiming payment_intent.succeeded to unlock trip generation without paying | CRITICAL — free document generation, revenue loss | Medium (public endpoint, event format is documented) |
| Replay attack | Tampering | Attacker replays a legitimate captured webhook to double-trigger a paid event | HIGH — idempotency bypass, double-credit | Low (requires prior capture) |
| Unsigned payload | Tampering | Request without Stripe-Signature header triggers processing logic | CRITICAL — same as forged event | Medium (scan tools hit webhooks constantly) |
| No event logging | Repudiation | No audit trail for which events were received and processed | MEDIUM — unable to dispute chargebacks or debug payment flows | High (common omission) |
| Webhook secret leakage | Information Disclosure | STRIPE_WEBHOOK_SECRET exposed in logs, error messages, or exception traces | HIGH — enables forged webhooks permanently until rotation | Low (requires log access) |
| Webhook endpoint DoS | Denial of Service | Attacker floods endpoint with malformed requests; if naive, each triggers expensive compute (Stripe lib parse + DB query) | MEDIUM — service degradation | Medium |
| Overprivileged webhook handler | Elevation of Privilege | Webhook processing code has access to admin-level DB operations beyond what event type requires | MEDIUM — blast radius of a successful forge | Low (design risk) |

### Required Controls

**CRITICAL — Block all payments until implemented:**

1. **Stripe signature verification (MUST)**
   - Use `stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)`
   - Do NOT implement manual HMAC comparison — Stripe's SDK handles timestamp tolerance (5 minutes default) and replay protection
   - On `stripe.error.SignatureVerificationError`: return HTTP 400 `{"error": "invalid_signature"}`
   - On missing `Stripe-Signature` header: return HTTP 400 (same response — do not distinguish)
   - NEVER return HTTP 500 on signature failure — this leaks that processing occurred

   ```python
   # CORRECT — use Stripe SDK, not manual hmac
   try:
       event = stripe.Webhook.construct_event(
           payload=raw_body,          # bytes — before JSON parsing
           sig_header=request.headers.get("stripe-signature"),
           secret=settings.stripe_webhook_secret,
       )
   except stripe.error.SignatureVerificationError:
       return JSONResponse(status_code=400, content={"error": "invalid_signature"})
   except Exception:
       return JSONResponse(status_code=400, content={"error": "invalid_payload"})
   ```

   > **IMPORTANT:** FastAPI's request body must be consumed as raw bytes BEFORE any JSON parsing for signature verification. Use `await request.body()` — do not use `request.json()` first.

2. **Idempotency — payment events (MUST)**
   - Before processing any `payment_intent.succeeded` or `checkout.session.completed` event: check if `payments.external_id` already has `status = 'paid'`
   - If already paid: return HTTP 200 `{"received": true}` immediately — do not re-process
   - Use database-level constraint: `payments.external_id` should have a UNIQUE index
   - Log the duplicate event_id with level INFO (not ERROR — duplicates are expected behavior from Stripe)

3. **Audit logging (MUST)**
   - Log every webhook receipt with: `event_id`, `event_type`, `livemode`, timestamp, processing result (accepted/rejected/duplicate)
   - Do NOT log the full event payload (may contain PII or card data)
   - Minimum log entry: `{"event": "webhook_received", "stripe_event_id": "evt_xxx", "type": "checkout.session.completed", "result": "processed"}`

4. **Rate limiting (SHOULD)**
   - Apply rate limiting at the reverse proxy level (nginx/caddy) for `/api/payments/webhook`
   - Stripe IPs: optionally allowlist Stripe's webhook IP ranges (documented at stripe.com/docs/ips) — reduces noise but not a substitute for signature verification

### Verification Checklist (for Backend Code Review)
- [ ] `stripe.Webhook.construct_event` called with `raw_body` (bytes), not parsed JSON
- [ ] `stripe.error.SignatureVerificationError` caught and returns HTTP 400
- [ ] Missing `Stripe-Signature` header returns HTTP 400 (not 500, not 200)
- [ ] Payment status idempotency check before any DB mutation
- [ ] `stripe_event_id` logged on every webhook receipt
- [ ] Webhook secret loaded from `settings.stripe_webhook_secret` (env var), not hardcoded

---

## Attack Surface 2: Internal X-API-Key (Bot -> API)

### Data Flow
```
[Bot Process] --> POST /api/trips
                  Header: X-API-Key: {INTERNAL_API_KEY}
```

### STRIDE Analysis

| Threat | Category | Description | Impact | Likelihood |
|--------|----------|-------------|--------|------------|
| Key in plaintext in logs | Information Disclosure | Logging framework captures full request headers including X-API-Key | HIGH — key compromised, all endpoints exposed | High (default behavior in many frameworks) |
| Key in codebase | Information Disclosure | Hardcoded key or key in committed .env / config file | CRITICAL — permanent exposure in git history | Medium (common mistake) |
| Brute force / enumeration | Spoofing | Attacker attempts to enumerate valid keys; timing side-channel leaks key length or validity | HIGH — full API access | Low (if rate-limited) / Medium (if not) |
| Key rotation complexity | Tampering | No documented rotation procedure; key never rotated after compromise | HIGH — prolonged exposure window | High (ops gap) |
| 401 response leaks auth type | Information Disclosure | HTTP 401 with WWW-Authenticate header reveals auth mechanism | LOW — aids reconnaissance | Medium |
| Weak key (short/predictable) | Spoofing | Default `changeme-secret` or short key used in production | CRITICAL | Medium (config drift) |
| Key shared across environments | Information Disclosure | Same key in staging and production; staging compromise leads to production access | HIGH | Medium |

### Required Controls

1. **Timing-safe comparison (MUST)**
   - Use `secrets.compare_digest(provided_key, expected_key)` — prevents timing side-channel attacks
   - Do NOT use `==` comparison for secrets

   ```python
   import secrets
   from fastapi import Header, HTTPException
   from src.lib.config import settings

   async def verify_api_key(x_api_key: str = Header(alias="X-API-Key")) -> None:
       if not secrets.compare_digest(
           x_api_key.encode("utf-8"),
           settings.internal_api_key.encode("utf-8"),
       ):
           raise HTTPException(status_code=403, detail="Forbidden")
   ```

2. **Return 403, not 401 (MUST)**
   - HTTP 401 conventionally includes `WWW-Authenticate` header, revealing the auth type
   - HTTP 403 on invalid key — do not reveal whether the key is wrong vs. missing vs. malformed
   - Missing header: also return 403 (FastAPI Header dependency raises 422 by default — override to 403)

3. **Key never logged (MUST)**
   - Configure structlog/logging to mask the `X-API-Key` header
   - In any access log or middleware that logs headers, add `X-API-Key` to a sanitized headers list
   - Key must never appear in Sentry breadcrumbs or request context

4. **Key stored in env var only (MUST)**
   - `settings.internal_api_key` sourced from `INTERNAL_API_KEY` env var via Pydantic Settings
   - `.env.example` must have placeholder only: `INTERNAL_API_KEY=changeme-secret`
   - The default `changeme-secret` in `src/lib/config.py` is acceptable for local dev but MUST be overridden in any deployed environment

5. **Minimum key length (SHOULD)**
   - Production key MUST be at least 32 characters, randomly generated
   - Generation command (document in ops runbook): `python -c "import secrets; print(secrets.token_hex(32))"`

6. **Key rotation procedure (MUST document)**

   **Rotation steps (zero-downtime):**
   1. Generate new key: `python -c "import secrets; print(secrets.token_hex(32))"`
   2. Update `INTERNAL_API_KEY` in secret manager / .env for BOTH the API service and the Bot service
   3. Redeploy API service first (accepts new key)
   4. Redeploy Bot service (sends new key)
   5. Verify bot→API calls succeed in logs
   6. If compromise is suspected: immediate rotation; accept brief downtime (bot error messages to users) over continued exposure

   **When to rotate:** compromise suspected, team member offboards, annually as baseline.

7. **Environment separation (SHOULD)**
   - Staging and production MUST use different `INTERNAL_API_KEY` values
   - If a single repo manages multiple environments, ensure env-specific secret injection

### Verification Checklist (for Backend Code Review)
- [ ] `secrets.compare_digest` used in `src/api/deps.py` — not `==`
- [ ] Invalid or missing key returns HTTP 403 (not 401, not 422)
- [ ] `X-API-Key` not present in any log output (access logs, structlog, Sentry)
- [ ] `INTERNAL_API_KEY` loaded only from env var — not hardcoded
- [ ] Production key is >= 32 chars random hex/alphanumeric

---

## Attack Surface 3: Telegram Bot (User Input)

### Data Flow
```
[Telegram User] --message/callback--> [Bot Handlers]
                                          |
                                          +--> Input validation
                                          |
                                          +--> POST /api/trips (validated data only)
```

### STRIDE Analysis

| Threat | Category | Description | Impact | Likelihood |
|--------|----------|-------------|--------|------------|
| SQL injection via user input | Tampering | User input reaches DB without sanitization | HIGH — data breach, DB manipulation | Low (SQLAlchemy ORM mitigates) / Medium (if raw SQL used) |
| Malicious IATA code | Tampering | Input like `"../../../etc"` or SQL fragment in origin field | MEDIUM — depends on how field is used downstream | Medium |
| Country field injection | Tampering | Free-text country bypasses European destination constraint; trip generated for arbitrary location | LOW business risk / MEDIUM for unexpected behavior | Medium |
| PII in logs | Information Disclosure | `telegram_id`, username, or message content logged in plaintext | MEDIUM — LGPD violation; operational data leak | High (common logging pattern) |
| Unbounded input | Denial of Service | Very long preference text or restrictions list causes excessive compute in AI/enrichment | MEDIUM | Low (current MVP; higher risk if LLM added) |
| Rate abuse per user | Denial of Service | Single user creates multiple trips simultaneously, exhausting payment URLs or worker slots | MEDIUM | Medium |
| Future prompt injection (LLM) | Elevation of Privilege | If LLM added to process briefing, user input injected as instruction | CRITICAL (future) | N/A for MVP — note for backlog |

### Required Controls

1. **Input validation — all briefing fields (MUST)**

   | Field | Validation Rule | Rejection Response |
   |-------|----------------|-------------------|
   | `origin` | Regex: `^[A-Z]{3}$` (IATA 3-letter code) | "Invalid airport code. Please use 3-letter IATA format (e.g., GRU)." |
   | `country` | Allowlist: European countries only (see list below) | "We currently serve European destinations only." |
   | `days` | Integer, range 3-30 inclusive | "Trip duration must be between 3 and 30 days." |
   | `budget_per_person_brl` | Integer, positive, min 1000, max 500000 | "Please enter a valid budget amount in BRL." |
   | `party_size` | Enum: `"solo"` or `"couple"` only | "Please select Solo or Couple." |
   | `preferences.pace` | Enum: `"light"`, `"medium"`, `"intense"` | Bot UI enforces via inline keyboard — also validate server-side |
   | `preferences.focus` | Array of allowed strings: `["food", "culture", "nature", "shopping", "nightlife"]` | Strip unknown values; require at least 1 |
   | `preferences.restrictions` | Array of allowed strings with prefix pattern `"mobility:"`, `"diet:"` | Strip unknown prefixes |

   **European countries allowlist (minimum):**
   ```
   Albania, Andorra, Austria, Belgium, Bosnia and Herzegovina, Bulgaria, Croatia,
   Cyprus, Czech Republic, Denmark, Estonia, Finland, France, Germany, Greece,
   Hungary, Iceland, Ireland, Italy, Kosovo, Latvia, Liechtenstein, Lithuania,
   Luxembourg, Malta, Moldova, Monaco, Montenegro, Netherlands, North Macedonia,
   Norway, Poland, Portugal, Romania, San Marino, Serbia, Slovakia, Slovenia,
   Spain, Sweden, Switzerland, Ukraine, United Kingdom, Vatican City
   ```

2. **No raw SQL (MUST)**
   - Verify all DB interactions go through SQLAlchemy ORM
   - `select()`, `insert()`, `update()` with bound parameters — never `text()` with user input concatenation
   - Code review MUST flag any use of `session.execute(text(f"... {user_input} ..."))` as CRITICAL

3. **PII masking in logs (MUST)**
   - Never log `telegram_id` in plaintext in production
   - Masking pattern: `user:****{str(telegram_id)[-4:]}` (last 4 digits only)
   - `telegram_name` (display name): log as `user_name:[redacted]`
   - Structlog processor to strip PII fields:
     ```python
     # Add to structlog processor chain
     def mask_pii(logger, method, event_dict):
         if "telegram_id" in event_dict:
             tid = str(event_dict["telegram_id"])
             event_dict["telegram_id"] = f"****{tid[-4:]}"
         event_dict.pop("telegram_name", None)
         return event_dict
     ```

4. **Rate limiting per telegram_id (SHOULD)**
   - 1 active trip per user at a time: check for existing trip with `status IN ('queued', 'running')` before creating a new one
   - If active trip exists: inform user with status link instead of creating duplicate
   - This also prevents accidental double-submission during bot UX flows

5. **Prompt injection — LLM backlog note (MUST document for future)**
   - MVP has no LLM component; briefing data goes directly to structured data pipeline
   - IF an LLM layer is added (Phase 2): user input MUST NOT be concatenated into system prompts
   - All LLM integration must implement OWASP LLM01 controls: input sanitization, output validation, tool allowlisting, iteration limits
   - Flag: any future PR adding LLM requires security review BEFORE merge

### Verification Checklist (for Backend Code Review)
- [ ] Origin field validated with `^[A-Z]{3}$` regex
- [ ] Country validated against European allowlist (not free-text)
- [ ] Days validated as integer in range [3, 30]
- [ ] Budget validated as positive integer
- [ ] party_size validated as enum (solo|couple)
- [ ] No `session.execute(text(...))` with user-controlled input
- [ ] SQLAlchemy ORM used for all DB queries
- [ ] `telegram_id` masked in all log output (not raw)
- [ ] 1 active trip per user check enforced before new trip creation

---

## Attack Surface 4: S3/R2 Presigned URLs

### Data Flow
```
[Worker] --> S3/R2 upload (trips/{trip_id}/itinerary.pdf)
         <-- presigned URL (7-day expiry)

[API] --> GET /api/trips/:id/output
      <-- { pdf_url: <presigned_url> }

[Bot] --> sends presigned URL to Telegram user
```

### STRIDE Analysis

| Threat | Category | Description | Impact | Likelihood |
|--------|----------|-------------|--------|------------|
| Sequential ID guessing | Information Disclosure | Object key uses sequential ID (e.g., `trips/1234/itinerary.pdf`) — attackers enumerate other users' documents | HIGH — PII in documents (trip plans with personal details) | High (if sequential) |
| Public bucket | Information Disclosure | Bucket configured as public; any object accessible without presigned URL | CRITICAL — all documents exposed | Low (config error) |
| URL sharing / forwarding | Information Disclosure | User shares presigned URL; unintended recipient accesses document | LOW-MEDIUM — by design unavoidable; mitigated by expiry | Medium (user behavior) |
| Expired URL not regenerated | Denial of Service | URLs expire after 7 days; no regeneration path for users who lose the URL | LOW — UX issue, not security | High (workflow gap) |
| SSRF via presigned URL | Server-Side Request Forgery | If API re-fetches presigned URL server-side on behalf of user, SSRF risk | LOW (only if design changes) | Low |
| Bucket policy misconfiguration | Elevation of Privilege | S3 bucket policy allows broader actions (e.g., ListBucket) beyond intended GetObject | MEDIUM — enumerate all document keys | Low-Medium |

### Required Controls

1. **UUID-based object keys (MUST)**
   - Object key pattern: `trips/{trip_id}/itinerary.pdf` where `trip_id` is a UUID v4
   - `trip_id` is set as `gen_random_uuid()` in DB schema (C1 — already correct)
   - UUID is cryptographically unpredictable — guessing probability is negligible (~1/2^122)
   - Never use sequential IDs, telegram_id, or username in object keys

2. **Presigned URL TTL = 7 days (MUST)**
   - `settings.presigned_url_ttl_seconds = 7 * 24 * 3600` — already in config
   - Verify this value is passed to `boto3.generate_presigned_url(ExpiresIn=settings.presigned_url_ttl_seconds)`
   - Do NOT hardcode the TTL in the worker — always use `settings`

3. **Bucket NOT public (MUST)**
   - AWS S3 Block Public Access: enable all four block settings at bucket level
   - Cloudflare R2: disable public bucket access
   - Verify: `aws s3api get-bucket-policy-status --bucket trip-planner-docs` should show `IsPublic: false`

4. **Bucket policy — least privilege (SHOULD)**
   Recommended bucket policy (AWS S3):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "DenyPublicAccess",
         "Effect": "Deny",
         "Principal": "*",
         "Action": "s3:GetObject",
         "Resource": "arn:aws:s3:::trip-planner-docs/*",
         "Condition": {
           "StringNotEquals": {
             "s3:authType": "REST-QUERY-STRING"
           }
         }
       }
     ]
   }
   ```
   This denies direct GetObject access (requires presigned URL query string auth).

5. **IAM/R2 least privilege for worker (SHOULD)**
   - Worker IAM role/API token: allow only `s3:PutObject` and `s3:GetObject` on `arn:aws:s3:::trip-planner-docs/trips/*`
   - Deny `s3:ListBucket`, `s3:DeleteObject`, `s3:PutBucketPolicy`
   - API service (if it generates presigned URLs): allow `s3:GetObject` only

6. **No ListBucket permission (SHOULD)**
   - Without ListBucket, even a compromised key cannot enumerate all object keys
   - Verify IAM policy has no `s3:ListBucket` action for application roles

### Verification Checklist (for DevOps/Backend Code Review)
- [ ] Object key uses `trip_id` (UUID), not sequential ID or telegram_id
- [ ] `presigned_url_ttl_seconds` = 604800 (7 * 24 * 3600) passed to boto3
- [ ] Bucket Block Public Access enabled (verified via AWS console or CLI)
- [ ] Application IAM role/token has no `s3:ListBucket` permission
- [ ] Presigned URL generation uses `settings.presigned_url_ttl_seconds` (not hardcoded)

---

## Attack Surface 5: Database (PostgreSQL)

### Data Flow
```
[API/Worker] --> SQLAlchemy ORM --> PostgreSQL
                                    - users table (telegram_id, name, email)
                                    - trips table (preferences_json)
                                    - payments table (external_id, status, amount)
                                    - trip_outputs table (pdf_url, docx_url)
                                    - recommendations table
```

### STRIDE Analysis

| Threat | Category | Description | Impact | Likelihood |
|--------|----------|-------------|--------|------------|
| SQL injection | Tampering | Raw SQL with user input concatenation bypasses ORM | CRITICAL — full DB read/write | Low (ORM in use) / High (if raw SQL added) |
| DATABASE_URL in code | Information Disclosure | Connection string with credentials committed to repo | CRITICAL — full DB access | Medium (common mistake) |
| Overprivileged DB user | Elevation of Privilege | App DB user has CREATE/DROP/GRANT privileges; SQL injection escalates to schema destruction | HIGH | Medium (default postgres superuser) |
| Payment card data storage | Information Disclosure | Card numbers, CVVs, or full card data stored in payments table | CRITICAL — PCI DSS violation, LGPD violation | Low (Stripe handles it) — verify |
| Unencrypted sensitive fields | Information Disclosure | preferences_json with disability/dietary data stored in plaintext | MEDIUM — LGPD sensitive category data | Medium |
| DB connection string in logs | Information Disclosure | Alembic or SQLAlchemy logs connection URL on startup | MEDIUM — credentials in log files | Medium |
| No connection pool limits | Denial of Service | Unconstrained connections exhaust DB server | MEDIUM | Medium (ops gap) |

### Required Controls

1. **SQLAlchemy ORM only — no raw SQL with user input (MUST)**
   - All queries via SQLAlchemy `select()`, `insert()`, `update()`, `delete()` with bound parameters
   - If `text()` is needed (rare migration scenarios): ONLY with hardcoded SQL, never with user-controlled input
   - Code review gate: any `text(f"... {variable} ...")` pattern = automatic rejection

2. **DATABASE_URL in env var only (MUST)**
   - Loaded via `settings.database_url` from `DATABASE_URL` env var
   - `.env.example` has placeholder: `DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/tripplanner`
   - NEVER commit a `.env` file with real credentials
   - CRITICAL GAP: `.gitignore` is ABSENT from this repository (see Critical Issues section)

3. **DB user least privilege (MUST — DevOps task)**
   - Application DB user should have: `SELECT, INSERT, UPDATE, DELETE` on application tables only
   - No `CREATE TABLE`, `DROP TABLE`, `ALTER TABLE`, `CREATE INDEX` in runtime credentials
   - Alembic migrations run with a SEPARATE migration user that has DDL privileges
   - SQL to create least-privilege app user:
     ```sql
     CREATE USER tripplanner_app WITH PASSWORD '<strong-password>';
     GRANT CONNECT ON DATABASE tripplanner TO tripplanner_app;
     GRANT USAGE ON SCHEMA public TO tripplanner_app;
     GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO tripplanner_app;
     GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO tripplanner_app;
     ```

4. **No payment card data stored (MUST — verify)**
   - `payments` table schema (C1) stores only: `provider`, `amount_cents`, `currency`, `status`, `external_id`
   - `external_id` = Stripe checkout session ID or payment intent ID (e.g., `cs_live_xxx`) — NOT card data
   - This is correct and PCI-compliant: Stripe is the cardholder data environment, not this application
   - Code review MUST verify no card-related fields are added to the payments table

5. **preferences_json sensitivity (SHOULD review)**
   - `preferences.restrictions` may contain `"mobility:wheelchair"` or `"diet:vegan"` — potentially LGPD special category data (health-related)
   - MVP: store as-is in JSONB (acceptable with proper DB access controls)
   - Phase 2: consider field-level encryption for restrictions field if health data classification confirmed

6. **Connection string not logged (MUST)**
   - Disable SQLAlchemy connection URL logging: `logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)`
   - Set Alembic logging level to suppress connection URL output in CI/CD logs

### Verification Checklist (for Backend/DevOps Code Review)
- [ ] No `session.execute(text(f"..."))` with user-controlled input in any file
- [ ] `DATABASE_URL` loaded only from env var — not hardcoded
- [ ] App DB user has CRUD only (no DDL privileges) — separate migration user
- [ ] `payments` table has NO card number, CVV, or cardholder name fields
- [ ] SQLAlchemy engine logging suppressed (no connection URL in output)
- [ ] `.gitignore` present and includes `.env` (CRITICAL GAP — see below)

---

## Attack Surface 6: User Data (LGPD Compliance)

### Data Collected
| Data | Table | Classification | Basis |
|------|-------|---------------|-------|
| `telegram_id` | users | Identifier (pseudonymous) | Contract performance |
| `name` | users | PII (optional) | Contract performance |
| `email` | users | PII (optional) | Contract performance |
| `preferences_json` | trips | Behavioral / potentially sensitive (mobility, diet) | Contract performance |
| `status`, `amount` | payments | Financial transaction data | Contract performance |
| `pdf_url`, `docx_url` | trip_outputs | Document access URLs | Contract performance |

### STRIDE Analysis

| Threat | Category | Description | Impact | Likelihood |
|--------|----------|-------------|--------|------------|
| No privacy notice | Information Disclosure | Users unaware their data is stored; LGPD violation (Art. 8) | MEDIUM — regulatory risk | High (MVP gap) |
| No deletion mechanism | Elevation of Privilege (user) | Users cannot exercise LGPD right to deletion (Art. 18) | MEDIUM — regulatory risk | High (not in MVP scope) |
| PII in error messages | Information Disclosure | `telegram_id` or name in exception sent to user or Sentry | MEDIUM — data exposure | Medium |
| PII in Sentry (stack traces) | Information Disclosure | Exception context includes user PII captured automatically by Sentry SDK | MEDIUM — PII in third-party system | High (Sentry default behavior) |
| Data retention undefined | Information Disclosure | Data retained indefinitely; LGPD requires defined retention period | MEDIUM — regulatory risk | High (MVP gap) |
| Telegram name stored without consent | Information Disclosure | `name` column stores Telegram display name without explicit user consent | LOW-MEDIUM | Medium |

### Required Controls

1. **Privacy notice in /start command (MUST)**
   - Bot /start message MUST include data transparency notice:
     ```
     Before we begin, a quick note on privacy:

     We store your trip preferences and payment status to generate your personalized itinerary.
     Your data is used only for trip generation and is not shared with third parties beyond Stripe (payment processing).

     By continuing, you agree to these terms.
     ```
   - This provides the LGPD transparency obligation (Art. 9) and records user continuation as implicit consent for contract performance

2. **Data deletion — /delete command (SHOULD — Phase 2 backlog)**
   - LGPD Art. 18 grants right to deletion of data processed based on consent
   - Phase 2 implementation: `/delete` command triggers `DELETE FROM users WHERE telegram_id = ?` cascade
   - Until implemented: provide a contact method (email) for deletion requests in /start message
   - Backlog item: implement /delete with cascade soft-delete across users, trips, payments tables

3. **Sentry PII scrubbing (MUST)**
   - Configure Sentry SDK `before_send` hook to strip PII before transmission:
     ```python
     import sentry_sdk
     from sentry_sdk.scrubber import EventScrubber, DEFAULT_DENYLIST

     def before_send(event, hint):
         # Strip request data that may contain X-API-Key or user data
         if "request" in event:
             event["request"].pop("data", None)
             if "headers" in event["request"]:
                 event["request"]["headers"].pop("x-api-key", None)
                 event["request"]["headers"].pop("X-API-Key", None)
         return event

     sentry_sdk.init(
         dsn=settings.sentry_dsn,
         before_send=before_send,
         send_default_pii=False,   # MUST be False
     )
     ```
   - `send_default_pii=False` prevents Sentry from automatically capturing user IDs and IP addresses

4. **No PII in user-facing error messages (MUST)**
   - Error responses to users: generic messages only ("An error occurred. Please try again.")
   - Internal error details: structured logs (server-side) with masked PII — not in API responses

5. **Data retention policy (SHOULD — document)**
   - Define retention period: recommendation is 2 years from trip creation date
   - Phase 2: implement automated cleanup job for expired records
   - Document retention decision as accepted risk in MEMORY.md

### Verification Checklist (for Backend/Bot Code Review)
- [ ] /start command includes privacy notice with data transparency statement
- [ ] `sentry_sdk.init` called with `send_default_pii=False`
- [ ] `before_send` hook configured to strip `X-API-Key` and request data
- [ ] Error responses to Telegram users contain no PII or stack traces
- [ ] Data deletion contact method mentioned in /start (until /delete command implemented)

---

## Attack Surface 7: Secrets Management

### Secrets Inventory
| Secret | Location | Used By |
|--------|----------|---------|
| `INTERNAL_API_KEY` | Env var | Bot (sends), API (verifies) |
| `TELEGRAM_BOT_TOKEN` | Env var | Bot |
| `STRIPE_SECRET_KEY` | Env var | API (payments) |
| `STRIPE_WEBHOOK_SECRET` | Env var | API (webhook verification) |
| `DATABASE_URL` | Env var | API, Worker |
| `REDIS_URL` | Env var | API, Worker |
| `AWS_ACCESS_KEY_ID` | Env var | Worker |
| `AWS_SECRET_ACCESS_KEY` | Env var | Worker |
| `SENTRY_DSN` | Env var | API, Bot, Worker |

### STRIDE Analysis

| Threat | Category | Description | Impact | Likelihood |
|--------|----------|-------------|--------|------------|
| `.env` committed to git | Information Disclosure | Actual `.env` file with real keys pushed to repository | CRITICAL — all secrets exposed | High (CRITICAL GAP: no .gitignore) |
| Secrets in Docker image layers | Information Disclosure | `ARG` or `ENV` in Dockerfile bakes secrets into image layer; visible with `docker history` | HIGH — image registry exposure | Medium |
| Secrets in CI/CD logs | Information Disclosure | CI runner echoes env var values in build logs | HIGH | Medium |
| `SENTRY_DSN` logged | Information Disclosure | Sentry DSN logged on startup; DSN has write access to error project | LOW-MEDIUM | Medium |
| Default `changeme-secret` in production | Spoofing | Default `INTERNAL_API_KEY` value used in deployed environment | CRITICAL | Medium (config drift) |
| No secret rotation process | Elevation of Privilege | Compromised secret has indefinite validity | HIGH | High (no process defined) |
| Secrets in `docker-compose.yml` | Information Disclosure | Hardcoded values in docker-compose env section committed to repo | HIGH | Medium |

### Required Controls

1. **`.gitignore` MUST include `.env` (CRITICAL — BLOCKER)**

   **CRITICAL GAP IDENTIFIED:** `.gitignore` does NOT exist in this repository.

   Create `.gitignore` immediately (DevOps task — BLOCKER before any real secrets are added):
   ```
   # Secrets and environment
   .env
   .env.local
   .env.production
   .env.staging
   *.key
   *.pem

   # Python
   __pycache__/
   *.py[cod]
   .venv/
   venv/
   dist/
   build/
   *.egg-info/

   # IDE
   .idea/
   .vscode/
   *.swp

   # OS
   .DS_Store
   Thumbs.db

   # Logs
   *.log
   logs/
   ```

2. **`.env.example` has placeholder values only (MUST — verify)**
   - Current `.env.example` uses placeholders: `changeme-secret`, `your_bot_token`, `sk_test_...`, `whsec_...`, `...` — CORRECT
   - The `SENTRY_DSN=https://...@sentry.io/...` is a placeholder — CORRECT
   - Do NOT put real DSNs or partial real keys in `.env.example`

3. **Docker: runtime env injection, not ARG baking (MUST)**
   - Dockerfile MUST NOT use `ARG STRIPE_SECRET_KEY` followed by `ENV STRIPE_SECRET_KEY=$STRIPE_SECRET_KEY`
   - Correct pattern: env vars injected at runtime via `docker-compose.yml` `env_file: .env` or orchestrator secrets
   - Acceptable `docker-compose.yml` pattern:
     ```yaml
     services:
       api:
         image: trip-planner:latest
         env_file: .env     # reads from .env at runtime, NOT at build time
     ```
   - Verify: `docker history trip-planner:latest` should show no secret values in any layer

4. **Sentry DSN is a secret (MUST)**
   - `SENTRY_DSN` is a write-access token; treat it as a secret
   - Do NOT log `sentry_dsn` value on startup
   - If logging Sentry initialization: log only `"sentry_enabled": True` — not the DSN value

5. **docker-compose.yml has no hardcoded secrets (MUST)**
   - Use `env_file: .env` or `environment: - VARIABLE_NAME` (value from shell env) — never `environment: - KEY=actual_secret_value`

6. **Secret rotation procedure (MUST document)**
   - See rotation procedure documented under Attack Surface 2 (X-API-Key)
   - For Stripe secrets: rotate via Stripe dashboard; requires webhook secret update + API service restart
   - For Telegram bot token: regenerate via BotFather; requires bot service restart
   - For AWS credentials: rotate via IAM; requires worker service restart
   - After any suspected compromise: rotate ALL secrets, not just the suspected one

### Verification Checklist (for DevOps Code Review)
- [ ] `.gitignore` EXISTS and includes `.env` (BLOCKER)
- [ ] No `ARG` with secret names in Dockerfile
- [ ] `docker-compose.yml` uses `env_file` or env var references, not hardcoded values
- [ ] Sentry DSN not logged in startup messages
- [ ] `INTERNAL_API_KEY` default (`changeme-secret`) NOT present in any deployed environment
- [ ] `.env.example` has NO real keys, tokens, or DSN values

---

## Severity Priority Table — MVP

| Control | Surface | Severity | Phase | Owner | Status |
|---------|---------|---------|-------|-------|--------|
| Create `.gitignore` with `.env` | Secrets | **CRITICAL BLOCKER** | Now (before any commit with real secrets) | DevOps | MISSING |
| Stripe webhook signature verification | Webhook | **CRITICAL** | Before any payment processed | Backend | Not yet implemented |
| `secrets.compare_digest` for X-API-Key | Internal Auth | **HIGH** | MVP | Backend | Not yet implemented |
| Return 403 on bad key, 400 on bad webhook | Internal Auth / Webhook | **HIGH** | MVP | Backend | Not yet implemented |
| User input validation (IATA, country, ranges) | Bot Input | **HIGH** | MVP | Backend/Bot | Not yet implemented |
| Webhook idempotency check | Webhook | **HIGH** | Before any payment processed | Backend | Not yet implemented |
| Audit log: webhook event_id on receipt | Webhook | **HIGH** | MVP | Backend | Not yet implemented |
| PII masking in logs (telegram_id) | Logging | **HIGH** | MVP | Backend | Not yet implemented |
| Sentry `send_default_pii=False` + before_send | Observability | **HIGH** | MVP | Backend | Not yet implemented |
| Presigned URL expiry = 7 days | Storage | **MEDIUM** | MVP | Backend/Worker | Configured in settings |
| UUID object keys in S3 | Storage | **MEDIUM** | MVP | Backend | Correct per C5 |
| Bucket NOT public | Storage | **MEDIUM** | MVP | DevOps | Needs verification |
| DB user least privilege (no DDL) | Database | **MEDIUM** | MVP | DevOps | Not verified |
| payments table: no card data | Database | **MEDIUM** | MVP | Backend | Correct per schema C1 |
| LGPD privacy notice in /start | Privacy | **LOW** | MVP | Backend/Bot | Not implemented |
| LGPD /delete command | Privacy | **LOW** | Phase 2 | Backend | Backlog |
| S3 deny policy for non-presigned access | Storage | **LOW** | Phase 2 | DevOps | Backlog |
| Rate limiting per telegram_id | Bot | **LOW** | MVP | Backend | Not implemented |
| Key length >= 32 chars (production) | Secrets | **MEDIUM** | Before production | DevOps/Ops | Operational |
| Data retention policy defined | Privacy | **LOW** | Phase 2 | PM + Backend | Backlog |

---

## Backend Agent Security Checklist (Self-Review Before PR)

```
Authentication & Authorization
[ ] stripe.Webhook.construct_event used (NOT manual HMAC comparison)
[ ] X-API-Key compared with secrets.compare_digest (NOT ==)
[ ] Invalid/missing X-API-Key returns HTTP 403 (not 401, not 422)
[ ] Invalid/missing Stripe-Signature returns HTTP 400 (not 500, not 200)
[ ] Webhook processing checks idempotency before any DB mutation

Secrets
[ ] No secrets in code — all in settings.* loaded from env vars
[ ] INTERNAL_API_KEY never appears in logs, Sentry, or error responses
[ ] stripe.webhook_secret never appears in logs or error responses
[ ] Sentry init: send_default_pii=False

Input Validation (Bot)
[ ] origin validated: regex ^[A-Z]{3}$
[ ] country validated: European countries allowlist
[ ] days validated: integer, 3-30 inclusive
[ ] budget_per_person_brl validated: positive integer, reasonable range
[ ] party_size validated: enum (solo|couple only)
[ ] preferences fields validated against allowed enums/prefixes

Database
[ ] SQLAlchemy ORM used everywhere — NO raw SQL with user input
[ ] No session.execute(text(f"...{user_var}...")) pattern anywhere
[ ] payments table: NO card number, CVV, or cardholder fields
[ ] DATABASE_URL loaded only from env var — not in code

Storage
[ ] Presigned URL TTL = settings.presigned_url_ttl_seconds (7 days)
[ ] Object key uses trip_id (UUID), not sequential ID

Logging & Observability
[ ] telegram_id masked in all log output: ****{last4}
[ ] telegram_name not logged in production
[ ] X-API-Key not logged in access logs or middleware
[ ] Sentry before_send strips X-API-Key and request data

Privacy (LGPD)
[ ] /start command includes data transparency notice
[ ] Error responses to Telegram users contain NO PII or stack traces
[ ] Data deletion contact method in /start message

Infrastructure (flag for DevOps)
[ ] .gitignore exists and includes .env (BLOCKER — verify before first real-secret commit)
[ ] Dockerfile has no ARG/ENV baking secrets
[ ] docker-compose.yml has no hardcoded secret values
```

---

## Critical Issues — Must Address Before First Real Payment

### CRITICAL-1: Missing `.gitignore` (BLOCKER)

**Finding:** No `.gitignore` file exists in the repository.

**Risk:** If a developer creates a real `.env` file with production secrets (STRIPE_SECRET_KEY, TELEGRAM_BOT_TOKEN, AWS_SECRET_ACCESS_KEY) and runs `git add .` or `git commit -a`, ALL secrets will be committed to git history. Git history is permanent — even after removal, the secret must be considered compromised.

**Action required:** DevOps agent MUST create `.gitignore` with `.env` included IMMEDIATELY — before any team member adds real secrets to their local environment.

**Escalation:** If this is not resolved before the backend agent runs any real Stripe or Telegram credentials locally, all those credentials must be rotated after adding `.gitignore`.

---

### CRITICAL-2: Stripe Webhook Verification Not Implemented

**Finding:** `src/api/routers/payments.py` does not exist yet. The webhook endpoint must implement `stripe.Webhook.construct_event` from day one.

**Risk:** Without signature verification, any attacker can POST a fake `checkout.session.completed` event and unlock trip generation without paying.

**Action required:** Backend agent MUST implement signature verification as the FIRST thing in the webhook handler — before any business logic. No partial implementation acceptable.

---

### HIGH-1: `secrets.compare_digest` Not Verified in Auth Dependency

**Finding:** `src/api/deps.py` does not exist yet. When implementing X-API-Key auth, timing-safe comparison is required.

**Risk:** Timing side-channel could theoretically leak key validity information in a low-latency environment. More practically: any `==` comparison is bad practice for secret comparison and violates security baseline.

**Action required:** Backend agent MUST use `secrets.compare_digest` in `src/api/deps.py` — not `==`.

---

### HIGH-2: `.env.example` — `INTERNAL_API_KEY=changeme-secret` Needs Stronger Guidance

**Finding:** The placeholder `changeme-secret` is only 16 characters and could be used literally in a development environment that later becomes production.

**Recommendation:** Add a comment in `.env.example`:
```
# PRODUCTION: Generate with: python -c "import secrets; print(secrets.token_hex(32))"
# MINIMUM 32 chars required in any deployed environment
INTERNAL_API_KEY=changeme-secret-REPLACE-WITH-32-CHAR-RANDOM-VALUE
```

---

## ADR — Security Decisions for This Build

### ADR-SEC-001: X-API-Key over JWT for Internal Auth

**Decision:** Use pre-shared X-API-Key (single key, env var, secrets.compare_digest) for bot→API auth.
**Rationale:** MVP has a single bot client; JWT adds key management overhead (signing keys, token refresh) without meaningful security improvement in a single-client scenario.
**Accepted risks:** No per-request token expiry; key compromise = full API access until rotation.
**Review trigger:** If multiple bots or external clients need API access — upgrade to JWT with client credentials grant.

### ADR-SEC-002: Stripe SDK for Webhook Verification (not manual HMAC)

**Decision:** Use `stripe.Webhook.construct_event` exclusively — no manual HMAC implementation.
**Rationale:** Stripe SDK includes replay protection (5-minute timestamp tolerance), correct encoding, and version-aware signature schemes (v1 preferred over v0). Manual HMAC is error-prone and a common source of bypass vulnerabilities.
**Constraint:** Raw request body must be passed as bytes, before any JSON parsing.

### ADR-SEC-003: LGPD Phase 1 — Contract Performance Basis

**Decision:** Store user data (telegram_id, preferences, payment status) under LGPD Art. 7, VI (contract performance) rather than consent.
**Rationale:** Data is strictly necessary to deliver the paid service (trip itinerary). Consent adds complexity (withdrawal mechanism) that is disproportionate for MVP.
**Constraint:** Data must be limited to what is strictly necessary for trip generation. No marketing use without separate consent.
**Review trigger:** If user data is used for analytics, recommendation improvement, or marketing — consent basis required with full LGPD mechanism.

---

## References

- [OWASP Top 10:2025](https://owasp.org/Top10/)
- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)
- [STRIDE Threat Model](https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats)
- [Stripe Webhook Security](https://stripe.com/docs/webhooks/signatures)
- [Python `secrets` module](https://docs.python.org/3/library/secrets.html)
- [LGPD — Lei Geral de Proteção de Dados (Lei 13.709/2018)](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm)
- [Sentry PII Scrubbing](https://docs.sentry.io/platforms/python/data-management/sensitive-data/)
- [S3 Presigned URLs — AWS Docs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)
