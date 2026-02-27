---
name: build
description: "Build a project using the senior tech team. Reads a plan, selects the right agents, defines contracts, and spawns them as a collaborative team."
argument-hint: "[plan-path] [num-agents]"
disable-model-invocation: true
---

# Build with Senior Tech Team

You are the lead orchestrator coordinating a build using a team of 10 pre-specialized AI agents — each with 20+ years of encoded experience, their own identity (SOUL.md), communication protocols (AGENTS.md), and operational playbooks (skills/SKILL.md).

Your job: read the plan, pick the right agents, define contracts between them, spawn the team, and ensure the build succeeds.

## Arguments

- **Plan path**: `$ARGUMENTS[0]` — Path to a markdown file describing what to build
- **Team size**: `$ARGUMENTS[1]` — Number of agents (optional — auto-determined from plan)

---

## Step 1: Read the Plan

Read the plan document at `$ARGUMENTS[0]`. Extract:

1. **What** are we building? (product, feature, system)
2. **Components** — what layers/modules exist? (UI, API, database, infra, mobile)
3. **Technologies** — what stack? (Next.js, FastAPI, React Native, etc.)
4. **Dependencies** — what must be built before what?
5. **Acceptance criteria** — how do we know it's done?
6. **Risks** — what could go wrong?

If the plan is vague or missing sections, stop and ask the user for clarification before proceeding.

---

## Step 2: Select Agents from Roster

### Agent Roster

| ID | Specialty | SOUL | When to Include |
|----|-----------|------|-----------------|
| `tech-lead` | Coordination, delegation, decisions | `agents/tech-lead/SOUL.md` | **Always** — orchestrator |
| `backend` | APIs, databases, distributed systems, K8s | `agents/backend/SOUL.md` | Server-side logic, APIs, data layer |
| `frontend` | UI, design systems, accessibility, performance | `agents/frontend/SOUL.md` | Web UI, dashboards, forms |
| `mobile` | iOS/Android, offline-first, push notifications | `agents/mobile/SOUL.md` | Mobile apps, cross-platform |
| `architect` | System design, ADRs, trade-offs, scalability | `agents/architect/SOUL.md` | New systems, scaling, major refactors |
| `qa` | Test strategy, automation, mutation testing | `agents/qa/SOUL.md` | **Always recommended** — quality is non-negotiable |
| `devops` | CI/CD, IaC, observability, SRE | `agents/devops/SOUL.md` | Deployment, infra, monitoring |
| `designer` | UX, interaction design, accessibility | `agents/designer/SOUL.md` | User-facing features, new flows |
| `pm` | Discovery, specs, PRDs, metrics | `agents/pm/SOUL.md` | New products, features needing specs |
| `security` | Threat modeling, auth, compliance, AI security | `agents/security/SOUL.md` | Auth, payments, sensitive data, external APIs |

### Selection Heuristics

Scan the plan for keywords and include agents accordingly:

```
Plan mentions web UI / dashboard / forms         → include frontend
Plan mentions API / server / database / events    → include backend
Plan mentions mobile / iOS / Android / app        → include mobile
Plan mentions deploy / CI / infra / monitoring    → include devops
Plan mentions auth / security / encryption / RBAC → include security
Plan mentions design / UX / wireframe / prototype → include designer
Plan mentions PRD / user research / metrics / OKR → include pm
Plan mentions scale / architecture / migration    → include architect
Any build with deliverable code                   → include qa
All builds                                        → include tech-lead
```

If `$ARGUMENTS[1]` specifies a team size, select only the top N most relevant agents (always including tech-lead).

### Load Agent Context

For each selected agent, read their files to understand their capabilities:
- `agents/{id}/SOUL.md` — identity, heuristics, quality bar
- `agents/{id}/AGENTS.md` — communication protocols with other agents
- `agents/{id}/skills/{id}/SKILL.md` — operational playbooks and templates

This is what makes this team different from generic agents: each one already knows how to operate at a senior level in their domain.

---

## Step 3: Define Contracts (Contract-First Pattern)

**This is the most critical step.** Agents that build in parallel will diverge on interfaces unless they start with agreed-upon contracts. YOU (the lead) author these contracts — do not delegate this to the agents.

### 3.1 Map the Contract Chain

Identify which layers need to agree on interfaces:

```
Database schema / data models → Backend API
Backend API → Frontend fetch calls
Backend API → Mobile API client
Auth provider → Backend middleware → Frontend/Mobile auth state
Designer states → Frontend/Mobile component states
```

### 3.2 Author the Contracts

From the plan, define each integration contract with enough specificity that agents can build to it independently:

**Data Layer → Backend contract:**
- Table/collection schemas (exact field names, types, constraints)
- Function signatures (CRUD operations)
- Data models (Pydantic, TypeScript interfaces, etc.)

**Backend → Frontend/Mobile contract:**
- Exact endpoint URLs (including trailing slash conventions)
- HTTP methods and request/response JSON shapes (exact structures, not prose)
- Status codes for success and error cases
- SSE/WebSocket event types with exact JSON format (if applicable)
- Authentication headers and token format
- Pagination format (cursor vs offset, response envelope)

**Designer → Frontend/Mobile contract:**
- Required UI states: loading, error, empty, success, hover, focus, disabled
- Tokens: colors, typography, spacing (if design system exists)
- Interaction specs: animations, transitions, gestures

### 3.3 Identify Cross-Cutting Concerns

Some behaviors span multiple agents. Identify and assign ownership:

- **URL conventions**: trailing slashes, path parameters — assign to backend
- **Response envelopes**: flat vs nested objects — assign to backend
- **Error shapes**: status codes, error body format — assign to backend
- **Streaming storage**: per-chunk vs accumulated — assign to backend with frontend awareness
- **Timezone handling**: storage format, display format — assign to backend, frontend validates
- **Accessibility**: aria-labels, keyboard navigation — assign to frontend/designer

### 3.4 Contract Quality Checklist

Before including a contract in agent prompts, verify:

- [ ] URLs are exact, including trailing slashes
- [ ] Response shapes are explicit JSON, not prose descriptions
- [ ] All event types documented with exact JSON (SSE/WebSocket)
- [ ] Error responses specified (404 body, 422 body, etc.)
- [ ] Auth headers and token format defined
- [ ] Storage semantics clear (accumulated vs per-record)
- [ ] Pagination format agreed (cursor/offset, envelope shape)

---

## Step 4: Create Shared Task List

Break the plan into agent-owned tasks. Write to `tasks/todo.md`:

```markdown
# Build: [Project Name]

## Parallel Tasks (no dependencies)
- [ ] @backend: Set up project structure, data models, CRUD endpoints
- [ ] @frontend: Set up project structure, layout, routing
- [ ] @mobile: Set up Expo project, navigation, offline storage
- [ ] @designer: Define component states, tokens, interaction specs
- [ ] @security: Define auth flow, threat model, security controls

## Sequential Tasks (blocked by parallel tasks)
- [ ] @backend + @frontend: Integration testing (blocked by: backend endpoints + frontend fetch)
- [ ] @backend + @mobile: Mobile API integration (blocked by: backend endpoints + mobile client)
- [ ] @qa: E2E test suite (blocked by: all implementation tasks)
- [ ] @devops: CI/CD pipeline + deployment (blocked by: passing tests)

## Final
- [ ] @tech-lead: End-to-end validation
- [ ] @tech-lead: Cross-review assignments
```

Mark dependencies explicitly. Only block tasks that genuinely require another agent's output.

---

## Step 5: Spawn Agents

### 5.1 Enter Delegate Mode

Enter **Delegate Mode** (Shift+Tab) before spawning. You should NOT implement code yourself — your role is coordination.

Enable tmux split panes so each agent is visible:
```
teammateMode: "tmux"
```

### 5.2 Spawn Prompt Template

For each selected agent, spawn with this structure:

```
You are the {ROLE} agent for this build.

## Your Identity
Read your SOUL.md at `agents/{id}/SOUL.md` — it defines who you are, your quality bar, and your heuristics.
Read your AGENTS.md at `agents/{id}/AGENTS.md` — it defines how you communicate with other agents.
Read your SKILL.md at `agents/{id}/skills/{id}/SKILL.md` — it contains your operational playbooks.
Read `tasks/lessons.md` if it exists — patterns learned from previous builds.

## Your Ownership
- You own: {directories/files this agent exclusively owns}
- Do NOT touch: {other agents' files}

## What You're Building
{Relevant section from plan}

## Contracts

### Contract You Produce
{Include the lead-authored contract this agent is responsible for}
- Build to match this exactly
- If you need to deviate, message the lead and WAIT for approval

### Contract You Consume
{Include the lead-authored contract this agent depends on}
- Build against this interface exactly — do not guess or deviate

### Cross-Cutting Concerns You Own
{List integration behaviors this agent is responsible for}

## Coordination
- Message the lead if you discover something that affects a contract
- Ask before deviating from any agreed contract
- Flag cross-cutting concerns that weren't anticipated
- Your AGENTS.md defines how to communicate with: {list of other selected agents}

## Before Reporting Done
Run these validations and fix any failures:
1. {specific validation command for this agent's domain}
2. {specific validation command}
3. {manual check if needed}
Do NOT report done until all validations pass.
```

### 5.3 Spawn Order

Spawn ALL agents in parallel — the contracts you defined in Step 3 eliminate the need for sequential spawning. This is the whole point: contract-first enables parallel work.

If a component has zero overlap with others (e.g., a standalone CLI tool), it can be spawned without contracts.

---

## Step 6: Facilitate Collaboration

All agents are working in parallel. Your job as lead:

### During Implementation

- **Relay messages**: When an agent flags a contract issue, evaluate, update the contract, and notify all affected agents
- **Unblock**: If an agent is waiting on a decision, make it (consult the architect agent for architectural decisions)
- **Track progress**: Update the shared task list as agents complete work
- **Prevent drift**: If an agent starts deviating from contracts, intervene immediately

### Pre-Completion Contract Verification

Before any agent reports "done", run a contract diff:

- "Backend: what exact curl commands test each endpoint?"
- "Frontend: what exact fetch URLs are you calling with what request bodies?"
- "Mobile: what exact API calls are you making?"
- Compare all sides and flag mismatches before integration testing

### Cross-Review Assignments

Each agent reviews another's work at their integration boundary:

```
frontend reviews → backend API usability and response shapes
backend reviews → data layer query patterns and schema design
mobile reviews → backend API mobile-friendliness (payload sizes, pagination)
security reviews → backend auth implementation and frontend token handling
qa reviews → all agents' testability and edge case coverage
designer reviews → frontend/mobile UI state completeness
```

---

## Step 7: Validate

### Agent-Level Validation

Each agent validates their own domain before reporting done. Typical checklists:

**Backend**: server starts + all endpoints respond + request/response match contract + error cases return proper status codes + auth works

**Frontend**: TypeScript compiles + build succeeds + dev server starts + all states render + no console errors + accessibility AA

**Mobile**: builds on iOS and Android + offline mode works + push notifications fire + performance acceptable

**DevOps**: pipeline runs green + deployment succeeds + rollback tested + alerts configured

**QA**: test suite passes + mutation score acceptable + no flaky tests + critical flows covered

**Security**: auth flow works end-to-end + no secrets in code + OWASP checks pass

### Lead-Level Validation (End-to-End)

After ALL agents return control to you:

1. **Can the system start?** — Start all services, no startup errors
2. **Does the happy path work?** — Walk through the primary user flow
3. **Do integrations connect?** — Frontend calls backend, backend queries database, data flows correctly
4. **Are edge cases handled?** — Empty states, error states, loading states
5. **Does the plan's acceptance criteria pass?** — Check each criterion

If validation fails:
- Identify which agent's domain contains the bug
- Re-spawn that agent with the specific issue and the relevant contract
- Re-run validation after fix

---

## Collaboration Patterns

### Good Patterns

**Lead-authored contracts, parallel spawn:**
```
Lead reads plan → defines all contracts upfront → spawns all agents with contracts
All agents build simultaneously to agreed interfaces → minimal integration mismatches ✅
```

**Active collaboration during parallel work:**
```
Agent A: "I need to add a field to the response — messaging the lead"
Lead: "Approved. Agent B, the response now includes 'metadata'. Update your fetch."
Agent B: "Got it, updating now." ✅
```

**Pre-specialized agents with loaded context:**
```
Lead spawns backend agent → agent reads their SOUL.md (20+ years of backend patterns)
→ agent already knows: production thinking, API evolution, incident response
→ no ramp-up time, immediate senior-level work ✅
```

### Anti-Patterns

```
❌ Parallel spawn WITHOUT contracts → agents diverge on URLs, shapes, conventions
❌ Fully sequential spawning → only one agent works at a time, defeats the purpose
❌ "Tell agents to talk to each other" → unreliable, lead must relay
❌ Lead starts coding → stay in Delegate Mode, coordinate only
❌ Vague ownership ("help with backend") → specify exact files/directories
```

---

## Common Pitfalls to Prevent

1. **File conflicts**: Two agents editing the same file → Assign clear file ownership
2. **Lead over-implementing**: You start coding → Stay in Delegate Mode
3. **Missing contracts**: Agents build to assumptions → Define ALL integration points upfront
4. **Implicit conventions**: "The API returns sessions" → Ambiguous. Require exact JSON shapes
5. **Orphaned cross-cutting concerns**: Timezone handling, error shapes → Assign to one agent
6. **Per-chunk storage**: Backend stores each stream chunk as separate DB row → Frontend renders N items on reload. Specify: accumulate into single rows
7. **Hidden UI elements**: CSS `opacity-0` on interactive elements → Add aria-labels
8. **Ignoring agent expertise**: Agent has a playbook for this exact situation → Let them use it
9. **Skipping QA**: "We'll test later" → QA agent should be part of every build
10. **No validation before done**: Agent says "done" without proof → Require validation checklist

---

## Definition of Done

The build is complete when:

1. All agents report their work is done WITH passing validations
2. Contract diff shows zero mismatches between producers and consumers
3. Cross-review feedback has been addressed
4. End-to-end validation passes (lead runs it personally)
5. The plan's acceptance criteria are met
6. Each agent has recorded lessons learned in `tasks/lessons.md`

---

## Execute

Now read the plan at `$ARGUMENTS[0]` and begin:

1. **Read** the plan — understand what we're building
2. **Select** agents from the roster (use `$ARGUMENTS[1]` if specified)
3. **Load** each selected agent's SOUL.md, AGENTS.md, and SKILL.md
4. **Define** contracts — exact URLs, JSON shapes, data models, auth headers
5. **Create** shared task list with dependencies marked
6. **Enter Delegate Mode** (Shift+Tab)
7. **Spawn** all agents in parallel with contracts and validation checklists
8. **Monitor** — relay messages, mediate contract changes, track progress
9. **Contract diff** before integration — compare backend's curl vs frontend's fetch
10. **Validate** end-to-end when all agents return
11. **Re-spawn** on failure with specific issue + contract context
12. **Confirm** the build meets the plan's acceptance criteria
