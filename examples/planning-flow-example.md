# Planning Flow Example: From Vague Idea to Build-Ready Plan

This example shows how the `/plan` skill transforms a vague user request into a structured plan that `/build` can execute.

---

## The Vague Request

User says:
> "Create a calendar assistant application"

That's it. No stack, no features, no target user. Just an idea.

---

## What Happens (Step by Step)

### Step 1: Intake Assessment

The `/plan` skill classifies this as **"Needs discovery"** — it's a single sentence with no technical context.

It asks the user 3-5 targeted questions:

```
Before I plan this, I need to understand:

1. **Who uses this?** → individuals managing personal schedules
2. **Platform?** → web app (can be opened from any device)
3. **Key action?** → create events using natural language ("lunch with Ana on Friday at noon")
4. **Integrations?** → Google Calendar (sync events bidirectionally)
5. **Constraints?** → none stated; assume MVP scope
```

### Step 2: PM Discovery (What + Why + For Whom)

The PM agent's thinking activates:

**Problem Definition:**
- **What problem?** Existing calendar tools require too many clicks and form fields
- **Who?** Professionals managing busy schedules who want less friction
- **How today?** Google Calendar / Outlook — manual clicks, form fields, repetitive
- **Core value?** Type what you want in plain language, assistant handles the rest
- **MVP scope?** NL event creation + weekly view + Google Calendar sync

**User Stories (MVP):**

```
1. As a busy professional,
   I want to type "Schedule lunch with Ana next Friday at noon"
   so that the event is created without filling forms.
   - AC: Event appears on calendar grid within 5 seconds
   - AC: Event syncs to Google Calendar

2. As a user with a packed week,
   I want to ask "What do I have on Thursday?"
   so that I get a quick summary without scrolling.
   - AC: Natural language summary of day's events

3. As someone who forgets meetings,
   I want to receive a reminder 15 minutes before events
   so that I never miss a commitment.
   - AC: Email notification arrives 15 min before event
```

**Scope:**
- **IN:** NL event creation, weekly/monthly calendar grid, Google Calendar sync, email reminders, conflict detection
- **OUT:** Multi-calendar support, team scheduling, voice input, mobile native app, recurring event editing via NL

### Step 3: Architect Design (How)

The Architect agent designs the system:

**Stack:**
- Frontend: Next.js (App Router) + TypeScript + Tailwind CSS
- Backend: Next.js API Routes (fullstack, same repo — simplest for MVP)
- Database: PostgreSQL (Neon) with Prisma
- AI: Claude API for NL → event parsing
- Auth: NextAuth.js with Google OAuth
- Calendar Sync: Google Calendar API
- Deploy: Vercel

**Components:** Database layer (4 tables), API routes (auth + calendar CRUD + AI chat + cron), Frontend (login + calendar grid + chat sidebar + settings)

**Risk Assessment:**

| Risk | Impact | Mitigation |
|------|--------|------------|
| AI parses dates wrong | High | Show preview before confirming |
| Google OAuth token expiry | High | Refresh token flow |
| Timezone confusion | High | Store UTC, display in user tz |

### Step 4: Tech Lead Team Validation

The Tech Lead evaluates which agents are needed:

**Team Justification:**

| Agent | Include? | Justification | Deliverables |
|-------|----------|---------------|-------------|
| tech-lead | YES | Always — orchestration | Contracts, task list, validation |
| backend | YES | API routes, DB, Google Calendar integration, AI chat endpoint | Schema, CRUD endpoints, OAuth flow, AI parsing |
| frontend | YES | Calendar grid, chat sidebar, forms, responsive UI | Pages, components, state management |
| qa | YES | Quality non-negotiable — NL parsing needs thorough testing | Test suite, E2E for critical flows |
| security | YES | Google OAuth + token storage + AI with user data | Auth review, token handling, data protection |
| designer | YES | User-facing app needs polished UX — chat + calendar interaction | Component states, interaction specs |
| devops | NO | Vercel handles deployment; MVP doesn't need complex infra | — |
| mobile | NO | Web only for MVP (responsive covers mobile) | — |
| architect | NO | Standard web app pattern; no novel architecture needed | — |
| pm | NO | Discovery done during planning; specs are clear | — |

**Team size: 6 agents** (tech-lead + backend + frontend + qa + security + designer)

**Validation:**
- Every component has an owner
- Integration boundaries covered (backend ↔ frontend via contracts)
- Auth has dedicated security review
- No idle agents
- Workload balanced: backend (G), frontend (G), qa (M), security (M), designer (M)

### Step 5: Generated Plan

The output is `examples/calendar-assistant-plan.md` — a complete, structured plan identical in format to the existing example, ready for `/build`.

### Step 6: User Approval

```
✅ Plan ready: Calendar Assistant (MVP)

Summary: Web app with AI-powered natural language calendar management
Team: 6 agents (tech-lead, backend, frontend, qa, security, designer)
Key decisions: Next.js fullstack, PostgreSQL, Claude API for NL, Google Calendar sync
Build size: Medium (estimated G complexity)

Does this plan look right? Want to adjust anything before we build?

When ready: /build examples/calendar-assistant-plan.md
```

---

## The Two-Command Flow

```
/plan Create a calendar assistant application
→ PM discovers, Architect designs, Tech Lead validates team
→ Output: examples/calendar-assistant-plan.md

/build examples/calendar-assistant-plan.md
→ Tech Lead defines contracts, spawns agents, coordinates build
→ Output: working application
```

---

## When `/plan` Skips Steps

| User Says | What `/plan` Does |
|-----------|-------------------|
| "Create a calendar app" | Full flow (discovery → design → team → plan) |
| "Build a Next.js calendar with Google sync and NL input" | Partial (skip clarification, run design → team → plan) |
| "Here's my calendar app idea: [detailed paragraph with stack]" | Light (validate team + fill gaps only) |
| [Provides a complete plan file] | Skip → "Run `/build` directly" |

---

## How Team Selection Works (Not Just Keywords)

The Tech Lead doesn't just scan for "web UI" → include frontend. The validation process asks:

1. **Does this agent have specific deliverables?** If you can't name 3+ concrete things the agent will produce, don't include them.

2. **Is there an integration boundary?** If backend produces APIs and frontend consumes them, both are needed. If there's no mobile UI, the mobile agent adds zero value.

3. **Is the concern critical enough for a specialist?** Auth with Google OAuth + token storage + user data = security agent needed. A static landing page with no auth = security agent not needed.

4. **Does adding this agent reduce risk more than it adds coordination overhead?** Each additional agent means more contracts, more communication, more potential for drift. The marginal benefit must exceed the marginal cost.

5. **Could another agent absorb this work?** If the designer's only task is "make it look decent" and the frontend agent has strong UI skills (which it does — check its SOUL.md), maybe you don't need a dedicated designer for an internal tool.

This is how a real tech lead thinks about staffing — not keyword matching, but value-based team composition.
