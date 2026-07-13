# Stage A image for the Propeller Design Configurator web app.
#
# Layers:
#   1. python:3.13-slim base (matches the project venv per W15).
#   2. System libs for pyrender / trimesh headless rendering.
#      Required even when no mesh is generated at runtime because
#      ``tools/__init__.py`` imports ``render_mesh.py`` at module
#      load time, which imports pyrender unconditionally.
#   3. Project requirements (installed before app code so docker
#      can cache the dep layer when only source changes).
#   4. Project source (filtered by .dockerignore — see that file
#      for what NEVER goes into the image).
#
# CMD: uvicorn serves the FastAPI + JS web app (web_app:app) on
# ${PORT} (Railway sets this) or 8501 locally.  Single worker only
# — web_app.py holds in-process session state and an in-process SSE
# viz bus, so >1 worker would split state and break the live viewer.
#
# Stage A scope: no DB, no R2.  The DATABASE_URL / R2 env vars
# referenced by docker-compose.yml are accepted but unused — they
# come into play in Stage B.  See extra_utilities/cloud_
# architecture_notes.md C6 for the Stage A vs Stage B button-
# labelling discipline and warnings_developer.md W14 for the
# matching code-side rule.

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYOPENGL_PLATFORM=osmesa

# System packages:
#   * libgl1 / libglu1-mesa / libosmesa6 — pyrender's OpenGL stack.
#     PYOPENGL_PLATFORM=osmesa above selects the software-renderer
#     so a GPU is not required.
#   * libxext6 / libsm6 / libxrender1 — pyglet's X-fallback bits
#     pulled in by the pyrender import chain even when OSMesa is
#     the active backend.
#   * libgomp1 — runtime for numpy/trimesh's OpenMP loops.
#   * curl — used by the HEALTHCHECK below.
#   * nodejs / npm — Node runtime for the headless FEG geometry backend
#     (tools/generate_mesh/feg_export.mjs runs web/feg/* via Node + three,
#     when GEOMETRY_BACKEND="feg" or as the RhinoCompute fallback).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglu1-mesa \
        libosmesa6 \
        libxext6 \
        libsm6 \
        libxrender1 \
        libgomp1 \
        curl \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dep layer first so source-only changes do not invalidate the
# (slow) pip install.  requirements-web.txt adds the FastAPI/uvicorn
# stack web_app.py needs — it is the Railway entry point now, so
# these are no longer "local only" deps.
COPY requirements.txt requirements-web.txt ./
RUN pip install -r requirements.txt -r requirements-web.txt && \
    # pyrender 0.1.45 pins ``PyOpenGL==3.1.0`` exactly — a 2014
    # release whose OSMesa bindings are incomplete and miss
    # ``OSMesaCreateContextAttribs``, which breaks offscreen
    # rendering when ``PYOPENGL_PLATFORM=osmesa`` (the env var set
    # below).  PyOpenGL 3.1.10 has identical surface for everything
    # pyrender uses, plus the missing OSMesa symbol.  ``--no-deps``
    # is required because pip's resolver would otherwise honour
    # pyrender's ``==3.1.0`` pin and refuse the upgrade.  See
    # requirements.txt comments around the pyrender line for the
    # full reasoning.
    pip install --no-deps --upgrade PyOpenGL==3.1.10

# Node dependency layer: the FEG geometry backend's only npm dep is
# ``three`` (pinned in package.json to match the browser CDN import map).
# Copied before the app source so it caches independently of code changes;
# node_modules is dockerignored, so THIS install — not the developer's
# local tree — is what ships in the image.
COPY package.json ./
RUN npm install --omit=dev && npm cache clean --force

# Application code.  .dockerignore filters out .venv, .git, node_modules,
# logs/, attempts/, previous_sessions/, database/, inputs/, etc.
COPY . ./

# Fallback port when $PORT is unset (local `docker run`); Railway
# injects $PORT (commonly 8080) and the CMD honours it.
EXPOSE 8501

# web_app.py has no dedicated health route, but GET /api/config is a
# cheap endpoint that never requires auth and always returns 200 JSON
# — hitting it via curl lets the orchestrator (docker compose /
# Railway) detect a crashed-but-not-dead container.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT:-8501}/api/config" || exit 1

# JSON exec form via ``sh -c`` so $PORT expands AND signals propagate
# correctly to uvicorn (``exec`` replaces the shell with the uvicorn
# process so ``docker stop`` / Railway's SIGTERM reach it directly
# instead of being caught by an intermediate shell).
# --host 0.0.0.0 is required so the container is reachable from the
# host network.  No --workers: uvicorn's default single worker is
# mandatory here (see the header comment — in-process session + SSE
# bus).  No --reload: that is a local-dev-only convenience.
CMD ["sh", "-c", "exec uvicorn web_app:app --host 0.0.0.0 --port ${PORT:-8501}"]
