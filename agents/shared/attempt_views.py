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

Which views exist, their files and their order are declared by the tools
that produce them (``outputs.images`` in ``setups/<setup>/tools/<tool>/tool.yaml``);
each view's flag is that tool's ``view_<view>`` setting, changed in Workflow
Settings (MAS-blueprint P3c, ``engine/pack_tools.py``).

This module deliberately imports NOTHING heavy -- only the engine's manifest
reader, which imports no tool code.  ``r2_uploader`` and the retrieve tool
both import it, and neither may be made to drag in langchain or the geometry
backend.
"""
from __future__ import annotations

from engine import pack_tools as _pack_tools

# (view name, "<tool>.<setting>" flag, render filename), in the order the
# tools declare (isometric first: the single most informative view of the
# design).  Read once at import: the manifests do not change while the
# process runs; the flags are read fresh on every call below.
VIEWS: tuple[tuple[str, str, str], ...] = tuple(
    (r["view"], f"{r['tool']}.{r['setting']}", r["file"])
    for r in _pack_tools.image_outputs()
)

# The views produced by a generator's render step.  It writes them all in
# one call -- it is not per-view -- so ``attempt_renders`` generates the set
# whenever ANY of them is enabled and missing, and the per-view flag then
# governs upload and retrieval.
MESH_VIEWS: frozenset[str] = frozenset(
    r["view"] for r in _pack_tools.image_outputs()
    if r["tool"] in _pack_tools.generators()
)

VIEW_FILES: dict[str, str] = {v: f for v, _flag, f in VIEWS}


def is_enabled(view: str) -> bool:
    """True iff *view* is switched on.  Unknown views are False.

    Read FRESH on every call, like every other setting in this codebase:
    the Workflow Settings changes take effect on the next session.
    """
    return _pack_tools.view_enabled(view)


def enabled_views() -> list[str]:
    """Enabled view names, in registry order."""
    return [v for v, _flag, _f in VIEWS if _pack_tools.view_enabled(v)]


def enabled_view_files() -> list[str]:
    """Render filenames of the enabled views, in registry order."""
    return [VIEW_FILES[v] for v in enabled_views()]
