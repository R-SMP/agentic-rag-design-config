"""Tools available to agents.

The Tool Caller is given the mesh-generation tool, the calculator,
and ONE of two render-and-check tools — never both.  Which render-
and-check tool is bound is decided at session start by ``loader.py``
calling :func:`set_render_library` BEFORE the Tool Caller is built.
Both render tools register the same LangChain tool name
(``render_and_check_mesh``) so prompt fragments and routing wiring
stay backend-agnostic.
"""

from tools.calculate.calculate import calculate
from tools.render_mesh.render_mesh import (
    render_and_check_mesh as _render_trimesh,
    set_mesh_checks as _set_mesh_checks_trimesh,
)
from tools.render_mesh.render_mesh_pyvista import (
    render_and_check_mesh_pv as _render_pyvista,
    set_mesh_checks as _set_mesh_checks_pyvista,
)
from tools.generate_mesh.generate_mesh import generate_propeller_mesh

# Valid choices.
RENDER_LIBRARIES: tuple[str, ...] = ("trimesh", "pyvista")

# Active selection — mutated by ``set_render_library`` before
# ``ToolCaller`` is constructed.  Default keeps prior behaviour
# (trimesh) for any caller that forgets to pick.
_active_render_library: str = "trimesh"


def set_render_library(library: str) -> None:
    """Pick which mesh-check / render tool the Tool Caller will receive.

    Must be called before constructing the Tool Caller.  Raises on
    unknown choices so a typo at startup fails loudly instead of
    silently keeping the default.
    """
    global _active_render_library
    if library not in RENDER_LIBRARIES:
        raise ValueError(
            f"Unknown render library {library!r}; expected one of "
            f"{RENDER_LIBRARIES}."
        )
    _active_render_library = library


def get_render_library() -> str:
    """Return the currently selected render library name."""
    return _active_render_library


def set_mesh_checks(enabled: bool) -> None:
    """Toggle deterministic mesh quality checks on BOTH backends.

    The Tool Caller only ever sees one of the two tools at runtime,
    but both module-level flags are kept in sync so a future
    re-binding (e.g. for testing) inherits the same setting.
    """
    _set_mesh_checks_trimesh(enabled)
    _set_mesh_checks_pyvista(enabled)


def get_render_tool():
    """Return the LangChain tool object for the active render library."""
    if _active_render_library == "pyvista":
        return _render_pyvista
    return _render_trimesh


def get_tools() -> list:
    """Return the design tools the Tool Caller binds for this session.

    Exactly one render-and-check tool is included, picked by
    :func:`get_render_library`.
    """
    return [generate_propeller_mesh, calculate, get_render_tool()]


# Backwards-compatible alias for callers that just want "the design tools".
# Resolved lazily so it always reflects the current selection.
def __getattr__(name: str):
    if name == "TOOLS":
        return get_tools()
    raise AttributeError(name)
