"""``visualize_3d_model`` — a Receptionist tool that pushes a mesh to
the web viewer.

Takes the path to an ``.obj`` file, asks the web interface (via the
decoupled visualization bus) to display it interactively, and returns
a short success/failure string back to the calling agent.

No web imports here — the tool only touches ``agents.shared.viz_bus``,
which the web layer subscribes to.  In the REPL / Streamlit (no web
viewer) the publish simply reaches zero subscribers and the tool says
so honestly.
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from agents.shared.viz_bus import publish
from config import ATTEMPTS_DIR


@tool
def visualize_3d_model(obj_path: str) -> str:
    """Display a generated 3D model (.obj) in the web interface's
    interactive viewer.

    Use this when a design attempt has produced a propeller mesh and
    the user should see it: pass the absolute path to that attempt's
    ``propeller_mesh.obj``.  The model loads live in the web UI's 3D
    panel where the user can rotate and zoom it.  This tool does NOT
    let you observe the mesh — you still never describe its
    appearance.

    Args:
        obj_path: Absolute path to the ``.obj`` mesh file.  Must be
            an existing ``.obj`` inside the attempts directory.

    Returns:
        A short message stating whether the model was sent to the
        web viewer, or precisely why it could not be.
    """
    raw = (obj_path or "").strip()
    if not raw:
        return ("visualize_3d_model: FAILED — no obj_path given. Pass "
                "the absolute path to the attempt's propeller_mesh.obj.")
    try:
        target = Path(raw).resolve()
    except Exception as exc:
        return f"visualize_3d_model: FAILED — invalid path {raw!r}: {exc}"

    if target.suffix.lower() != ".obj":
        return (f"visualize_3d_model: FAILED — {target} is not an .obj "
                f"file. Only mesh .obj files can be visualised.")
    if not target.is_file():
        return (f"visualize_3d_model: FAILED — no file at {target}. "
                f"Check the attempt folder path.")

    try:
        root = ATTEMPTS_DIR.resolve()
    except OSError:
        root = ATTEMPTS_DIR
    if root != target and root not in target.parents:
        return (f"visualize_3d_model: FAILED — {target} is outside the "
                f"attempts directory ({root}); only generated meshes "
                f"under attempts/ can be shown.")

    reached = publish({
        "type": "visualize",
        "path": str(target),
        "name": target.name,
    })
    if reached:
        return (f"visualize_3d_model: OK — sent {target.name} to the "
                f"web interface's 3D viewer.")
    return (f"visualize_3d_model: OK — {target.name} is valid and was "
            f"queued, but no web interface is currently connected to "
            f"display it (e.g. running headless / REPL).")
