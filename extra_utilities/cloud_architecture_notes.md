# Cloud architecture notes (v2 cloud migration)

This file records every infrastructure decision made for the v2
migration from a local-only `python main.py` REPL to a cloud-hosted
multi-user web service. It is the authoritative reference for hosting,
frontend, auth, session state, and domain choices.

For database-specific decisions, see `database_design_notes.md`.
For runtime invariants, see `warnings_developer.md`.
For open issues and planned enhancements, see `TODO_known_issues.md`.

---

## C1. Backend hosting: Railway

**Choice.** The multi-agent FastAPI process runs on **Railway**
(Hobby plan, ~$5/mo credit + pay-as-you-go).

**Why.** Fastest path to a deployed service; one platform hosts the
backend, Postgres, and Redis together; GitHub auto-deploy on push to
`main`; idle cost is genuinely low for an MVP. Railway Postgres
includes pgvector, which the database design needs.

**Stack co-locations on Railway.**
- FastAPI backend (also serves Streamlit — see C2).
- Railway Postgres (pgvector ≥ 0.5, HNSW from day one).
- Railway Redis (lightweight `session_id` routing only — see C4).
- GitHub Container Registry (`ghcr.io`) for Docker images.
- Cloudflare R2 (separate account) for binary artefacts (renders,
  OBJs, future static assets).

**Migration path to production.** When Railway's single-pod
constraints or pricing become limiting, the documented production
target is **Azure Container Apps + Azure Database for PostgreSQL
Flexible Server + Azure Cache for Redis + Azure Blob Storage**. The
schema and code do not need to change — only environment variables
and the deployment target. Defer this migration until usage justifies
~€60–90/mo baseline cost.

---

## C2. Frontend: Streamlit served by FastAPI

**Choice.** Frontend is **Streamlit**, served by the same FastAPI
process that runs the agent loop. No separate frontend host.

**Why.** All-Python (matches the rest of the stack), 1–2 days to
prototype, no separate deploy, no JS/CSS knowledge required. Looks
"internal-tool" but acceptable for thesis-stage demos.

### Streamlit limitations to watch for

These are the symptoms that, when they start to bite, signal that the
Streamlit phase has run its course:

1. **Whole-script re-run on every interaction.** Streamlit re-executes
   the entire Python script every time the user clicks anything. State
   has to be persisted via `st.session_state` carefully; otherwise
   work-in-progress is lost. Long agent loops cannot run synchronously
   inside the script — they have to be backgrounded with threads or an
   external task queue, with progress streamed back via `st.empty()`
   placeholders.
2. **Multi-user concurrency.** One Streamlit server process serves all
   users, but the script-rerun model means concurrent users can step on
   each other's `st.session_state` if not isolated by user-keyed
   namespacing. Heavy concurrent load is not Streamlit's strength.
3. **Opinionated layout.** Single-column-by-default. Multi-pane
   dashboards (chat on the left, render on the right, parameters on
   top) are achievable with `st.columns` and `st.tabs` but require
   fighting the framework. Custom widgets need third-party components
   or `streamlit.components.v1.html` escapes.
4. **URL / state coupling.** Streamlit's URL doesn't reflect app state
   well. Deep links ("share this specific session view") require manual
   query-param plumbing.
5. **Mobile.** Mediocre out of the box. Touch interactions and small
   screens don't get the same polish as desktop.
6. **Long-running tasks.** Agent dispatch loops that take minutes need
   careful background-task patterns (threads + polling, or an external
   queue) to avoid blocking the script's UI thread. The cleanest
   pattern is: agent loop runs in FastAPI background tasks; Streamlit
   polls a status endpoint for progress updates.
7. **Look-and-feel.** "Made with Streamlit" badge in the footer; styling
   options are limited to a theme config plus CSS injection escapes. Not
   a problem for thesis demos; a problem for paper figures or public
   product launches.
8. **Auth integration awkwardness.** Streamlit's session model doesn't
   pair cleanly with traditional cookie-based auth. A FastAPI middleware
   that gates HTTP requests sits *in front of* Streamlit, which works,
   but in-app concepts like "the current user's identity" need to be
   passed via headers or query params explicitly.

### Future migration: HTMX with FastAPI templates

Migrate to HTMX-driven Jinja templates served by the same FastAPI
process when **two or more** of the limitations above start to bite
on real usage. Specifically, HTMX with FastAPI templates solves:

- **Per-interaction granularity.** HTMX swaps individual DOM fragments
  (`hx-post="/turn"` returns just the chat-bubble HTML, not the whole
  page). No script re-run. State stays put.
- **True multi-user concurrency.** FastAPI handles each request
  independently in its own request context; users are isolated by
  default.
- **Free layout.** You write the HTML and CSS. Multi-pane dashboards,
  custom widgets, mobile-friendly responsive design are all standard.
- **Stable URLs.** Each route has its own URL; deep linking is trivial.
- **Better long-running task UX.** Server-Sent Events (`hx-sse`) or
  WebSockets stream progress directly into the page without polling.
- **Cleaner auth.** FastAPI's `Depends(...)` injection naturally fits
  cookie-based auth or header-based gates. Identity flows through the
  same path as everything else.

Effort: 4–7 days from a working Streamlit MVP. Not urgent — defer
until Streamlit limitations become real friction, not theoretical.

---

## C3. Auth: shared invite code + per-IP rate limit

**Choice.** v2 ships with **(b) shared invite code** as the primary
gate, plus **(c) per-IP rate limit** (`slowapi` FastAPI middleware) as
defence-in-depth. Both are implemented in our own code; no external
auth provider is integrated yet.

**Why.** ~2 hours of work, kills 99% of token-drain risk, no external
dependency, no custom domain required, no user management overhead.
Sufficient for thesis-stage and small invited groups.

### Problems with shared invite code

These are real and worth understanding before relying on it:

1. **Code can leak.** Anyone you give the code to can pass it to anyone
   else, with no record. Once shared widely (in a Slack channel, a
   screenshot, an accidental commit), the code is effectively public
   until rotated.
2. **No per-user accountability.** All sessions look identical from
   the server's perspective. You cannot tell which session belonged to
   which person, which complicates debugging ("who ran the session that
   filed bug #3?") and prevents per-user usage analytics.
3. **No per-user rate limits.** Rate limits run per IP. One enthusiastic
   demo user behind the same NAT as you can hit IP limits and lock you
   out of your own app.
4. **Rotation is a hassle.** Changing the code requires notifying
   everyone with the old code through a separate channel (email, Slack).
   No graceful overlap window unless you implement multi-code support
   manually.
5. **No audit trail.** Cannot reconstruct "which user did what" after
   the fact for compliance or incident-response purposes.
6. **No selective revocation.** Cannot revoke access for one specific
   person without rotating the code for everyone.
7. **No identity for personalisation.** Cannot offer "your past
   sessions" or per-user preferences because there is no user identity.

### Other available solutions (in order of upgrade complexity)

When the limitations above start to bite, these are the upgrade options:

- **(a) No gate.** Listed for completeness only. Genuinely dangerous
  with billed LLM APIs behind the URL. Do not use.
- **(b) Shared invite code** — current choice. See above.
- **(c) Per-IP rate limit** — already wired alongside (b).
- **(d) Cloudflare Access** — free service, puts a Cloudflare-hosted
  login wall in front of the app. Email magic-link, Google/Microsoft
  SSO. Requires a custom domain on Cloudflare DNS. Real auth, real
  audit trail, no auth code in the app. **Right next step** when the
  app is publicly linkable. ~30 min setup once a custom domain is in
  place.
- **(e) Clerk free tier.** Drop-in user-management SDK. Free up to 10k
  monthly active users. Provides email/password, magic links, OAuth,
  password resets, user list, etc. ~2–4 hours to integrate. Right
  choice when the app needs real user accounts (per-user history pages,
  per-user preferences, billing-per-user). Overkill for thesis stage.
- **(f) Auth0 free tier.** Similar to Clerk, more enterprise-flavoured.
  Pick if there is a specific Auth0 reason; otherwise Clerk is more
  modern.
- **(g) Roll-your-own.** Don't.

### Independent of the auth choice

**Hard monthly spend caps must be set in the OpenAI, Anthropic, and
Google AI dashboards** before any cloud deploy. This is the absolute
floor against runaway costs and is independent of every auth choice.
If a future auth path fails open, the spend cap is what saves you.
Set the cap to a number you would be okay losing entirely.

---

## C4. Session state: Option A (in-process memory) with
serialisation-ready design

**Choice.** v2 keeps every active session's agent state in **process
RAM** as plain Python objects, indexed by `session_id` in a
module-level `dict[session_id, Session]`. Redis is used only for the
`session_id` cookie/routing, not for session state itself.

**Why.**
1. Railway MVP is one backend pod. Multi-pod is not on the table.
2. v2 development will involve constant deploys; a session lost
   mid-conversation is annoying but not data-loss — saved sessions go
   to Postgres at quit time, not mid-session.
3. Option A is simpler to reason about while we are still figuring out
   where every piece of session state actually lives.

### Day-one design rule

**Agent state must be plain data — JSON-serialisable from day one.**
Specifically:

- Every agent's `messages` list lives as already-serialisable LangChain
  messages (`BaseMessage` subclasses, all of which support `.dict()` /
  `.parse_obj()`).
- No live LLM client references inside the snapshot. LLM clients live
  in a **process-wide cache** built once at FastAPI startup and looked
  up by `(provider, model)` key.
- All other per-agent state (`_pending_hop`, `_pending_image_blocks`,
  `_pending_image_paths`, `cycle_start_ts`, current attempt id, etc.)
  is captured as plain data alongside `messages`. This ties into TODO
  `O4` in `TODO_known_issues.md`.
- The `Session` class exposes `Session.to_dict()` and
  `Session.from_dict(data, llm_clients)` symmetric methods. The
  in-memory store today never calls them; it just holds live objects.

With that shape, the storage layer is swappable:

```python
# Today (Option A — in-memory):
def load_session(session_id: str) -> Session:
    return _IN_MEMORY[session_id]

def save_session(session: Session) -> None:
    _IN_MEMORY[session.session_id] = session

# Tomorrow (Option B — Redis-serialised):
def load_session(session_id: str) -> Session:
    blob = redis.get(f"session:{session_id}")
    if blob is None:
        raise SessionExpiredError(session_id)
    return Session.from_dict(json.loads(blob), LLM_CLIENT_CACHE)

def save_session(session: Session) -> None:
    redis.setex(
        f"session:{session.session_id}",
        SESSION_TTL_SECONDS,
        json.dumps(session.to_dict()),
    )
```

Same agent code, same `Session` class, same FastAPI handlers.

### Future migration: Option B — Redis-serialised sessions

Trigger to migrate: when **any one** of these is true:

- Restart-safety becomes important (you stop wanting to nuke in-flight
  sessions on every deploy).
- You scale beyond one Railway pod.
- RAM pressure becomes real (active sessions × per-session message
  history > available process memory).
- You want a natural per-session TTL ("expire sessions after 24h
  inactivity") which Redis provides for free.

How to construct it (sketch — to be implemented later):

1. **Library.** `redis-py` (already a Railway-recommended client).
   Connection string from `REDIS_URL` env var, which Railway provisions
   automatically when you attach a Redis service.
2. **Serialiser.** `json.dumps(session.to_dict())`. JSON is enough at
   this scale; switch to msgpack only if profiling shows it matters.
3. **TTL.** `redis.setex(key, SESSION_TTL_SECONDS, blob)` — start at
   24h, tune from observed inactivity patterns.
4. **Key pattern.** `session:<session_id>` for the state blob. Keep
   `session_id` in a secure HTTP-only cookie on the user's browser.
5. **LLM client cache.** Already needed in Option A; survives unchanged.
   Build at FastAPI startup, reference in `Session.from_dict()`.
6. **Sanitisation invariant** (carries from Option A): every snapshot
   contains plain data only. No `httpx.Client`, no `langchain_openai.
   ChatOpenAI`, no file handles, no live anything.
7. **Pickle pitfalls** (only relevant if you ever swap JSON for pickle):
   `BaseMessage` instances pickle, but LLM clients and tool bindings do
   not. Test before committing to pickle.
8. **Backward compatibility.** When migrating, deploy code that can
   read either backend; populate Redis on first turn after deploy;
   cut over fully once all active sessions have been re-saved.

Effort estimate: 1 day if the Option-A `Session` class was built
correctly. The migration is a load/save swap, not an agent refactor.

---

## C5. Domain: Railway provider subdomain

**Choice.** v2 ships on Railway's **provider subdomain**
(`*.up.railway.app`). No custom domain purchased.

**Why.** Free, immediate, requires no DNS work, sufficient for
thesis-stage internal sharing.

### When to migrate to a custom domain

Buy a custom domain (~€10–15/year at Cloudflare Registrar, Namecheap,
Porkbun, or gandi.net) when **any one** of these triggers fires:

1. The URL needs to appear in the thesis manuscript, a paper, or a
   public talk.
2. You want to enable **Cloudflare Access** (auth option `(d)` in C3),
   which does not work cleanly with provider subdomains.
3. The audience grows beyond a small invited group and a memorable
   URL becomes worth the small annual cost.
4. You want to put it on a CV / portfolio page.
5. Email links sent to users need a stable, on-brand domain.

### What a custom domain solves

- **Professional appearance.** `https://propellerconfig.ch` reads as a
  real product; `https://your-project-prod-abc1.up.railway.app` reads
  as a Railway test deployment.
- **Stability.** Provider subdomains are tied to Railway's URL scheme
  and platform. Migrating off Railway later means every link breaks.
  A custom domain travels with you across hosts.
- **Cloudflare Access compatibility.** Most hosted-auth services
  require a domain you control on Cloudflare DNS or similar. Custom
  domain unlocks (d).
- **Memorability.** A real domain is shareable verbally; a provider
  subdomain is not.
- **Branded email.** Once the domain exists you can also issue
  `support@<domain>` for transactional / contact email later.
- **HTTPS handling stays trivial.** Railway issues Let's Encrypt
  certificates automatically for verified custom domains; no manual
  cert work required.

### Migration steps when triggered

1. Buy the domain at Cloudflare Registrar (sells at-cost; ~€10–12/year
   for `.ch`, `.com`, `.app`).
2. In Railway: project settings → "Custom domain" → enter the domain.
3. Add the CNAME record at Cloudflare DNS that Railway tells you to
   add.
4. Wait for DNS propagation (usually <1h).
5. Railway issues HTTPS automatically.
6. Update internal references (env vars, README, any hard-coded base
   URLs).

Effort: ~30 min when the trigger fires. Not worth doing in advance.

---

## Quick-reference: the v2 stack

| Layer | Choice |
|---|---|
| Backend host | Railway (Hobby) |
| Backend framework | FastAPI |
| Frontend | Streamlit served by the FastAPI process |
| Postgres | Railway Postgres (pgvector ≥ 0.5, HNSW from day one) |
| Redis | Railway Redis (`session_id` routing only in Option A) |
| Object storage | Cloudflare R2 |
| Container registry | ghcr.io |
| Source / CI | GitHub + GitHub Actions (CI added later) |
| Image build | Manual from laptop initially |
| Secrets | Railway env vars |
| Mesh backend | Existing Azure Windows VM (Rhino Compute) |
| LLM APIs | OpenAI + Anthropic + Google, hard monthly spend caps |
| Embedding model | OpenAI `text-embedding-3-large` @ 1024 dims |
| Auth | Shared invite code + per-IP rate limit (`slowapi`) |
| Session state | In-process Python dict, serialisation-ready design |
| Region | EU (closest to ETH and Rhino Compute VM) |
| Domain | Railway provider subdomain (`*.up.railway.app`) |
| Logging | Existing log-file infra (deferred per Cloud Services sheet) |
| Scheduled jobs | None for MVP |
