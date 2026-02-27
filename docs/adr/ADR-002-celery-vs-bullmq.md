## ADR-002: Celery + Redis Instead of BullMQ for Async Trip Generation

**Status:** Accepted
**Date:** 2026-02-26
**Deciders:** Tech Lead, Architect

---

### Context

Trip generation is a long-running, CPU and I/O intensive job: it queries data sources, runs the rules engine quality filters, assembles the trip composer output, renders PDF (ReportLab) and DOCX (python-docx), and uploads to S3/R2. Estimated completion time: 30–120 seconds for a 10-day Europe trip.

Telegram bots have a hard timeout of ~15 seconds per message response. Synchronous generation inside the bot handler would exceed this limit and produce a degraded or broken UX. An async queue is therefore a non-negotiable architectural requirement.

The original plan mentioned BullMQ as a queue candidate. BullMQ is a Node.js library built on Redis. Since ADR-001 established a pure Python monorepo, this ADR documents why Celery + Redis was chosen over BullMQ and other alternatives.

### Architecture Characteristics Affected

| Characteristic | Impact |
|---|---|
| **Reliability** | At-least-once delivery with configurable retry and exponential backoff |
| **Operability** | Worker observability (Flower, Celery events); Redis well-understood |
| **Maintainability** | Same language as API and worker; no FFI or subprocess boundary |
| **Performance** | Task serialization overhead is measurable but acceptable at MVP scale |
| **Deployability** | Worker shares Docker image with API (ADR-001) |

### Alternatives Considered

#### Option A: BullMQ (Node.js + Redis)

- **Pros:**
  - Excellent DX: typed job definitions, built-in rate limiting, job priorities, repeatable jobs
  - Active ecosystem; rich dashboard (Bull Board)
  - Redis-backed; no additional message broker infrastructure
- **Cons:**
  - Requires Node.js runtime — contradicts ADR-001 Python monorepo decision
  - Would require a Node.js worker container alongside Python API and bot containers: back to polyglot ops
  - Job payload must be serialized; Python worker would need to consume from Redis directly (fragile, no contract)
  - Debugging spans two runtimes
- **Verdict:** Eliminated by ADR-001. Would reintroduce the polyglot complexity this project explicitly rejected.

#### Option B: ARQ (asyncio-native Python queue)

- **Pros:**
  - Pure asyncio: no separate worker thread pool; compatible with async SQLAlchemy
  - Simpler than Celery: fewer concepts, smaller surface area
  - Redis-backed; same infrastructure dependency as Celery option
- **Cons:**
  - Less mature ecosystem than Celery: fewer integrations, less community tooling
  - No built-in Flower-equivalent monitoring dashboard
  - Retry semantics and dead-letter-queue patterns require more manual implementation
  - Smaller community → higher risk of unmaintained dependency over 12+ months
- **Fitness function:** retry and DLQ behavior would require custom implementation with test coverage burden

#### Option C: RQ (Redis Queue, Python)

- **Pros:**
  - Simple API; easy to understand and onboard
  - Redis-backed; minimal configuration
  - Python-native; no runtime boundary
- **Cons:**
  - Fewer features than Celery: no chord/chain/group primitives, limited retry policies
  - No built-in task routing with priority queues at the same level as Celery
  - Less suitable if generation pipeline evolves into multi-step chained tasks (rules → compose → generate → upload)
  - Monitoring tooling less mature than Celery's Flower
- **Verdict:** Viable for simple cases but would require more custom code if the generation pipeline grows in complexity.

#### Option D: Keeping Node.js only for the queue (hybrid approach)

- **Pros:**
  - BullMQ's DX is genuinely superior for queue management
- **Cons:**
  - Reintroduces Node.js runtime for a single concern
  - Polyglot ops: separate node_modules, separate runtime patching, coordination in CI/CD
  - Cross-language job consumption: Python worker polling Redis keys directly is fragile and undocumented
- **Verdict:** Rejected. Same rationale as ADR-001.

#### Option E (Chosen): Celery 5+ with Redis broker

- **Pros:**
  - Python-native: worker code is plain Python; SQLAlchemy sessions, Pydantic models, boto3 — all work directly
  - Proven at scale: widely deployed in production across the Python ecosystem
  - Built-in retry with configurable backoff (max_retries=3, countdown=1s/5s/30s)
  - Flower provides real-time task monitoring UI out of the box
  - Task routing to named queues (`trip_generation`) is first-class
  - Chord/chain primitives available if the generation pipeline is decomposed in Phase 2
  - Redis as broker and result backend — single infrastructure dependency already needed for caching
- **Cons:**
  - Heavier than ARQ or RQ: more configuration surface, more concepts (beat, flower, canvas)
  - Celery serialization: JSON by default; msgpack available for performance if needed
  - Celery's concurrency model (prefork by default) does not play well with asyncio in the worker tasks — worker tasks must be written as sync functions or use `gevent`/`eventlet`
  - Known issue: Celery's task state machine can have edge cases with database session lifecycle; requires explicit session management in tasks

### Decision

**Adopted Option E: Celery 5+ with Redis broker and result backend.**

Contract (from tasks/todo.md — C4):
- Queue name: `trip_generation`
- Task name: `worker.tasks.generate_trip`
- Payload: `{ "trip_id": "<uuid>", "output_id": "<uuid>" }`
- Retry: 3 attempts, exponential backoff (1s, 5s, 30s)
- On failure: `trip_outputs.status = "failed"`, `error_message` set

The concurrency limitation (prefork + sync tasks) is acceptable for MVP: doc generation is a CPU-bound workload that benefits from process isolation, not asyncio coroutines. If the API needs high async throughput, it runs as a separate process from the worker.

### Consequences

**Positive:**
- Worker tasks are plain synchronous Python functions — simpler to write and test
- Shared Pydantic models and SQLAlchemy sessions between API and worker; no serialization layer needed for internal data
- Redis already required by the architecture (session/rate-limiting candidate); reusing it as Celery broker avoids additional infrastructure
- Flower monitoring available without additional tooling

**Negative:**
- Celery prefork worker and async SQLAlchemy do not mix natively; worker must use synchronous SQLAlchemy sessions (separate engine config for worker vs API)
- Celery configuration surface is larger than ARQ/RQ; onboarding cost is higher
- JSON serialization of task payloads adds minor overhead vs in-process calls

**Risks:**
- Celery's long-running tasks may encounter Redis connection timeout; must configure `broker_transport_options` with heartbeat and visibility timeout > max task duration (>120s)
- If generation pipeline grows to 5+ chained steps, Celery Canvas complexity increases; revisit with ARQ or a dedicated orchestrator (Temporal/Prefect) at that point

### Fitness Functions

- `FF-004`: Worker job completion for a 10-day Europe trip < 5 minutes — measured in CI integration test with a mocked data source.
- `FF-005`: Failed task rate < 1% in production (non-retryable failures); monitored via Flower + Sentry.
- `FF-006`: `trip_outputs.status` reflects accurate state within 2 seconds of task state transition — validated by polling integration test.
- `FF-007`: Redis broker visibility timeout configured to `>= 600s` (10 min) — enforced via CI config lint check to prevent silent task re-queuing.

### When to Revisit

- If generation pipeline is decomposed into 5+ discrete async steps requiring orchestration (consider Temporal or Prefect)
- If worker throughput requires asyncio concurrency (reconsider ARQ or Celery + gevent)
- If Redis cost/ops burden grows; evaluate dedicated broker (RabbitMQ) at that point with evidence
