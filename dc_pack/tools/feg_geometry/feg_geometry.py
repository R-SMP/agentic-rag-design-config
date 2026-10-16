"""The FEG geometry tool: the propeller built by the browser 3D preview's own
code (``dc_pack/preview/feg/*``), run headless by Node through ``feg_export.mjs``.

Local, fast, no server; a visually faithful sub-mm approximation of the
Grasshopper geometry (``rhino_geometry``).  :func:`make_model` is memoised on
the parameters and the newest mtime of the exporter and ``preview/feg/*.js``, so
editing the geometry code evicts stale entries.  The engine calls it
(``engine/pack_tools.make_model``: the generator's geometry tool, the web
app's Download buttons) with parameters it has already checked.
"""

import functools
import json
import subprocess
from pathlib import Path

from engine.tooling import GeometryResult, ToolError

# Headless FEG exporter + its source tree (used for cache invalidation).
_FEG_EXPORTER = Path(__file__).resolve().parent / "feg_export.mjs"
_FEG_SOURCE_DIR = Path(__file__).resolve().parents[2] / "preview" / "feg"

# Repeated builds of the same parameters (a download after the run) are
# served from memory.
_CACHE_SIZE = 64


def _sources_mtime_ns() -> int:
    """Newest mtime across the FEG exporter + preview/feg/*.js — part of the FEG
    cache key so editing the geometry code evicts stale entries."""
    paths = [_FEG_EXPORTER, *_FEG_SOURCE_DIR.glob("*.js")]
    try:
        return max((p.stat().st_mtime_ns for p in paths), default=0)
    except OSError:
        return 0


@functools.lru_cache(maxsize=_CACHE_SIZE)
def _make_cached(
    params_tuple: tuple,
    feg_mtime_ns: int,
) -> tuple[str, int, None]:
    """Memoised implementation of :func:`make_model`: ``(obj_text,
    vertex_count, None)``.

    ``feg_mtime_ns`` is cache-key only (evicts on a preview/feg edit)."""
    del feg_mtime_ns
    params = dict(params_tuple)
    try:
        proc = subprocess.run(
            ["node", str(_FEG_EXPORTER), json.dumps(params)],
            capture_output=True, text=True, timeout=120,
        )
    except FileNotFoundError as exc:
        raise ToolError(
            f"FEG error: Node runtime not found ({exc})."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolError(
            f"FEG error: exporter timed out ({exc})."
        ) from exc
    except Exception as exc:  # noqa: BLE001 — surface any launch failure
        raise ToolError(f"FEG error: {exc}") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()[-500:]
        raise ToolError(
            f"FEG error: exporter exited {proc.returncode}: {detail}"
        )

    mesh_text = proc.stdout
    vertex_count = sum(
        1 for ln in mesh_text.splitlines() if ln.startswith("v ")
    )
    if vertex_count == 0:
        raise ToolError("FEG error: exporter produced no vertices.")
    # FEG bakes everything into a single mesh — no per-component sidecar.
    return mesh_text, vertex_count, None


def make_model(params: dict) -> GeometryResult:
    """The propeller's model from *params*, via the headless FEG exporter.
    Raises ToolError (``FEG error: …``)."""
    text, vertex_count, _ = _make_cached(tuple(sorted(params.items())), _sources_mtime_ns())
    return GeometryResult(model=text, vertex_count=vertex_count)
