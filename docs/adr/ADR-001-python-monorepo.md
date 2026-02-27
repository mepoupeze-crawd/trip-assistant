## ADR-001: Python Monorepo — FastAPI + python-telegram-bot + Celery

**Status:** Accepted
**Date:** 2026-02-26
**Deciders:** Tech Lead, Architect

---

### Context

The original plan acknowledged two viable implementation paths:

1. **Node.js bot (Telegraf) + Python API via HTTP** — leverage the mature Telegraf ecosystem for Telegram bot development while using Python's document generation libraries (ReportLab, python-docx) in a separate service.
2. **Pure Python monorepo** — one runtime, one repo, Python for everything.

The core constraint driving this decision is the document generation requirement. ReportLab (PDF) and python-docx (DOCX) are Python libraries with no mature equivalents in Node.js that match their typesetting quality and customization capability for rich, print-ready travel itinerary documents. Any polyglot approach forces cross-process or cross-service communication between the bot layer and the document generator.

The team is small (MVP context), the domain is still being defined, and operational simplicity has been established as a priority constraint.

### Architecture Characteristics Affected

| Characteristic | Impact |
|---|---|
| **Deployability** | Single runtime = single Dockerfile base image, fewer moving parts |
| **Maintainability** | Shared models and schemas; no translation layer between languages |
| **Operability** | One language in logs, one debugger, one dependency manager |
| **Performance** | No HTTP hop between bot and doc generator; in-process for worker |
| **Testability** | Shared Pydantic schemas enable contract tests without service boundaries |

### Alternatives Considered

#### Option A: Node.js bot (Telegraf) + Python API via HTTP call

- **Pros:**
  - Telegraf has strong Telegram middleware ecosystem
  - Node.js event loop well-suited for I/O-bound bot interactions
  - Teams with Node.js expertise can parallelize more easily
- **Cons:**
  - Two runtimes in production (Node.js container + Python container) from day one
  - HTTP call between bot and API for every message adds latency and failure surface
  - Two separate dependency graphs; security patching doubles
  - Schema duplication: TypeScript types + Pydantic models describing the same domain
  - No shared models — contract drift is a latent risk
- **Fitness function:** inter-service contract test required (Pact or similar) to prevent drift

#### Option B: Node.js bot (Telegraf) + Python subprocess for doc generation

- **Pros:**
  - Bot stays in Node.js; Python invoked only at document generation step
- **Cons:**
  - Subprocess is a fragile integration: no error propagation contract, blocking, hard to test
  - Process management burden in production (zombie processes, signals)
  - Still two runtimes to install, patch, and monitor
  - Debugging spans two language stacks
- **Fitness function:** subprocess integration tests required; timeout enforcement needed at OS level

#### Option C (Chosen): Pure Python monorepo — FastAPI + python-telegram-bot + Celery

- **Pros:**
  - Single runtime (Python 3.12+), single dependency manager (pip/uv)
  - Shared Pydantic models between bot handler, API, and worker — zero schema drift by design
  - In-process access to ReportLab and python-docx in the worker — no serialization overhead for doc generation
  - One Dockerfile base image; all processes (api, bot, worker) share it, differentiated by CMD
  - Simpler local development: one `docker-compose up` runs everything
  - SQLAlchemy async models shared across API and worker — no ORM per service
- **Cons:**
  - python-telegram-bot is capable but has a smaller middleware ecosystem than Telegraf
  - Python GIL limits true CPU parallelism in a single process (mitigated: API and bot are I/O-bound; CPU-bound doc gen is in the Celery worker as a separate process)
  - Some Telegram bot patterns are better documented in the Node.js/Telegraf community

### Decision

**Adopted Option C: Pure Python monorepo.**

The document generation requirement makes Python mandatory for the worker. Given that, introducing Node.js only for the bot creates a distributed monolith risk (coordinated deploy, shared state via HTTP, duplicate schemas) with no countervailing benefit for the MVP scale. python-telegram-bot covers all required Telegram Bot API features.

Architecture layout:
- `src/api/` — FastAPI application (async)
- `src/bot/` — python-telegram-bot handlers
- `src/worker/` — Celery tasks (rules engine + trip composer + doc generator)
- `src/db/` — SQLAlchemy async models (shared by api and worker)
- `src/lib/` — shared Pydantic schemas, utilities

All three processes (api, bot, worker) run from the same Docker image, launched with different `CMD` entries via `docker-compose`.

### Consequences

**Positive:**
- Zero schema drift: Pydantic models are imported, not duplicated
- One runtime to secure, patch, and monitor
- Simpler onboarding: developers only need Python proficiency
- Document generation quality guaranteed by ReportLab/python-docx with no translation layer

**Negative:**
- Telegraf ecosystem (middleware, plugins) not available; must implement patterns manually with python-telegram-bot
- Python startup time is slightly higher than Node.js for cold starts (non-issue for container-based deploy with persistent processes)

**Risks:**
- If team later needs a React-based frontend admin panel, a Node.js addition is natural — this ADR does not preclude that (different bounded context)
- If bot traffic scales to require horizontal scaling independently of the API, the shared-image approach still supports it (Kubernetes: separate deployments from same image)

### Fitness Functions

- `FF-001`: All Pydantic schemas imported by both `src/bot/` and `src/api/` must pass the same unit test suite — enforced in CI per commit.
- `FF-002`: Single Docker image build time < 3 minutes in CI (measures accidental dependency bloat).
- `FF-003`: Bot → API roundtrip latency p99 < 200ms on localhost (measures that in-process shared models don't add overhead when crossing to HTTP API).

### When to Revisit

- If a second language team joins and owns a new bounded context independently (natural point to introduce a second runtime with its own repo)
- If Telegram Bot API requires a feature only available in Telegraf and not in python-telegram-bot
- If document generation requires a completely different stack (e.g., headless Chrome for HTML→PDF rendering)
