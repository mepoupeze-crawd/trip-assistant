## ADR-003: Stripe as Primary Payment Provider (MercadoPago as Phase 2)

**Status:** Accepted
**Date:** 2026-02-26
**Deciders:** Tech Lead, Architect, PM

---

### Context

The bot sells a single product: a luxury Europe trip planning report at R$100 per generation. The plan lists two candidate providers: **Stripe** (international) and **MercadoPago** (Brazil-focused). The target audience is travelers planning luxury Europe trips — a segment that skews toward users with international credit cards, though many are Brazilian.

Payment infrastructure is a hard dependency for the full user flow: no payment confirmation = no generation job dispatched. Reliability of the payment webhook is therefore a correctness concern, not just a UX concern.

The system currently holds `payments.provider` as a text column supporting both `"stripe"` and `"mercadopago"` — the schema is already designed for dual-provider.

Price: R$100 per trip (amount_cents = 10000, currency = BRL).

### Architecture Characteristics Affected

| Characteristic | Impact |
|---|---|
| **Reliability** | Webhook reliability directly impacts generation pipeline correctness |
| **Security** | Webhook signature verification is the primary attack surface |
| **Maintainability** | Single provider in MVP reduces integration surface |
| **Extensibility** | Schema already supports `provider` column for Phase 2 addition |
| **User Experience** | Payment method availability affects conversion |

### Alternatives Considered

#### Option A: MercadoPago first (then Stripe in Phase 2)

- **Pros:**
  - Native support for Brazilian payment methods: PIX, boleto bancário, cartão de crédito parcelado
  - Broad coverage of Brazilian unbanked/underbanked population
  - Lower cross-border fees for BRL transactions
- **Cons:**
  - MercadoPago webhook reliability has known intermittent issues in the developer community (delays, duplicate events)
  - Developer experience is significantly lower: less consistent documentation, SDK quality varies
  - International travelers paying in non-BRL currencies face more friction
  - MercadoPago sandbox environment has historically been flaky for integration testing
  - If target audience includes non-Brazilian travelers (e.g., Argentines, Colombians planning Europe trips), Stripe's international reach is superior
- **Verdict:** Valid for a BR-only market play, but risky for MVP given webhook reliability concerns and international audience.

#### Option B: Dual provider from day one (Stripe + MercadoPago simultaneously)

- **Pros:**
  - Maximum payment method coverage from launch
  - No Phase 2 migration needed
- **Cons:**
  - Two webhook endpoints to implement, test, and secure
  - Two payment state machines running in parallel — higher defect surface
  - Dual provider adds significant complexity to the `payments` table state machine (which provider confirmed? partial states?)
  - Doubles the integration test surface in CI
  - Stripe and MercadoPago have incompatible event models; reconciliation logic is non-trivial
- **Verdict:** Premature for MVP. YAGNI applies. The schema already supports it for Phase 2.

#### Option C (Chosen): Stripe for MVP, MercadoPago in Phase 2

- **Pros:**
  - Stripe has best-in-class webhook reliability: HMAC-SHA256 signature, retry with exponential backoff, event deduplication
  - Stripe Checkout hosted page handles PCI compliance without custom card form
  - Excellent SDK quality (`stripe-python`): typed, well-documented, actively maintained
  - Stripe supports BRL as currency natively — the R$100 charge works without currency conversion
  - Testing is reliable: Stripe test mode is production-faithful; card numbers are well-documented
  - Webhook event `checkout.session.completed` is atomic and reliable for triggering generation
  - Stripe Dashboard provides real-time payment visibility for ops
- **Cons:**
  - No PIX or boleto support — Brazilian users who prefer these methods cannot pay in MVP
  - Stripe fees for BRL transactions include cross-border processing fee (typically ~2.9% + fixed fee)
  - Some Brazilian-market users may perceive Stripe as less familiar than MercadoPago

### Decision

**Adopted Option C: Stripe for MVP with MercadoPago as explicitly planned Phase 2.**

Rationale:
1. **Webhook correctness is a system correctness concern.** The `POST /api/payments/webhook` endpoint is the only signal that unlocks trip generation dispatch. Stripe's HMAC-SHA256 signature (`Stripe-Signature` header) and idempotent event IDs make webhook handling deterministic. MercadoPago's webhook reliability at the time of decision does not match this bar.
2. **BRL is natively supported.** Stripe accepts BRL as a settlement currency; the R$100 price works without conversion complexity.
3. **PCI scope is minimized.** Stripe Checkout (hosted redirect) means card data never touches the API server; PCI scope reduces to SAQ A.
4. **Phase 2 path is explicit and low-cost.** The schema already has `payments.provider` as a nullable text column. Adding MercadoPago means: (a) implementing a second webhook handler, (b) adding a MercadoPago checkout URL creation path, (c) testing both flows. No schema migration required.

Integration contract (from tasks/todo.md):
- Initiate checkout: `POST /api/payments/create` → returns `payment_url` (Stripe Checkout URL)
- Confirm: `POST /api/payments/webhook` with `Stripe-Signature` header
- On `checkout.session.completed`: set `payments.status = "paid"` and dispatch generation job

### Consequences

**Positive:**
- Single payment state machine in MVP — lower defect surface
- HMAC webhook verification implemented once, reviewed once by Security agent
- Stripe test mode provides reliable CI integration tests for the full payment → generation flow
- Stripe Dashboard gives ops team real-time visibility without custom tooling

**Negative:**
- Brazilian users preferring PIX or boleto cannot pay in MVP — potential conversion loss for this segment
- Stripe cross-border processing fee applies to BRL charges (estimated: 2.9% + R$0.30 per charge)
- MercadoPago integration is deferred — must be explicitly scheduled in Phase 2 backlog before targeting BR-specific marketing

**Risks:**
- If the primary target market shifts to mass-market Brazil before Phase 2 is complete, conversion will be impacted
- Mitigation: track payment abandonment rate on Stripe Checkout; if > 30%, accelerate MercadoPago Phase 2

### Fitness Functions

- `FF-008`: Stripe webhook signature verification must reject requests with invalid `Stripe-Signature` — enforced by unit test (tampered payload → 400 response).
- `FF-009`: Payment → generation dispatch latency < 10 seconds from `checkout.session.completed` event receipt — measured in integration test with Stripe CLI webhook forwarding.
- `FF-010`: `payments.status` never transitions to `"paid"` without a valid Stripe event ID stored in `external_id` — enforced by DB constraint check in CI.
- `FF-011`: Zero plaintext Stripe API keys in source code or logs — enforced by git-secrets pre-commit hook and CI secret scanner.

### When to Revisit

- When MercadoPago PIX/boleto demand is evidenced by user feedback or payment abandonment data
- When Stripe fee cost becomes material (> 5% of revenue) — evaluate MercadoPago for BR-market transactions
- If Stripe changes BRL settlement terms or availability
