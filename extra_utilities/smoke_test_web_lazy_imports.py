"""Offline guard: every lazily-imported module used in ``web_app.py`` must
actually be imported in a scope that reaches the use.

``web_app.py`` deliberately has NO module-level ``postgres_pool`` import --
see the note above the reset endpoint: "only loaded when the destructive
endpoint actually fires, so a Railway deploy without DATABASE_URL set never
tries to open the pool just to serve other views."  Each handler that needs
it does ``from agents.shared import postgres_pool`` itself.

Forget that line and nothing complains at import time, at startup, or in any
test that does not call the route.  The handler raises ``NameError`` on its
first request, FastAPI turns that into a bare ``Internal Server Error``, and
the browser reports it as ``Unexpected token 'I', "Internal S"... is not
valid JSON`` -- a message that points at the frontend, not at the missing
import.  That shipped for `/api/manual_entries` and `/api/manual_entry/delete`
and was only noticed once someone tried to view the manual entries.

Most routes here touch no database, so ordinary use exercises none of this.
A static check is the cheap way to cover all of them at once.

Pure ``ast`` analysis: nothing is imported, no app is started, no network and
no database.  Run from the repo root::

    python extra_utilities/smoke_test_web_lazy_imports.py
"""

from __future__ import annotations

import ast
import io
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = _REPO_ROOT / "web_app.py"

# Modules web_app.py is expected to import lazily, inside the functions that
# use them.  Add to this only when a new one is introduced on purpose.
LAZY_MODULES = frozenset({"postgres_pool"})

_failures: list[str] = []


_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _bound_here(node: ast.AST) -> set[str]:
    """Names bound by imports in *node*'s OWN scope.

    Descends through control flow (``if`` / ``try`` / ``with`` / loops), where
    an import still binds in this scope, but stops at a nested function or
    class: an import inside one of those is not visible to its parent.

    ``ast.walk`` cannot express that -- it is a flat traversal, so skipping a
    nested ``FunctionDef`` node still yields the imports inside it.  Using it
    here made this guard report `postgres_pool` as module-level when it was
    only ever imported inside handlers.
    """
    out: set[str] = set()

    def descend(n: ast.AST) -> None:
        for child in ast.iter_child_nodes(n):
            if isinstance(child, _SCOPES):
                continue
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                for alias in child.names:
                    out.add(alias.asname or alias.name.split(".")[0])
            descend(child)

    descend(node)
    return out


def _uses(node: ast.AST, name: str) -> list[int]:
    """Line numbers where *name* is READ inside *node*, nested scopes and all."""
    return sorted({
        n.lineno for n in ast.walk(node)
        if isinstance(n, ast.Name) and n.id == name
        and isinstance(n.ctx, ast.Load)
    })


def _walk(node: ast.AST, visible: set[str], where: str) -> None:
    """Check every function in *node*, carrying down the visible bindings."""
    for child in getattr(node, "body", []):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            inner = visible | _bound_here(child)
            label = f"{where}.{child.name}" if where else child.name
            for mod in LAZY_MODULES:
                if mod in inner:
                    continue
                lines = _uses(child, mod)
                # Only report the OUTERMOST function that is missing it --
                # a nested use is the same defect, reported once.
                if lines:
                    _failures.append(
                        f"{label} (line {child.lineno}) uses `{mod}` at "
                        f"line(s) {', '.join(map(str, lines))} but never "
                        f"imports it, and web_app.py has no module-level "
                        f"import of it either -> NameError -> HTTP 500")
                    break
            else:
                _walk(child, inner, label)
        elif isinstance(child, ast.ClassDef):
            _walk(child, visible | _bound_here(child), child.name)


def main() -> int:
    print("[smoke-web-lazy-imports]  checking web_app.py ...")
    if not TARGET.is_file():
        print(f"FAIL - {TARGET} not found")
        return 1

    tree = ast.parse(io.open(TARGET, encoding="utf-8").read(),
                     filename=str(TARGET))

    module_level = _bound_here(tree)
    for mod in sorted(LAZY_MODULES):
        if mod in module_level:
            _failures.append(
                f"`{mod}` is imported at MODULE level in web_app.py.  It is "
                f"meant to be lazy so a deploy without DATABASE_URL does not "
                f"open the pool to serve unrelated views -- either restore "
                f"the local imports or drop it from LAZY_MODULES here.")

    _walk(tree, module_level, "")

    print()
    if _failures:
        print(f"FAIL - {len(_failures)} problem(s):")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print(f"PASS - every use of {', '.join(sorted(LAZY_MODULES))} in "
          f"web_app.py has an import in scope")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
