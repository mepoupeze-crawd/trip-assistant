## ADR-004: No LLM Calls in MVP — Deterministic Rules Engine Only

**Status:** Accepted
**Date:** 2026-02-26
**Deciders:** Tech Lead, Architect, PM

---

### Context

The plan describes a "trip composer" that assembles a luxury Europe itinerary from structured data, filtered by an "anti-trap rules engine" with quality thresholds. The natural question is: should this composition be done by a Large Language Model (LLM) or by a deterministic rules-based system?

LLMs (e.g., GPT-4, Claude, Gemini) are capable of generating travel narratives that sound authoritative and personalized. However, the target product is a **luxury trip planning report sold for R$100** — a product where the quality bar is not "sounds good" but "is accurate, auditable, and trustworthy." A recommendation for a hotel or restaurant that sounds convincing but is wrong (closed, relocated, below quality threshold, tourist trap) directly harms the customer and the brand.

The plan explicitly defines quality thresholds (C6 in tasks/todo.md):
- Hotel: `rating >= 4.0 AND review_count >= 100`
- Attraction/activity: `rating >= 4.0 AND review_count >= 500`
- Restaurant/bar: `rating >= 4.2 AND review_count >= 200`

These thresholds are deterministic filters, not generation prompts.

### The Hallucination Risk — Why This Matters for This Product

LLMs hallucinate. In travel planning, hallucination takes these concrete forms:

1. **Phantom places**: The model generates a hotel or restaurant name that sounds plausible but does not exist, or existed and closed.
2. **Stale data presented as current**: LLM training data has a cutoff; a restaurant acclaimed in 2022 may have closed by 2025.
3. **Quality inversion**: The model recommends a place it "knows" without verifying it meets the defined quality thresholds for rating and review count.
4. **Confident wrongness**: LLMs present hallucinated facts with the same confidence as accurate ones — users cannot distinguish them without independent verification.

For a luxury product, a single wrong recommendation (e.g., a tourist trap hotel recommended with confidence) destroys trust and triggers refund requests. The "beautiful but wrong" failure mode is categorically worse than "less personalized but correct."

### Architecture Characteristics Affected

| Characteristic | Impact |
|---|---|
| **Reliability** | Deterministic engine produces consistent, auditable output; LLM output is probabilistic |
| **Security** | LLM introduces prompt injection attack surface; not present in rules engine |
| **Cost** | LLM API calls: $0.01–$0.06 per generation at scale; rules engine: $0 marginal cost |
| **Latency** | LLM call adds 5–30s to generation pipeline; deterministic engine: milliseconds |
| **Auditability** | Every rule applied can be logged and inspected; LLM reasoning is opaque |
| **Testability** | Deterministic engine: 100% reproducible unit tests; LLM: requires eval framework |

### Alternatives Considered

#### Option A: LLM as primary trip composer

- **Pros:**
  - Rich, personalized narrative text for hotel descriptions, activity suggestions, day-by-day itinerary prose
  - Adapts to preferences in natural language (pace, focus, restrictions)
  - Faster to prototype: prompt engineering vs rules engine implementation
- **Cons:**
  - Hallucination risk is fundamental and unmitigated in MVP: no eval loop, no grounding mechanism
  - LLM cannot enforce `rating >= 4.0` constraints reliably — it will include places that "feel right" regardless of actual ratings
  - Adds API cost per generation: at R$100 product price, LLM cost must be < R$5 to maintain margin
  - Adds 5–30s latency to already long generation pipeline
  - Requires eval infrastructure (test sets, human review, automated scoring) before production use
  - Prompt injection: a user who inputs `preferences_json` with adversarial content can attempt to manipulate output
  - LLM outputs are non-deterministic: same input produces different output, making regression testing unreliable
- **Verdict:** Viable for Phase 2, but only with eval loops, grounding from verified data sources, and guardrails. Not appropriate for MVP.

#### Option B: LLM for narrative text only, rules engine for recommendations

- **Pros:**
  - Rules engine guarantees quality-threshold compliance; LLM only writes prose about verified recommendations
  - Reduces hallucination surface: LLM receives structured data, not open-ended prompts
- **Cons:**
  - Still requires grounding strategy: LLM must be constrained to write only about recommendations already selected
  - Adds LLM API cost and latency for the narrative layer
  - Requires guardrails to prevent the LLM from "embellishing" with invented details about the verified recommendations
  - Eval infrastructure still needed to catch model drift over time
  - More complex architecture: two systems instead of one
- **Verdict:** A better LLM integration pattern than Option A, but still introduces complexity, cost, and hallucination risk that is not justified for MVP. Deferred to Phase 2.

#### Option C (Chosen): Deterministic rules engine + structured data, zero LLM

- **Pros:**
  - Zero hallucination risk: every recommendation comes from a verified data source with known provenance
  - Every output is auditable: log which rules applied, which items passed/failed thresholds, what fallback logic ran
  - Deterministic: same input always produces same output — regression testing is trivial
  - Zero marginal LLM cost per generation
  - No prompt injection attack surface
  - Fast: rules engine runs in milliseconds; document generation is the bottleneck, not composition
  - Correctness by construction: `rating >= 4.0 AND review_count >= 100` is enforced as a Python `if` statement, not a natural language instruction to a model
- **Cons:**
  - Output is structured and templated, not narratively rich — less "magical" than LLM-generated prose
  - Preferences must be mapped to structured filters, not interpreted from natural language (mitigated: preferences_json is already structured per C2 contract)
  - Cannot generate the kind of contextual commentary ("this restaurant is perfect for your interest in food + culture because...") without either templating or LLM
- **Verdict:** Accepted for MVP. The product promise is accuracy and quality, not narrative richness.

### Decision

**Adopted Option C: Deterministic rules engine only in MVP. LLM integration is explicitly Phase 2.**

The rules engine in MVP operates as follows:
1. **Input**: `preferences_json` (pace, focus, crowds, hotel, restrictions) + trip parameters (country, days, party_size, budget)
2. **Data sourcing**: Permitted data sources (Google Places API, curated internal data) — no LLM-generated data
3. **Filtering**: Quality thresholds per C6 (rating + review_count per category)
4. **Fallback logic**: If < 10 items pass threshold → expand radius → swap city → reduce list; log justification
5. **Composition**: Trip Composer assembles day-by-day itinerary from filtered recommendations
6. **Output**: Structured data passed to Document Generator (ReportLab for PDF, python-docx for DOCX)

Phase 2 LLM integration (when warranted):
- Requires: eval pipeline (offline test set + online canary metrics), grounding mechanism (LLM only narrates about verified recommendations), guardrails (output filter for invented proper nouns, cost caps), and human review of eval results before production.

### Consequences

**Positive:**
- MVP output is deterministic, auditable, and correct by construction
- No hallucination risk in MVP — directly protects brand trust for a paid product
- Regression testing is reliable: same input → same output → deterministic assertions
- No LLM API cost in the generation pipeline
- Simpler architecture: one system (rules engine) instead of two (rules + LLM)

**Negative:**
- Output narrative quality is limited to template-based text; less personalized prose
- Adding LLM in Phase 2 requires building eval infrastructure from scratch (not just "add the API call")
- Competitor products with LLM may appear more personalized to users who don't know about hallucination risks

**Risks:**
- Market expectation: if users expect AI-generated narratives, template output may feel underwhelming — mitigate with clear product positioning ("verified luxury recommendations") and quality bar emphasis
- Phase 2 LLM integration must not be added as an "API wrapper" — it requires architectural work (eval, guardrails, grounding); document this explicitly to prevent shortcuts

### Fitness Functions

- `FF-012`: Every recommendation in the output must have `source_url` pointing to a verified external source — enforced by output validation test (no recommendation without provenance).
- `FF-013`: No recommendation below quality threshold in any generated output — enforced by automated output validation: parse PDF/DOCX data and assert `rating >= threshold` for each recommendation category.
- `FF-014`: Generation pipeline contains zero HTTP calls to LLM provider APIs — enforced by network egress allowlist in CI (allowlist: Google Places API, S3/R2, Stripe; block: openai.com, anthropic.com, generativelanguage.googleapis.com).
- `FF-015`: Rules engine fallback logic is logged when triggered — enforced by integration test that asserts fallback events appear in structured logs when a city has < 10 qualifying recommendations.

### When to Revisit

- When narrative quality is identified as a top user complaint (NPS or support tickets)
- When eval infrastructure is ready: offline test set with human-labeled good/bad outputs, automated scoring, canary deployment capability
- When LLM API cost per generation is < 5% of product price (R$5 at R$100 price point) — currently feasible but requires ongoing monitoring as usage scales
- Before Phase 2 LLM integration: security agent must threat-model prompt injection and data exfiltration vectors
