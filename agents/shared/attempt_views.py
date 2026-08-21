"""Which render views an attempt carries — one registry, three consumers.

A "view" is one rendered PNG of an attempt.  ONE flag per view governs all
three things that can happen to it:

* **generate** — created at save time if missing (``attempt_renders``)
* **save**     — uploaded to R2 (``r2_uploader``)
* **retrieve** — fetched when an agent retrieves the attempt
  (``tools/retrieve_attempt``)

Those three modules used to disagree: ``render_blade_sections.png`` was
written into attempt folders by its tool but was in NEITHER the upload
whitelist NOR the retrieval map, so no archived attempt anywhere had one;
meanwhile ``render_side.png`` was uploaded but never fetched.  A single
registry is what stops that drifting apart again.

SAVING IS IRREVERSIBLE, RETRIEVAL IS NOT
----------------------------------------
Turning a view OFF is a decision about the PERMANENT RECORD: every attempt
archived while it was off has no such render, and turning the flag back on
cannot reach back.  Turning one ON only affects attempts saved afterwards.
That asymmetry is why one flag governs all three rather than saving
generously and fetching selectively.

This module deliberately imports NOTHING heavy — only the settings module.
``r2_uploader`` and the retrieve tool both import it, and neither may be
made to drag in langchain or the geometry backend.
"""

from __future__ import annotations

from workflow_settings import settings as _settings

# (view name, settings flag, render filename).  Order is the order views
# appear in a response; isometric first because it is the single most
# informative view of propeller geometry.
VIEWS: tuple[tuple[str, str, str], ...] = (
    ("isometric",      "ATTEMPT_VIEW_ISOMETRIC",      "render_isometric.png"),
    ("top",            "ATTEMPT_VIEW_TOP",            "render_top.png"),
    ("blade_sections", "ATTEMPT_VIEW_BLADE_SECTIONS",
     "render_blade_sections.png"),
    ("side",           "ATTEMPT_VIEW_SIDE",           "render_side.png"),
)

# The views produced by the 3D render core.  It writes ALL THREE in one
# call (``render_mesh._RENDER_NAMES``) — it is not per-view — so
# ``attempt_renders`` generates the set whenever ANY of them is enabled and
# missing, and the per-view flag then governs upload and retrieval.  The
# marginal cost of an unwanted third camera angle on an already-loaded mesh
# is not worth forking the render core over.
MESH_VIEWS: frozenset[str] = frozenset({"isometric", "top", "side"})

# Rendered from ``parameters.json`` alone — no mesh required, which is why
# ``attempt_renders`` does this one FIRST.
PARAMS_ONLY_VIEWS: frozenset[str] = frozenset({"blade_sections"})

VIEW_FILES: dict[str, str] = {v: f for v, _flag, f in VIEWS}


def is_enabled(view: str) -> bool:
    """True iff *view* is switched on.  Unknown views are False.

    Read FRESH from the settings module on every call, like every other
    setting in this codebase: ``web_app._build_session`` reloads settings in
    place and the Sessions Queue switches them between runs in one process.
    """
    for name, flag, _f in VIEWS:
        if name == view:
            return bool(getattr(_settings, flag, False))
    return False


def enabled_views() -> list[str]:
    """Enabled view names, in registry order."""
    return [v for v, flag, _f in VIEWS
            if bool(getattr(_settings, flag, False))]


def enabled_view_files() -> list[str]:
    """Render filenames of the enabled views, in registry order."""
    return [VIEW_FILES[v] for v in enabled_views()]


def view_file(view: str) -> str | None:
    """Render filename for *view*, or None when the view is unknown."""
    return VIEW_FILES.get(view)
