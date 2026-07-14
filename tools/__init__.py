"""Tools available to agents.

The Tool Caller is given the merged geometry+renders tool
(``generate_and_render_propeller``) and the calculator.  The merged tool
builds the mesh and then renders + checks it in one call; the render step
uses ONE of two render-and-check cores (trimesh or pyvista), picked at
session start by ``loader.py`` calling :func:`set_render_library` BEFORE the
Tool Caller is built and injected into the merged tool via
:func:`set_render_and_check_fn`.
"""

from tools.calculate.calculate import calculate
from tools.render_mesh.render_mesh import (
    render_and_check as _render_core_trimesh,
    set_mesh_checks as _set_mesh_checks_trimesh,
)
from tools.render_mesh.render_mesh_pyvista import (
    render_and_check_pv as _render_core_pyvista,
    set_mesh_checks as _set_mesh_checks_pyvista,
)
from tools.generate_mesh.generate_mesh import (
    generate_and_render_propeller,
    set_render_and_check_fn,
    set_geometry_backend,
    get_geometry_backend,
)

# Valid choices.
RENDER_LIBRARIES: tuple[str, ...] = ("trimesh", "pyvista")

# Active selection — mutated by ``set_render_library`` before
# ``ToolCaller`` is constructed.  Default keeps prior behaviour
# (trimesh) for any caller that forgets to pick.
_active_render_library: str = "trimesh"


def set_render_library(library: str) -> None:
    """Pick which mesh-check / render core the merged tool will use.

    Must be called before constructing the Tool Caller.  Raises on
    unknown choices so a typo at startup fails loudly instead of
    silently keeping the default.  Also re-wires the merged
    ``generate_and_render_propeller`` tool's render step to the newly
    selected backend.
    """
    global _active_render_library
    if library not in RENDER_LIBRARIES:
        raise ValueError(
            f"Unknown render library {library!r}; expected one of "
            f"{RENDER_LIBRARIES}."
        )
    _active_render_library = library
    # Keep the merged tool's built-in render step pointed at the active core.
    set_render_and_check_fn(get_render_core())


def get_render_library() -> str:
    """Return the currently selected render library name."""
    return _active_render_library


def set_mesh_checks(enabled: bool) -> None:
    """Toggle deterministic mesh quality checks on BOTH backends.

    The merged tool only ever runs one of the two render cores at
    runtime, but both module-level flags are kept in sync so a future
    re-binding (e.g. for testing) inherits the same setting.
    """
    _set_mesh_checks_trimesh(enabled)
    _set_mesh_checks_pyvista(enabled)


def get_render_core():
    """Return the render+check core function for the active render library.

    Called (via :func:`set_render_and_check_fn`) so the merged
    ``generate_and_render_propeller`` tool runs its render step with the
    selected backend."""
    if _active_render_library == "pyvista":
        return _render_core_pyvista
    return _render_core_trimesh


def get_tools() -> list:
    """Return the design tools the Tool Caller binds for this session.

    Geometry + renders are a SINGLE merged tool
    (``generate_and_render_propeller``): it builds the mesh and then, as its
    built-in final step, renders + checks it using the render core picked by
    :func:`set_render_library`.
    """
    return [generate_and_render_propeller, calculate]


# Wire the merged tool's render step to the default backend at import time so
# it works even when nobody calls set_render_library (e.g. standalone smoke
# tests).  set_render_library re-wires it whenever the selection changes.
set_render_and_check_fn(get_render_core())


# Backwards-compatible alias for callers that just want "the design tools".
# Resolved lazily so it always reflects the current selection.
def __getattr__(name: str):
    if name == "TOOLS":
        return get_tools()
    raise AttributeError(name)
