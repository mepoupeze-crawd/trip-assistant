# Calendar Assistant — Build Plan (MVP)

## What We're Building

A **web app + AI assistant** that helps users manage their calendar using natural language:

* Create, edit, and delete events by typing or speaking naturally ("Schedule lunch with Ana next Friday at noon")
* View a smart weekly/monthly calendar with conflict detection
* Get scheduling suggestions based on availability and preferences
* Sync with Google Calendar (read + write)
* Receive reminders via browser notification or email

---

## Why

Existing calendar tools require too many clicks and form fields. This assistant reduces friction by letting users describe what they want in plain language and handling the translation to calendar events automatically.

---

## Stack

* **Frontend**: Next.js (App Router) + TypeScript + Tailwind CSS
* **Backend**: Next.js API Routes (fullstack, same repo)
* **Database**: PostgreSQL (Neon) with Prisma
* **AI**: Claude API (claude-haiku-4-5-20251001) for NLP → event parsing
* **Auth**: NextAuth.js with Google OAuth (needed for Calendar API)
* **Calendar Sync**: Google Calendar API (via googleapis SDK)
* **Email**: Resend for reminder emails
* **Deploy**: Vercel (1 app, preview deployments)

---

## Components

### 1) Database Layer (PostgreSQL)

Tables:

* `users`: id, email, name, google_access_token, google_refresh_token, timezone, created_at
* `events`: id, user_id, google_event_id, title, description, start_at, end_at, location, is_all_day, recurrence_rule, created_at, updated_at
* `reminders`: id, event_id, user_id, remind_at, channel (`email` | `browser`), sent_at, created_at
* `chat_messages`: id, user_id, role (`user` | `assistant`), content, event_id (nullable, linked if message created/edited an event), created_at

### 2) Backend (Next.js API Routes)

Auth:
* `GET /api/auth/[...nextauth]` — NextAuth Google OAuth handler
* `GET /api/me` — current user + timezone

Calendar:
* `GET /api/events` — list events (query params: start, end, search)
* `POST /api/events` — create event (syncs to Google Calendar)
* `GET /api/events/:id` — event detail
* `PUT /api/events/:id` — update event (syncs to Google Calendar)
* `DELETE /api/events/:id` — delete event (syncs to Google Calendar)
* `POST /api/events/sync` — pull latest from Google Calendar into DB

AI Assistant:
* `POST /api/chat` — send a message; AI parses intent and returns structured action + natural language reply
  * Intent types: `create_event`, `edit_event`, `delete_event`, `query_events`, `suggest_time`, `unknown`
  * Response: `{ reply: string, action: { type, payload } | null }`

Reminders (cron):
* `POST /api/cron/reminders` — send due reminders (called by Vercel cron)

### 3) Frontend (Web)

Pages:
* `/` — redirect to `/calendar`
* `/login` — Google sign-in button
* `/calendar` — main view: weekly/monthly calendar grid + chat sidebar
* `/calendar/event/new` — form for manual event creation
* `/calendar/event/[id]` — event detail + edit form
* `/settings` — user timezone, notification preferences

UI States (required for every data-fetching component):
* loading skeleton, empty state, error with retry, success

Chat sidebar states:
* idle, typing, processing (AI thinking), action preview (before confirming), confirmed, error

### 4) Infra / Operations (minimum)

* 1 Vercel project (auto preview deployments from PRs)
* Neon PostgreSQL (free tier for MVP)
* Vercel cron job for reminder sending (`/api/cron/reminders` every 5 min)
* Environment variables: `DATABASE_URL`, `NEXTAUTH_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ANTHROPIC_API_KEY`, `RESEND_API_KEY`

---

## Dependencies Between Components

```
DB schema (Prisma) → API routes (CRUD)
Google OAuth (NextAuth) → Calendar API access (google_access_token)
Calendar API contract → Frontend calendar grid + chat action handler
AI /api/chat response shape → Frontend chat sidebar action confirmation flow
Reminder schema → Cron job + email templates
```

---

## Acceptance Criteria (MVP)

1. User signs in with Google and sees their existing Google Calendar events on the grid
2. User types "Schedule a call with João tomorrow at 3pm" and the assistant creates the event on Google Calendar (appears on grid within 5 seconds)
3. User types "What do I have on Thursday?" and gets a natural language summary
4. User manually creates/edits/deletes an event via form — syncs bidirectionally with Google Calendar
5. User receives a reminder email 15 minutes before an event
6. Calendar grid shows conflict highlight when two events overlap
7. App works on mobile (responsive, no horizontal scroll)

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Google OAuth token expiry | High | Use refresh_token flow; store encrypted tokens |
| AI parses event incorrectly (wrong date/time) | High | Show action preview to user before confirming; let user edit |
| Google Calendar rate limits | Medium | Cache events locally in DB; sync on demand + on login |
| Timezone confusion | High | Store all times as UTC; display in user's local timezone (from `users.timezone`) |
| Reminder cron misses events | Medium | Log all cron runs; idempotent send (check `sent_at` before sending) |

---

## Validation

### Local Setup

```bash
npm install
cp .env.example .env.local  # fill in Google, Anthropic, Resend keys
npx prisma migrate dev
npm run dev
```

### Quick API Checks

```bash
# Create event via AI chat
curl -s -X POST http://localhost:3000/api/chat \
  -H "Content-Type: application/json" \
  -H "Cookie: next-auth.session-token=<your-token>" \
  -d '{"message": "Schedule team standup every weekday at 9am"}'

# List events
curl -s "http://localhost:3000/api/events?start=2026-02-01&end=2026-02-28" \
  -H "Cookie: next-auth.session-token=<your-token>"
```

### Manual E2E (10 minutes)

1. Sign in with Google → calendar grid loads with existing events
2. Type "Lunch with Maria on Friday at 1pm" → preview shown → confirm → event appears on grid and in Google Calendar
3. Click the new event → edit title → save → confirm change in Google Calendar
4. Type "What's on my calendar this week?" → get accurate summary
5. Delete event via grid → confirm removed from Google Calendar
6. Check reminder email arrives ~15 min before a test event
