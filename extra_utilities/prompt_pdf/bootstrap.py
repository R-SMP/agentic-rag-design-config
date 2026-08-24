"""Import the repo's prompt + tool layer without the heavy runtime deps.

Everything that only needs to EXIST for an import to succeed is stubbed;
everything that shapes a prompt or a tool description is the real module.
"""
import sys, types, importlib.abc, importlib.machinery
from pathlib import Path
from unittest.mock import MagicMock

REPO = Path(__file__).resolve().parents[2]   # <repo>/extra_utilities/prompt_pdf/x.py

# Third-party packages that are pure runtime plumbing (network, DB, 3D, LLM
# clients).  None of them contributes text to a prompt or a tool schema.
STUB_ROOTS = {
    "psycopg", "tiktoken", "trimesh", "pyrender", "pyvista", "rhino3dm",
    "compute_rhino3d", "boto3", "botocore", "voyageai",
    "openai", "anthropic", "google", "matplotlib", "scipy", "shapely",
    "cv2", "vtk", "OpenGL", "pyglet", "manifold3d", "mapbox_earcut",
    "langchain_openai", "langchain_anthropic", "langchain_google_genai",
    "langchain", "pgvector", "psycopg_pool", "psutil", "sse_starlette", "fastapi", "uvicorn",
    "starlette", "networkx", "collada", "lxml", "DracoPy", "embreex",
    "fast_simplification", "xatlas", "meshio", "pycollada", "svg",
}


class _StubLoader(importlib.abc.Loader):
    def create_module(self, spec):
        m = MagicMock(name=spec.name)
        m.__name__ = spec.name
        m.__path__ = []
        m.__spec__ = spec
        m.__all__ = []
        return m

    def exec_module(self, module):
        return None


class _StubFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root in STUB_ROOTS:
            return importlib.machinery.ModuleSpec(
                fullname, _StubLoader(), is_package=True
            )
        return None


def install():
    sys.path.insert(0, str(REPO))
    sys.meta_path.insert(0, _StubFinder())
    # numpy / PIL / dotenv are cheap and real if present; stub only if absent.
    for name in ("numpy", "PIL", "dotenv"):
        try:
            __import__(name)
        except ImportError:
            STUB_ROOTS.add(name)
    # `agents/__init__.py` imports the Orchestrator, which drags in the whole
    # LLM stack at import time.  Replace it with a bare namespace package so
    # submodules import individually.
    pkg = types.ModuleType("agents")
    pkg.__path__ = [str(REPO / "agents")]
    sys.modules["agents"] = pkg
    return REPO


# --------------------------------------------------------------------------
# Fallback: stub anything genuinely absent from this environment (optional
# native deps of the 3D stack, etc).  Sits at the END of sys.meta_path so a
# real installed module always wins.  Every name it catches is recorded, so
# the caller can assert no REPO module was silently stubbed.
# --------------------------------------------------------------------------
FALLBACK_STUBBED: set = set()


class _FallbackFinder(_StubFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(("agents", "tools", "workflow_settings",
                                "reduced7", "config")):
            return None
        FALLBACK_STUBBED.add(fullname)
        return importlib.machinery.ModuleSpec(
            fullname, _StubLoader(), is_package=True
        )


def install_fallback():
    sys.meta_path.append(_FallbackFinder())
