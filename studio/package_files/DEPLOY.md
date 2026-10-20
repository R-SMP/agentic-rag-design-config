# Deploying: {{TITLE}}

This folder is the multi-agent system for the {{DC}}, made with the MAS
Studio on {{MADE}} (engine {{ENGINE}}; {{VALIDATE}}).

It runs as one web app, which the `Dockerfile` builds.  The steps below put
it on Railway from a private GitHub repository, in about 20 minutes the
first time.  You need a GitHub account, a Railway account and an OpenAI API
key.

## 1. A private GitHub repository

In this folder, `python -m studio prepare` checks it first (Validate, what
git must leave out, anything that looks like a key) and prints these
commands; it never runs them itself:

    git init -b main
    git add .
    git commit -m "{{TITLE}}"
    gh repo create {{NAME}} --private --source . --push

Without the GitHub CLI (`gh`): create an empty private repository on
github.com, then run `git remote add origin <its address>` and
`git push -u origin main`.

`.env` is in `.gitignore`: the keys you keep there never reach GitHub.

## 2. A Railway service

1. On railway.com: **New Project → Deploy from GitHub repo**, and choose the
   repository.  Railway finds the `Dockerfile` and builds it (3–5 minutes).
2. In the service: **Settings → Networking → Generate Domain**.  That is
   your app's address.
3. Keep **one** replica: the app keeps the running session in its memory.

Every push to the repository's main branch builds and starts the app again.

## 3. Its variables

In the service: **Variables**.  Railway sets `PORT` itself: leave it out.

| Variable | Needed | What it is |
|---|---|---|
| `INVITE_CODE` | yes | The code people type to open the app and its MAS Studio.  **Without it there is no code at all: anyone with the address can use the app, and your API keys, and run code in the Studio.**  Make one with `python -c "import secrets; print(secrets.token_urlsafe(24))"`. |
| `OPENAI_API_KEY` | yes | The agents use OpenAI models unless you change them in Workflow Settings. |
| `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER_API_KEY` | for their models | Only for agents you switch to those providers in Workflow Settings. |

The tools of this setup:

{{TOOL_VARIABLES}}

Changing a variable restarts the app.  `.env.example` lists every variable
the app reads, with a note on each.

## 4. Check it

Open the address: its start page offers the configurator and the MAS
Studio (`/studio/`, on a copy of this setup).  Open the configurator, type
the invite code and ask for a design.  The first answer takes a minute or
two.  Railway shows the app's log under **Deployments → View logs**.

## Optional

### Keep past sessions: a volume

The app keeps finished sessions in `/app/previous_sessions`; without a
volume they are lost at the next deploy.  In the service: **Settings →
Volumes → New Volume**, mounted at `/app/previous_sessions`.

### A database: past designs, and search over them

1. Add a PostgreSQL database with the pgvector extension to the project
   (on Railway, a Postgres template with pgvector).
2. In the app's **Variables**, add `DATABASE_URL` as a reference to the
   database's `DATABASE_URL`.
3. Create the tables once, from your computer: put the database's
   `DATABASE_PUBLIC_URL` (its **Variables** tab) in `.env`, then run

       python extra_utilities/db_design/apply_schema.py extra_utilities/db_design/database_PostgreSQL_schema_v10.sql

4. In the app: **Workflow Settings › Database › Upload parameter schema**.
5. Search over past designs with their pictures needs `VOYAGE_API_KEY`;
   the pictures and models saved with a session go to Cloudflare R2:
   `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
   `R2_BUCKET_NAME`.

### Reading text in pictures (OCR)

Set `GOOGLE_CLOUD_VISION_API_KEY`: a Google Cloud key with the Vision API
enabled, not the same key as `GOOGLE_API_KEY`.

## Run it on your own computer

With Docker: copy `.env.example` to `.env` and fill it in, then run
`docker compose up --build app` and open http://127.0.0.1:8501/.

Without Docker, with Python 3.13 and Node (some tools also need the system
libraries the `Dockerfile` installs):

    pip install -r requirements.txt -r requirements-web.txt
    npm install
    uvicorn web_app:app --port 8501

## Change the configurator later

    python -m studio

opens the MAS Studio on `dc_pack/` at http://127.0.0.1:8770/.  Change what
you need, press **Validate**, then commit and push: Railway deploys the new
version.
