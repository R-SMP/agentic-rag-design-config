# Cloud deploy runbook (Stage A — Railway)

This is the step-by-step the operator follows to put a Stage A
container on Railway behind the invite-code gate.  Scope: **Stage A
only** — single Streamlit pod, no DB writes, no R2 uploads.  Stage B
will append a "Database wiring" section to this same file; Stage C
will append "RAG retrieval".

The Railway project is pre-existing per the v2 supplement section 1:

  * Project name: ``MT-propeller-v11``
  * Project ID:   ``21efab95-e48d-423f-91a3-622fb10f796b``
  * Region:       EU-West (closest to the existing Azure Rhino
                  Compute VM target and to ETH).
  * Postgres:     already provisioned with pgvector; not used in
                  Stage A but kept warm so Stage B does not need a
                  separate provisioning step.
  * R2 bucket:    ``mt-propeller-v11-artefacts`` in EU
                  jurisdiction; unused in Stage A.

No new infrastructure is required to ship Stage A — only an
application service inside the existing project.

---

## 0. Pre-flight checklist (MUST do before any deploy)

These are NOT optional and they are NOT in the code.  Each one
costs nothing to do and prevents an expensive mistake.

### 0.1. Hard monthly spend caps on every LLM provider dashboard

Cross-ref: `TODO_known_issues.md` OPS1.

Set a **hard** monthly spend cap on each LLM provider used by the
Stage A stack BEFORE the cloud URL accepts any traffic.  These caps
are the floor against runaway costs from a leaked invite code, a
bug, a rogue session, or — most plausibly during a demo — a tab
left open overnight with an active conversation.

  * **OpenAI** → platform.openai.com → Settings → Billing → Limits
    → set a monthly budget that returns 429 when exceeded.
  * **Anthropic** → console.anthropic.com → Settings → Plans &
    Billing → Spend limits → set a monthly cap.
  * **Google** (only if any agent uses Google models) → the GCP
    project linked to the API key → Billing → Budgets & alerts →
    set a budget action that DISABLES the project at the cap, not
    just an email alert.

Recommended starting cap: **€50/month per provider**.  Adjust up
only when telemetry shows sustained legitimate burn against the cap.
A cap is the only thing that saves your credit card if the invite
code leaks; the auth gate is the second line of defence, not the
first.

**Do not skip this step even for a "five-minute test deploy".**
Five minutes with a leaked URL is enough for a scraper to discover
the auth gate and start brute-forcing it.

### 0.2. Generate the invite code

Pick a random 24-byte URL-safe token:

```sh
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

Save it somewhere durable (NordPass) — you will paste it into
Railway in section 2 and share it with invitees out of band.  Do
NOT commit it.  Do NOT paste it into chat.

### 0.3. Confirm LLM API keys are available

You need at least one of `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` in
NordPass and ready to paste.  Confirm they still work locally
before deploying — a deploy that fails because of an expired key
wastes a deploy iteration.

### 0.4. Decide what to do about Rhino Compute

Per the v3 project memory, the Azure Rhino Compute VM region is
not yet confirmed.  Two choices for the first Stage A deploy:

  * **Deploy without mesh generation.**  The chat surface works
    end-to-end (Receptionist + Orchestrator + Planner + UII
    extraction + DCIC parameter assembly + DCOI critique on
    placeholder data), but the moment any agent calls the
    ``generate_propeller_mesh`` tool the request will fail because
    the container cannot reach a Rhino Compute server.  Acceptable
    for an end-to-end UI smoke test; not acceptable for an actual
    propeller demo.

  * **Defer the deploy** until the Rhino Compute VM is up and the
    URL is known.  Then set `RHINO_COMPUTE_URL` on Railway in
    section 2 to point at it.

The runbook below assumes you have made this call.  Either way,
DO NOT leave `RHINO_COMPUTE_URL` defaulting to `localhost:6500`
on Railway — that points the container at itself, which the
container's own filesystem cannot serve.

---

## 1. Wire the GitHub repo into Railway

Railway can either (a) pull an image from `ghcr.io` or (b) build
from a GitHub repo on every push.  Stage A uses **(b)** — Railway
builds the image from the `Dockerfile` at the repo root on every
push to `main`.

1. Open the Railway project ``MT-propeller-v11``.
2. Click **+ New** → **GitHub Repo**.
3. Authorise the Railway GitHub app for the repo if not done already.
4. Select ``R-SMP/agentic-rag-design-config``.
5. In the resulting service settings → **Source** tab:
   * Branch: ``main``
   * Build method: **Dockerfile** (Railway auto-detects from the
     repo root ``Dockerfile`` — no override needed).
   * Watch paths: leave default (full repo) — every push to main
     triggers a rebuild.
6. Do NOT click "Deploy" yet — env vars are still missing.

---

## 2. Configure the service environment

In the new service's **Variables** tab, add each variable below.
Paste values from NordPass; for the long shared keys (OpenAI,
Anthropic), use the first-4 + last-4 convention to verify you
pasted the right one without the full secret hitting your
clipboard history twice.

Required for Stage A:

| Variable | Value source | Notes |
|---|---|---|
| ``INVITE_CODE`` | Generated in section 0.2 | The login gate refuses everyone when this is unset (fail-secure). |
| ``OPENAI_API_KEY`` | NordPass | At least one of OpenAI / Anthropic must be set. |
| ``ANTHROPIC_API_KEY`` | NordPass | |
| ``RHINO_COMPUTE_URL`` | The Azure VM's URL, OR omit entirely | Omit means "no mesh tool will work" — see 0.4. |
| ``RHINO_COMPUTE_API_KEY`` | NordPass (if the VM enforces an API key) | |
| ``PORT`` | Auto-injected by Railway | Do NOT set manually; the Dockerfile reads ``${PORT:-8501}``. |

Optional but recommended:

| Variable | Value source | Notes |
|---|---|---|
| ``GOOGLE_API_KEY`` | NordPass (if Google models are configured) | Deferred per the v3 project memory. |

Stage A does NOT use these (Stage B / C will):

| Variable | Stage |
|---|---|
| ``DATABASE_URL`` | Stage B (Railway Postgres auto-injects this) |
| ``R2_ACCOUNT_ID``, ``R2_ACCESS_KEY_ID``, ``R2_SECRET_ACCESS_KEY``, ``R2_BUCKET_NAME`` | Stage B (R2 binary uploads) |
| ``STORAGE_BACKEND`` | Stage B (the default ``files`` is fine until then) |

After saving, the service auto-restarts.  Wait for the first
deploy to complete (3–5 min — Docker build + pip install).

---

## 3. First deploy + smoke test

1. **Watch the build log** in Railway → service → Deployments →
   latest deploy → View logs.  The lines you expect to see in
   order:
     * ``Successfully installed`` for every project dep (the long
       line ending in ``streamlit-...``).
     * ``Uvicorn server started on 0.0.0.0:8501`` (Streamlit
       startup banner).
     * ``You can now view your Streamlit app in your browser.``
     * The Local / Network / External URL lines.

   If any of those is missing OR if there is a Python traceback
   above them, fix the underlying issue (env var typo, broken
   requirement, etc.) — do NOT just re-deploy hoping it goes away.

2. **Open the public URL.**  Railway → service → Settings →
   Networking → "Public Networking" section → copy the
   ``*.up.railway.app`` domain.

3. **Verify the invite-code gate.**  The page should load showing
   the title, a "one user at a time" caption, and a password-style
   input.  Submit a deliberately WRONG code first: you should see
   the rejection message.  Then submit the real code: the chat
   surface should appear with the sidebar showing the new session
   id and the End Session button.

4. **Verify a chat turn (no Rhino Compute required).**  Send a
   message like ``hello`` — the Receptionist should reply directly
   without forwarding into the pipeline.  Confirm:
     * The assistant bubble renders.
     * The session log file exists in the container.  Use Railway's
       shell (Service → ⋯ menu → "Open shell") and ``ls /app/logs/``
       — you should see one ``streamlit_<id>.log`` and one
       ``agent_flow_*.txt``.

5. **Verify End Session.**  Click the sidebar button — the page
   should reset to the gate and re-prompt for the invite code.

If all five pass, Stage A is live.

---

## 4. Operational notes

### Redeploys

Push to ``main`` → Railway automatically rebuilds and rolls out
the new image.  In-flight Streamlit sessions are NOT preserved
across deploys (Stage A's session state lives in process memory
— see ``cloud_architecture_notes.md`` C4).  Schedule deploys for
times when no invitee is actively demoing.

### Killing a runaway deploy

If costs spike or an invitee reports the URL is leaked:

  1. **Rotate the invite code FIRST.**  Set a new ``INVITE_CODE``
     value in Railway → Variables → Save.  The service restarts;
     active sessions are dropped.  This locks out anyone with the
     old code immediately.
  2. **Then notify legitimate invitees** of the new code out of
     band.
  3. If you suspect more than a code leak (e.g. an LLM key was
     scraped from a log), **rotate the LLM keys in the provider
     dashboards** AND replace them in Railway Variables.

### Pausing / sleeping the service

Railway → service → Settings → Danger Zone → "Pause Service".
Useful if you are away for the weekend and want zero idle cost
even on the Hobby plan.  Resume via the same panel.

### Reading logs

Railway → service → Deployments → latest → View logs.  Streamlit
writes to stdout, so every ``[STREAMLIT]`` line from
``streamlit_app.py`` and every ``[RECEPTIONIST]`` /
``[DISPATCH]`` line from ``agents/dispatch.py`` appears there in
real time.  Per-session log files inside the container (``/app/
logs/streamlit_*.log``) are also accessible via the in-Railway
shell but do not survive a redeploy.

### Custom domain (deferred)

Stage A ships on the ``*.up.railway.app`` provider subdomain (see
``cloud_architecture_notes.md`` C5).  Buy a custom domain only
when one of the C5 triggers fires (manuscript link, Cloudflare
Access upgrade, public talk).  Migration is ~30 min when the
trigger fires.

---

## 5. What this runbook does NOT cover (yet)

These sections will be appended in later stages, in order:

  * **Stage B.**  Wiring ``DATABASE_URL`` into the running service,
    running the migration scripts (``db/migrations/001_initial_
    schema.sql`` + 002 + 003), provisioning R2 credentials onto
    Railway, exercising the Save button → DB → R2 path.
  * **Stage C.**  Wiring the RAG retrieval layer (the
    ``AgentQueryTool`` plumbing) into the chat surface.  No new
    infra; just code paths + env var documentation.

Both will reuse the project + service created in this runbook —
section 1 / 2 / 3 / 4 above stay valid; they just gain extra
required env vars and extra smoke-test items.
