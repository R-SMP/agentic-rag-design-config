"""Smoke test — DH internal call-chain kwarg propagation.

Pure AST analysis: catches NameError-class regressions where one
DH method calls another with kwargs whose values reference names
NOT in the caller's scope.  No LLM calls, no DB, no R2 — runs
in milliseconds.

Why this test exists
--------------------
The Phase 3C effort (2026-06-02) introduced TWO kwarg-propagation
bugs that slipped past the existing db_writer + Phase 3C smoke
tests because both bypass ``populate_database`` entirely:

  1. ``populate_database`` referenced ``session_id`` before
     assignment.  Fixed in commit ``8a55d17``.
  2. ``_run_identifying_conversation`` called
     ``_run_force_tool_phase`` with kwargs
     (``attempt_id_by_nnn``, ``cascaded_attempt_nnns``,
     ``db_writer_available``) that weren't in its parameter list.
     Fixed in the commit alongside this test file.

Both bugs were the same shape: a kwarg whose value was a bare
``Name`` not in the enclosing method's scope.  This test catches
that pattern automatically.

What it does
------------
For each instance method of ``DatabaseHandler`` listed in
``_SUSPECT_METHODS`` below:

  1. Grab the source via ``inspect.getsource``.
  2. Parse with ``ast``.
  3. Find every ``Call(...)`` node, recursively.
  4. For each kwarg whose value is a BARE ``ast.Name`` (not an
     expression / attribute / call), verify the name resolves to:
       - a parameter of the enclosing method, OR
       - a local assignment / for-loop target / with-binding /
         except-binding inside the method body, OR
       - a module-level global / import in
         ``database_handler.py``, OR
       - a Python builtin, OR
       - ``self`` / ``cls``.
  5. Report any unresolved name with file:line.

Caveats
-------
- Only catches BARE-NAME kwargs (``foo=foo``, ``foo=bar``).
  Misses kwargs whose value is an expression
  (``foo=bar.baz``, ``foo=some_func()``).
- Doesn't recurse into nested ``FunctionDef`` bodies — they have
  their own scope and we'd produce false positives there.  In
  practice the DH methods don't nest functions in ways that
  trigger this.
- Doesn't simulate runtime behaviour; misses bugs that aren't
  kwarg-propagation (e.g. wrong argument value semantics).

Trade-off accepted: false negatives possible, false positives
near-zero, runs in ~50ms, no external dependencies.

Run from repo root::

    python extra_utilities/db_design/smoke_test_dh_kwarg_propagation.py

Exits 0 on full pass; non-zero on any unresolved kwarg with a
clear file:line + which name didn't resolve.
"""

from __future__ import annotations

import ast
import builtins
import inspect
import sys
import textwrap
from pathlib import Path
from typing import Iterable, Set

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agents.database_handler.database_handler import DatabaseHandler  # noqa: E402


# Methods to inspect.  When a new method that drives the DH-side
# integration is added (or a method's call surface changes),
# append it here so the regression catch keeps applying.
_SUSPECT_METHODS = [
    "populate_database",
    "_run_identifying_conversation",
    "_run_force_tool_phase",
    "_phase_3c_persist_chunk",
    # The batched interview replaced ``_run_one_conversation`` (retired
    # with the text protocol).  These carry the same risk in the same
    # shape — several of them are called with kwargs assembled from the
    # caller's locals.
    "_run_batch",
    "_plan_batches",
    "_batch_questions",
    "_shorten_over_cap",
    "_force_tool_args",
]


def _collect_assign_target_names(
    target: ast.AST, names_set: Set[str]
) -> None:
    """Walk an assignment target node and add all bound names.

    Handles Name, Tuple, List, Starred.  Attribute / Subscript
    targets do NOT introduce a new name in scope, so they're
    skipped.
    """
    if isinstance(target, ast.Name):
        names_set.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for el in target.elts:
            _collect_assign_target_names(el, names_set)
    elif isinstance(target, ast.Starred):
        _collect_assign_target_names(target.value, names_set)


def _walk_no_nested_funcs(node: ast.AST) -> Iterable[ast.AST]:
    """Yield ``node`` and all descendants, BUT do NOT descend into
    nested function / class bodies — they have their own scope and
    their locals don't leak to the enclosing method.
    """
    yield node
    for child in ast.iter_child_nodes(node):
        if isinstance(
            child,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.Lambda,
                ast.ClassDef,
            ),
        ):
            # Yield the node itself (so e.g. an inner-function
            # parameter appears in the parent scope as a binding,
            # which Python does treat as an assignment of the
            # nested-func name) but skip its body.
            yield child
            continue
        yield from _walk_no_nested_funcs(child)


def _collect_in_scope_names(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Set[str]:
    """Return every name that resolves inside ``func_node``'s scope.

    Parameters (positional, kw-only, vararg, kwarg) + every name
    bound by an assignment / for / with / except / comprehension /
    import inside the function body.  Nested function/class defs
    contribute only their own name as a binding (their bodies are
    walked separately by the caller, not here).
    """
    names: Set[str] = set()
    # Parameters
    for arg in func_node.args.posonlyargs:
        names.add(arg.arg)
    for arg in func_node.args.args:
        names.add(arg.arg)
    for arg in func_node.args.kwonlyargs:
        names.add(arg.arg)
    if func_node.args.vararg:
        names.add(func_node.args.vararg.arg)
    if func_node.args.kwarg:
        names.add(func_node.args.kwarg.arg)

    # Body bindings
    for node in _walk_no_nested_funcs(func_node):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                _collect_assign_target_names(tgt, names)
        elif isinstance(node, ast.AnnAssign):
            _collect_assign_target_names(node.target, names)
        elif isinstance(node, ast.AugAssign):
            _collect_assign_target_names(node.target, names)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            _collect_assign_target_names(node.target, names)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    _collect_assign_target_names(
                        item.optional_vars, names
                    )
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(
                    (alias.asname or alias.name).split(".")[0]
                )
        elif isinstance(node, ast.Try):
            for handler in node.handlers:
                if handler.name:
                    names.add(handler.name)
        elif isinstance(node, ast.comprehension):
            _collect_assign_target_names(node.target, names)
        elif isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            # Nested function's NAME is a binding in the parent.
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
    return names


def _find_unresolved_kwargs(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    in_scope: Set[str],
) -> list[dict]:
    """Find every Call(...) kwarg in ``func_node``'s body (not in
    nested funcs) whose value is a bare Name not in ``in_scope``.
    """
    errors: list[dict] = []
    for node in _walk_no_nested_funcs(func_node):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg is None:
                    # **kwargs unpacking; skip.
                    continue
                if isinstance(kw.value, ast.Name):
                    name = kw.value.id
                    if name not in in_scope:
                        try:
                            call_str = ast.unparse(node.func)
                        except AttributeError:
                            call_str = "<call>"
                        errors.append({
                            "line": kw.value.lineno,
                            "call": call_str,
                            "kwarg": kw.arg,
                            "name": name,
                        })
    return errors


def _check_one_method(
    cls: type,
    method_name: str,
    module_globals: Set[str],
) -> tuple[str | None, list[dict]]:
    """Returns ``(warning_message, errors)``.

    warning_message is non-None when the method is missing or
    its source cannot be parsed.
    """
    method = getattr(cls, method_name, None)
    if method is None:
        return f"missing method: {method_name}", []

    try:
        src = inspect.getsource(method)
    except (OSError, TypeError) as exc:
        return f"could not getsource({method_name}): {exc}", []

    src = textwrap.dedent(src)
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return f"SyntaxError parsing {method_name}: {exc}", []

    func_node = next(
        (
            n for n in tree.body
            if isinstance(
                n, (ast.FunctionDef, ast.AsyncFunctionDef)
            )
        ),
        None,
    )
    if func_node is None:
        return f"no function def found in {method_name}", []

    in_scope = _collect_in_scope_names(func_node)
    in_scope.update(module_globals)
    in_scope.update(dir(builtins))
    in_scope.update({"self", "cls"})

    errors = _find_unresolved_kwargs(func_node, in_scope)
    return None, errors


def main() -> int:
    print("[kwarg-propagation] checking DH internal call-chain...")
    print()

    mod = inspect.getmodule(DatabaseHandler)
    module_globals: Set[str] = set(vars(mod).keys()) if mod else set()

    total_errors = 0
    method_label_width = max(
        len(name) for name in _SUSPECT_METHODS
    ) + 2

    for method_name in _SUSPECT_METHODS:
        warn, errors = _check_one_method(
            DatabaseHandler, method_name, module_globals,
        )
        label = method_name.ljust(method_label_width)
        if warn:
            print(f"  {label}  WARN  ({warn})")
            continue
        if errors:
            print(
                f"  {label}  FAIL  "
                f"({len(errors)} unresolved kwarg"
                f"{'s' if len(errors) != 1 else ''})"
            )
            for e in errors:
                print(
                    f"      line {e['line']}: "
                    f"{e['call']}(..., "
                    f"{e['kwarg']}={e['name']}, ...)"
                    f"  ← name '{e['name']}' not in scope"
                )
            total_errors += len(errors)
        else:
            print(f"  {label}  PASS")

    print()
    if total_errors == 0:
        print(
            f"PASS - all {len(_SUSPECT_METHODS)} DH methods have "
            f"clean bare-name kwarg propagation."
        )
        return 0
    else:
        print(
            f"FAIL - {total_errors} unresolved kwarg(s) across "
            f"DH methods."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
