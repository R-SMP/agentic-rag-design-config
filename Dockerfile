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
# CMD: streamlit listens on ${PORT} (Railway sets this) or 8501
# locally.  Headless mode + gatherUsageStats off keeps the
# container quiet and contained.
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
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglu1-mesa \
        libosmesa6 \
        libxext6 \
        libsm6 \
        libxrender1 \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dep layer first so source-only changes do not invalidate the
# (slow) pip install.
COPY requirements.txt ./
RUN pip install -r requirements.txt && \
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

# Application code.  .dockerignore filters out .venv, .git,
# logs/, attempts/, previous_sessions/, database/, inputs/, etc.
COPY . ./

# Default Streamlit port; Railway overrides via $PORT.
EXPOSE 8501

# Streamlit ships its own ``/_stcore/health`` endpoint.  The
# healthcheck hits it via curl so the orchestrator (docker compose
# / Railway) can detect a crashed-but-not-dead container.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT:-8501}/_stcore/health" || exit 1

# JSON exec form via ``sh -c`` so $PORT expands AND signals propagate
# correctly to streamlit (``exec`` replaces the shell with the
# streamlit process so ``docker stop`` / Railway's SIGTERM reach it
# directly instead of being caught by an intermediate shell).
# --server.address=0.0.0.0 is required so the container is reachable
# from the host network; --server.headless=true disables the
# "open in browser" prompt; --browser.gatherUsageStats=false keeps
# the container offline-friendly.
CMD ["sh", "-c", "exec streamlit run streamlit_app.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]
