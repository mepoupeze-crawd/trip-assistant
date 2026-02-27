---
name: plan
description: "Turn a vague idea into a structured build plan. Orchestrates PM (discovery), Architect (system design), and Tech Lead (team selection + validation) to produce a ready-to-build plan."
argument-hint: "[idea-description]"
---

# Plan: From Vague Idea to Build-Ready Plan

You are the planning orchestrator. When a user says something vague like "Create a calendar assistant" or "Build me a trip planner app", your job is to turn that into a structured build plan that `/build` can execute.

**This is the missing step between "I have an idea" and "the team is building it."**

## The Problem This Solves

The `/build` skill requires a detailed plan with: components, stack, data models, API contracts, acceptance criteria, and risks. Most users don't start there — they start with an idea. This skill bridges that gap by having the senior agents collaborate on planning before a single line of code is written.

## Arguments

- **Idea**: `$ARGUMENTS` — A natural language description of what the user wants to build (can be as vague as "a calendar app" or as detailed as a paragraph)

---

## Step 1: Intake — Understand the Idea (2 min)

Read what the user wants: `$ARGUMENTS`

### 1.1 Quick Assessment

Classify the request:

| Signal | Classification |
|--------|---------------|
| Has components, stack, acceptance criteria | **Ready for /build** — skip planning, suggest `/build` directly |
| Has clear product idea but no technical details | **Needs planning** — run full flow |
| Single sentence, no context | **Needs discovery** — start with PM discovery |
| Ambiguous (could be many things) | **Needs clarification** — ask 3-5 targeted questions first |

### 1.2 If Clarification Needed

Ask the user a MAXIMUM of 5 targeted questions. Do NOT ask open-ended questions. Use this format:

```
Before I plan this, I need to understand:

1. **Who uses this?** (individual / team / business)
2. **Platform?** (web / mobile / bot / API / CLI)
3. **Key action?** (what's the ONE thing the user must be able to do?)
4. **Integrations?** (does it connect to anything external?)
5. **Constraints?** (budget, timeline, existing tech stack?)
```

Skip questions where the answer is obvious from context. Never ask more than 5 questions total — if you can't scope with 5 questions, make reasonable assumptions and document them.

---

## Step 2: PM Discovery — Define the Product (What + Why + For Whom)

Activate the PM agent's thinking by reading `agents/pm/SOUL.md` and `agents/pm/skills/pm/SKILL.md`.

Apply the PM's operational playbooks:

### 2.1 Problem Definition (PM Playbook P5 — Opportunity Assessment)

Answer these from the user's input (or reasonable assumptions):

1. **What problem does this solve?** (pain point in plain language)
2. **Who has this problem?** (target user — be specific)
3. **How do they solve it today?** (alternatives, workarounds)
4. **What's the core value proposition?** (why would they switch?)
5. **What's the MVP scope?** (minimum that proves value)

### 2.2 User Stories (PM Template T4)

Write 3-7 user stories for the MVP:

```
As a [persona],
I want to [action],
so that [benefit/outcome].

Acceptance criteria:
- [ ] [verifiable condition 1]
- [ ] [verifiable condition 2]
```

### 2.3 Scope Definition (IN / OUT)

Explicitly define what's IN scope for MVP and what's OUT:

```
## Scope
- IN: [what we build now]
- OUT: [what we DON'T build — and why]
```

This prevents scope creep and sets expectations. The OUT list is as important as the IN list.

---

## Step 3: Architect Design — Define the System (How)

Activate the Architect agent's thinking by reading `agents/architect/SOUL.md` and `agents/architect/skills/architect/SKILL.md`.

### 3.1 Stack Selection (Architect ADR Process)

Choose technologies with justification:

```
## Stack

* **Frontend**: [choice] — [why, 1 sentence]
* **Backend**: [choice] — [why]
* **Database**: [choice] — [why]
* **Auth**: [choice] — [why]
* **AI/ML**: [choice, if applicable] — [why]
* **Integrations**: [external services] — [why]
* **Deploy**: [choice] — [why]
```

**Selection criteria** (from Architect SOUL):
- Simplest solution that meets requirements wins
- Build when core differentiator; buy when commodity
- Monolith when team small and domain unstable; microservices when independent teams
- Consider the user's existing stack if mentioned

### 3.2 Component Design (Architect C4 Level 2 — Containers)

Define the system components:

1. **Data Layer** — tables/collections with exact fields, types, constraints
2. **Backend** — API endpoints with methods, paths, request/response shapes
3. **Frontend** — pages/screens, routing, key UI states
4. **Infrastructure** — deployment, environment variables, cron jobs
5. **Integrations** — external APIs, webhooks, OAuth flows

### 3.3 Dependency Map

```
Component A → Component B (what flows between them)
Component B → Component C
```

### 3.4 Risk Assessment (Architect Heuristics)

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| [what could go wrong] | [H/M/L] | [H/M/L] | [how to prevent/handle] |

---

## Step 4: Tech Lead Validation — Select and Validate the Team

Activate the Tech Lead agent's thinking by reading `agents/tech-lead/SOUL.md` and `agents/tech-lead/skills/tech-lead/SKILL.md`.

### 4.1 Team Selection with Justification

**Don't just match keywords.** The Tech Lead evaluates each agent against the plan using this scoring matrix:

| Agent | Needed? | Justification | Confidence |
|-------|---------|---------------|------------|
| tech-lead | YES (always) | Orchestration, delegation, contract authoring | 100% |
| backend | [YES/NO] | [What specific work requires this agent?] | [H/M/L] |
| frontend | [YES/NO] | [What specific work requires this agent?] | [H/M/L] |
| mobile | [YES/NO] | [What specific work requires this agent?] | [H/M/L] |
| architect | [YES/NO] | [What specific work requires this agent?] | [H/M/L] |
| qa | [YES/NO] | [What specific work requires this agent?] | [H/M/L] |
| devops | [YES/NO] | [What specific work requires this agent?] | [H/M/L] |
| designer | [YES/NO] | [What specific work requires this agent?] | [H/M/L] |
| pm | [YES/NO] | [What specific work requires this agent?] | [H/M/L] |
| security | [YES/NO] | [What specific work requires this agent?] | [H/M/L] |

### 4.2 Team Validation Checklist

After selecting the team, validate the composition:

```
## Team Validation

Coverage check:
- [ ] Every component in the plan has an agent owner
- [ ] No component is owned by two agents (conflict risk)
- [ ] Every integration boundary has agents on both sides
- [ ] Critical concerns have dedicated agents (auth → security, quality → qa)

Efficiency check:
- [ ] No agent is included without specific deliverables
- [ ] Team size ≤ 7 agents (cognitive overhead grows with team size)
- [ ] If team > 7, justify why each agent is essential

Risk check:
- [ ] Agent with highest workload identified — is it overloaded?
- [ ] Cross-cutting concerns assigned to exactly one agent each
- [ ] Dependencies between agents are explicit and minimal
```

### 4.3 Team Optimization

If the validation reveals issues:

- **Missing coverage**: Add the agent needed, with specific justification
- **Overlap/conflict**: Remove the less critical agent, or split responsibilities clearly
- **Overloaded agent**: Consider splitting work or adding a supporting agent
- **Unnecessary agent**: Remove and document why (avoid team bloat)

### 4.4 Workload Distribution Preview

Show what each selected agent will own:

```
## Agent Assignments

@tech-lead: Orchestration, contracts, validation
  - Deliverables: contracts, task list, cross-review
  - Estimated complexity: [P/M/G]

@backend: [specific work]
  - Deliverables: [list]
  - Estimated complexity: [P/M/G]

@frontend: [specific work]
  - Deliverables: [list]
  - Estimated complexity: [P/M/G]

[... for each selected agent]
```

---

## Step 5: Compose the Build Plan

Assemble everything into a structured plan document. Save it to `examples/[project-name]-plan.md`.

### Plan Template

```markdown
# [Project Name] — Build Plan (MVP)

## What We're Building

[2-3 sentences describing the product]
[Bullet list of key features]

---

## Why

[The problem this solves, from PM discovery]

---

## Stack

[From Architect design]

---

## Components

### 1) [Component Name]
[Details: tables, endpoints, pages, etc.]

### 2) [Component Name]
[...]

---

## Dependencies Between Components

[Dependency map]

---

## Acceptance Criteria (MVP)

1. [From PM user stories — verifiable conditions]
2. [...]

---

## Risks and Mitigations

[From Architect risk assessment]

---

## Team

[From Tech Lead selection with justification]

---

## Validation

### Local Setup
[How to run locally]

### Quick Checks
[curl commands or similar]

### Manual E2E
[Step-by-step manual validation]
```

---

## Step 6: Present to User for Approval

Show the plan to the user with:

1. **Summary** (3 lines): what, why, who
2. **Team** (selected agents with justification)
3. **Key decisions** (stack choices, scope IN/OUT)
4. **Timeline hint** (not a promise — just "this is [small/medium/large] build")
5. **Questions for the user** (if any assumptions need validation)

Ask: **"Does this plan look right? Want to adjust anything before we build?"**

If approved, tell the user: **"Run `/build examples/[project-name]-plan.md` to start building."**

---

## Decision Framework: When Planning Adds Value vs When to Skip

| Scenario | Action |
|----------|--------|
| User gives 1 sentence with no context | **Full planning** (Steps 1-6) |
| User gives idea + some requirements | **Partial planning** (skip clarification, run Steps 2-6) |
| User gives detailed plan missing stack/team | **Light planning** (Steps 3-5 only) |
| User gives complete plan with everything | **Skip to /build** — tell user to run `/build` directly |

---

## Anti-Patterns

- **Over-planning**: Don't spend 2 hours planning a weekend project. Match planning depth to project complexity
- **Analysis paralysis**: If two options are close, pick one and document the trade-off. Don't optimize for perfection
- **Skipping PM discovery**: Even for "obvious" products, 5 minutes of problem definition prevents building the wrong thing
- **Ignoring constraints**: If the user said "use Python", don't recommend TypeScript. Respect stated constraints
- **Planning without validation**: Always present the plan for user approval before suggesting `/build`
- **Kitchen sink team**: Not every build needs 10 agents. A CLI tool might need only backend + qa + tech-lead

---

## Execute

Now read the user's idea from `$ARGUMENTS` and begin:

1. **Assess** — is this ready for /build, needs planning, needs discovery, or needs clarification?
2. **Discover** — PM: problem, users, MVP scope, user stories
3. **Design** — Architect: stack, components, data model, APIs, risks
4. **Validate** — Tech Lead: team selection with justification, workload distribution
5. **Compose** — assemble into build plan document
6. **Present** — show to user for approval
