# Luxury Europe Trip Planner 🗺️

A Telegram bot that turns a 5-minute briefing into a complete, curated Europe travel itinerary — delivered as a PDF and Word document.

> **We plan. You travel.**
> No reservations, no upsells — just an honest, ready-to-execute trip plan built on real data.

---

## What it does

Answer a few questions on Telegram, pay once, and receive a full travel plan:

- **City breakdown** — which cities to visit and how many days in each
- **Hotels** — 5-star and boutique picks, with budget-friendly nights when needed
- **Attractions & activities** — curated, not "top 10 tourist traps"
- **Restaurants & bars** — quality-filtered by rating and number of real reviews
- **Logistics** — flights, trains, transfers, rest days, and travel margins
- **Daily schedule** — morning / afternoon / evening table, day by day

Everything delivered as a **PDF + Word (.docx)** file you can share, print, or annotate.

---

## How to use the bot

1. **Open Telegram** and find the bot
2. **Type `/start`** — the bot will walk you through a short briefing (~5 min):
   - Departure city or airport (e.g. São Paulo / GRU)
   - Travelling solo or as a couple?
   - Which European country?
   - How many days, and which month/year?
   - Budget per person (in BRL)?
   - Your travel pace, priorities, and any restrictions
3. **Review the summary** — confirm or start over
4. **Complete payment** — R$100 via credit card
5. **Receive your plan** — PDF + DOCX delivered directly in the chat

Type `/check` at any time after payment to check if your plan is ready.

---

## What we don't do

- We **do not make reservations** — all links and sources are included so you book directly
- We **do not guarantee prices** — figures are estimates for planning purposes
- We cover **one country per trip** in this version (multi-country coming later)
- We deliver **one final itinerary** — no A/B/C variations or decision fatigue

---

## Quality promise

Every hotel, restaurant, attraction, and activity goes through an automatic quality filter before it enters your plan:

| Category | Minimum rating | Minimum reviews |
|----------|---------------|-----------------|
| Hotels | ≥ 4.0 ⭐ | ≥ 100 |
| Attractions & activities | ≥ 4.0 ⭐ | ≥ 500 |
| Restaurants & bars | ≥ 4.2 ⭐ | ≥ 200 |

**If a city doesn't have enough qualifying options**, the system expands the search or adjusts the city selection — and tells you in the plan. It never silently lowers the bar.

**If your budget is tight**, the plan substitutes 1–2 nights with a comfortable mid-range hotel instead of cutting your must-see experiences — and explains the trade-off.

Every recommendation includes its source, rating, and review count so you can verify before booking.

---

## Supported countries (Europe, MVP)

Austria · Belgium · Bulgaria · Croatia · Czech Republic · Denmark · Estonia · Finland · France · Germany · Greece · Hungary · Iceland · Ireland · Italy · Latvia · Lithuania · Netherlands · Norway · Poland · Portugal · Romania · Scotland · Slovakia · Slovenia · Spain · Sweden · Switzerland · United Kingdom

---

## Pricing

| | |
|--|--|
| Price per itinerary | **R$100** |
| Payment | Credit card via Stripe |
| Delivery time | A few minutes after payment |
| Format | PDF + Word (.docx) |

---

## FAQ

**Can I request changes after receiving my plan?**
Not in this version. The plan is generated once, based on your briefing. Make sure to review the summary carefully before confirming.

**What if the bot doesn't respond?**
Type `/start` to restart. If the problem persists, contact support with your Telegram username.

**I paid but haven't received my plan yet.**
Type `/check` in the bot chat. If it still shows "in progress" after 10 minutes, contact support.

**Can I get a refund?**
Refund policy is available via the support contact below.

**Do you store my data?**
We store your trip preferences and payment status to generate and deliver your plan. We do not store payment card details — payments are processed by Stripe. See our privacy notice in the bot's `/start` message.

---

## For developers and operators

### Stack

| Layer | Technology |
|-------|-----------|
| Bot | Python · python-telegram-bot v20 |
| API | FastAPI (async) |
| Queue | Celery + Redis |
| Database | PostgreSQL (SQLAlchemy 2.0 + Alembic) |
| Storage | S3-compatible (Cloudflare R2 or AWS S3) |
| Payments | Stripe Checkout |
| PDF generation | ReportLab |
| DOCX generation | python-docx |
| Observability | Sentry + structlog |
| CI/CD | GitHub Actions |

### Architecture overview

```
User (Telegram)
      │
      ▼
  Telegram Bot  ──── HTTP (X-API-Key) ────────► FastAPI
  (briefing +                                        │
   /check cmd)   ◄──── PDF + DOCX links ─────────────┤
                                                      │
            Stripe Webhook ───────────────────────────┤
                                                      ▼
                                               Celery Worker
                                                      │
                                          Rules Engine + Composer
                                          PDF / DOCX Generator
                                                      │
                                               S3 / R2 Storage
```

Three processes share one Python codebase: `api`, `bot`, `worker`.

### Running locally

```bash
# 1. Copy and fill in credentials
cp .env.example .env

# 2. Start all services (Postgres, Redis, API, Bot, Worker)
docker-compose up migrate   # run DB migrations once
docker-compose up           # start everything

# 3. Run the test suite
pip install -e ".[dev]"
pytest tests/ -v
```

### Environment variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL async connection string |
| `REDIS_URL` | Redis connection string |
| `INTERNAL_API_KEY` | Shared secret between bot and API (min 32 chars) |
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `STRIPE_SECRET_KEY` | Stripe API key |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `AWS_ACCESS_KEY_ID` | S3 / R2 access key |
| `AWS_SECRET_ACCESS_KEY` | S3 / R2 secret key |
| `AWS_BUCKET_NAME` | Bucket for PDF/DOCX files |
| `AWS_ENDPOINT_URL` | R2 endpoint URL (omit for standard AWS S3) |
| `API_BASE_URL` | Internal API base URL (default: `http://api:8000`) |
| `SENTRY_DSN` | Sentry DSN for error tracking |

### First deploy checklist

- [ ] Set all environment variables in your hosting platform
- [ ] Run migrations before starting the API: `docker-compose up migrate`
- [ ] Register Stripe webhook endpoint: `POST /api/payments/webhook`
- [ ] Set `STRIPE_WEBHOOK_SECRET` from Stripe dashboard
- [ ] Confirm `GET /health` returns `{"status": "ok"}` before routing traffic
- [ ] Set Telegram webhook or run in polling mode (polling is default)

### Project structure

```
src/
├── api/           FastAPI app, all 6 endpoints, auth middleware
├── bot/           Telegram bot, 12-step briefing flow, /check delivery
├── worker/        Celery worker, rules engine, trip composer, doc generator, S3
├── db/            SQLAlchemy models (5 tables), Alembic migrations
└── lib/           Shared Pydantic config

tests/
├── unit/          Rules engine, trip composer, document generator
├── integration/   All API endpoints + auth enforcement
└── e2e/           Full briefing → payment → generation → delivery flow

docs/
├── adr/           Architecture Decision Records
├── architecture.md   C4 diagram + flow diagrams
└── threat-model.md   STRIDE threat model, security controls
```

### Security notes

- Stripe webhook signature verified with HMAC-SHA256 via `stripe.Webhook.construct_event`
- Internal API key uses constant-time comparison (`hmac.compare_digest`) to prevent timing attacks
- No card data stored — only Stripe's external session ID
- Generated documents accessed via presigned S3 URLs (expire after 7 days); bucket is private
- Sentry configured with `send_default_pii=False`
- Full threat model: [`docs/threat-model.md`](docs/threat-model.md)

### Architecture decisions

| Decision | Rationale |
|----------|-----------|
| Pure Python monorepo | PDF/DOCX generation requires Python — avoiding a polyglot stack simplifies operations |
| Celery over BullMQ | Same runtime as the document generator; avoids a Node.js process just for the queue |
| Stripe for MVP | Better developer experience and webhook reliability; MercadoPago in Phase 2 |
| No LLM in MVP | Deterministic rules engine eliminates hallucination risk; LLM integration is Phase 2 with eval loops |

Full ADRs in [`docs/adr/`](docs/adr/).

---

## Roadmap

- [ ] MercadoPago / PIX payment (for Brazilian users)
- [ ] Multi-country itineraries
- [ ] Web viewer for the generated plan
- [ ] User data deletion command (LGPD compliance)
- [ ] LLM-assisted curation with eval loops and guardrails
- [ ] Real-time flight data via Amadeus or Skyscanner API

---

## Support

For issues with your plan or payment, contact support through [your support channel here].
