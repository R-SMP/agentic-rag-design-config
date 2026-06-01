"""Centralized path and infrastructure configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load root .env for shared infrastructure config
load_dotenv(Path(__file__).parent / ".env")

PROJECT_ROOT = Path(__file__).parent

# Tools base directory
TOOLS_DIR = PROJECT_ROOT / "tools"

# generate_mesh tool — only the Grasshopper definition lives in the
# tool directory; mesh outputs and parameter inputs are no longer
# stored under tools/.  Each design generation owns an attempt folder
# under ATTEMPTS_DIR (see below) which is the canonical home for
# parameters.json, propeller_mesh.obj, and render_*.png.
GH_DEFINITION_PATH = TOOLS_DIR / "generate_mesh" / "Propeller_Raul_V1.2.gh"

# User inputs.  Optional images live in INPUT_IMAGES_DIR; each
# ``<name>.png``, ``<name>.jpg``, or ``<name>.jpeg`` MUST be paired
# with ``<name>_note.txt`` describing what the image represents.
# The pairing is enforced by the Receptionist before the pipeline
# ever runs.
USER_INPUTS_DIR = PROJECT_ROOT / "inputs"
INPUT_IMAGES_SUBDIR = "input_images"
INPUT_IMAGES_DIR = USER_INPUTS_DIR / INPUT_IMAGES_SUBDIR

# Logs
LOGS_DIR = PROJECT_ROOT / "logs"

# Per-attempt folders (one per design generation): top-level so
# they're easy to inspect and so the loader can archive them
# wholesale at session end alongside the logs.
ATTEMPTS_DIR = PROJECT_ROOT / "attempts"

# Archived sessions
PREVIOUS_SESSIONS_DIR = PROJECT_ROOT / "previous_sessions"

# Database — populated by the Database Handler at end of session, used
# later for RAG.  Each saved session is one folder named after the
# archived session (e.g. ``ID007_20260502_143015``); inside it, one
# subfolder per agent and inside each agent folder one ``.txt`` file
# per question with the DH's question and the agent's answer.
DATABASE_DIR = PROJECT_ROOT / "database"

# RhinoCompute
RHINO_COMPUTE_URL = os.getenv("RHINO_COMPUTE_URL", "http://localhost:6500/")
RHINO_COMPUTE_API_KEY = os.getenv("RHINO_COMPUTE_API_KEY", "")

# PostgreSQL — Railway-hosted, pgvector enabled.  Schema lives in
# ``extra_utilities/db_design/database_PostgreSQL_schema_v4.sql``;
# architecture notes in ``database_and_RAG_architecture.md``.
#
# In production on Railway the service receives DATABASE_URL via
# reference variable, pointing at the in-cluster internal hostname
# (postgres.railway.internal:5432).  For local development the
# repo-root ``.env`` should also set DATABASE_PUBLIC_URL, the
# Railway TCP-proxy URL (zephyr.proxy.rlwy.net or similar) that
# resolves from a developer laptop.
#
# Both default to empty strings so a checkout without Postgres
# configured still imports cleanly — ``agents/shared/postgres_pool``
# treats empty URL as "Postgres disabled" and degrades gracefully.
DATABASE_URL = os.getenv("DATABASE_URL", "")
DATABASE_PUBLIC_URL = os.getenv("DATABASE_PUBLIC_URL", "")
