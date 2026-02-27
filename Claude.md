# Project Context — jgcalice-agents

## What This Repo Is

A framework of **10 pre-specialized senior AI agents** that work together as a team to build digital products. This is not a runnable application — it's a set of agent definitions you load into Claude Code (agent teams), OpenClaw, or Cursor.

## Agents

| Agent | Path | Role |
|---|---|---|
| tech-lead | `agents/tech-lead/` | Orchestrator — coordinates all other agents |
| backend | `agents/backend/` | APIs, data models, business logic |
| frontend | `agents/frontend/` | Web UI, state, accessibility |
| mobile | `agents/mobile/` | iOS/Android, offline-first |
| architect | `agents/architect/` | System design, ADRs, trade-offs |
| qa | `agents/qa/` | Test strategy, automation, quality gates |
| devops | `agents/devops/` | CI/CD, infra, observability |
| designer | `agents/designer/` | UX/UI, flows, design system |
| pm | `agents/pm/` | Discovery, specs, roadmap |
| security | `agents/security/` | Threat model, auth, compliance |

## How to Run an Agent Team

1. Enable agent teams: copy `.claude/settings.json.example` → `.claude/settings.json`
2. Start Claude Code from the repo root: `claude`
3. Two paths depending on where you are:

**Path A — You have an idea but no plan:**
```
/plan Create a calendar assistant application
```
The PM, Architect, and Tech Lead collaborate to produce a structured plan. Then:
```
/build examples/calendar-assistant-plan.md
```

**Path B — You already have a detailed plan:**
```
/build examples/calendar-assistant-plan.md
```

## Key Files Per Agent

Every agent directory contains:

- `SOUL.md` — identity, quality bar, decision heuristics (**read every session**)
- `AGENTS.md` — communication protocols with other agents (**read every session**)
- `USER.md` — who you're helping (fill in per project)
- `MEMORY.md` — long-term decisions and lessons (**read every session**)
- `memory/` — daily session notes (`memory/YYYY-MM-DD.md`)
- `skills/{role}/SKILL.md` — operational playbooks and checklists
- `tasks/todo.md` — current task tracking
- `tasks/lessons.md` — patterns learned from corrections

## Plan Skill (New — Idea → Plan)

`/plan <idea-description>` — turns a vague idea into a build-ready plan:
1. **PM Discovery** — defines the problem, target user, MVP scope, user stories
2. **Architect Design** — chooses stack, designs components, data model, APIs, risks
3. **Tech Lead Validation** — selects and validates the right team with justification
4. Outputs a structured plan file ready for `/build`

Full guide: `skills/plan/SKILL.md`

## Build Skill (Plan → Working Product)

`/build <plan-path> [num-agents]` — orchestrates a full team build:
1. Reads the plan, extracts components and dependencies
2. **Validates team composition** (coverage, efficiency, risk checks)
3. Authors API contracts upfront (contract-first — no guessing between agents)
4. Spawns all agents in parallel via tmux split panes
5. Coordinates until all acceptance criteria pass

If the plan is vague, `/build` redirects to `/plan` instead of asking the user to fill gaps.

Full orchestration guide: `skills/build/SKILL.md`

## Examples

- `examples/calendar-assistant-plan.md` — complete build plan (ready for `/build`)
- `examples/trip-planner.md` — Telegram bot build plan (ready for `/build`)
- `examples/planning-flow-example.md` — shows how `/plan` transforms "Create a calendar assistant" into a complete plan

## Cursor Rules

`rules/` — Cursor rules that activate automatically by file context (test files → QA rule, Dockerfile → DevOps rule, etc.).

## OpenClaw Config

`openclaw-config.json5` — agent routing configuration for OpenClaw workspaces.

## References

- Claude Code agent teams: https://code.claude.com/docs/en/agent-teams
- OpenClaw docs: https://docs.openclaw.ai/
- Anthropic skills: https://github.com/anthropics/skills/tree/main/skills
- Custom skills guide: https://support.claude.com/en/articles/12512198-how-to-create-custom-skills
