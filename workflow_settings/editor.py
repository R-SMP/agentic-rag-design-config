"""Read and safely rewrite ``workflow_settings/settings.py`` for the
web Workflow Settings editor.

Only the right-hand side of each top-level ``NAME: type = value``
assignment is rewritten; the module docstring, every comment, blank
lines and ordering are preserved verbatim.  ``settings.py`` stays the
single source of truth (``agents/loader.py`` and the Streamlit / CLI
front-ends all keep reading the same file).

``EMBEDDING_API_KEY`` is derived from the environment
(``os.getenv(...)``) — it is exposed read-only, its value is masked,
and it is never written back.

Settings are read fresh at each session build, so an edit made here
takes effect for the *next* session (after End Session / a new
session), not mid-conversation.  The rate-limiter constants are read
at import time in ``agents/shared/llm_provider.py`` and need a server
restart to take effect.
"""

from __future__ import annotations

import ast
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

SETTINGS_PATH = Path(__file__).parent / "settings.py"

# Fields whose value is constrained to a fixed set — rendered as
# dropdowns in the UI and validated on save.  Mirrors the contract
# enforced up-front in agents/loader.py.
ENUM_OPTIONS: dict[str, list[Any]] = {
    "RENDER_LIBRARY": ["trimesh", "pyvista"],
    "DCOI_COMPARISON_MODE": [1, 2, 3],
    "EMBEDDING_PROVIDER": ["OpenAI"],
}

# Derived from the environment via os.getenv — show read-only, mask
# the value, never rewrite.
DERIVED_READONLY = {"EMBEDDING_API_KEY"}

_FENCE_RE = re.compile(r"^#+\s*=+\s*$")


class SettingsError(ValueError):
    """Raised on an invalid edit; surfaced to the UI as a 400."""


def _strip_comment(line: str) -> str:
    """Drop the leading ``#`` (and at most one following space)."""
    s = line.lstrip()
    if not s.startswith("#"):
        return ""
    s = s[1:]
    if s.startswith(" "):
        s = s[1:]
    return s.rstrip()


def _comment_block(lines: list[str], start: int, end: int) -> tuple[str, str]:
    """Extract (group_title, help_text) from source ``lines`` in the
    1-based inclusive range ``[start, end]`` (the region between the
    previous statement and this assignment).

    ``group_title`` is the text fenced between two ``# ====`` rules
    (empty when there is no fenced header — the field inherits the
    caller's running group).  ``help_text`` is every other comment
    line, de-commented, with blank ``#`` lines kept as paragraph
    breaks.
    """
    if start > end:
        return "", ""
    region = lines[start - 1:end]
    fence_idx = [i for i, ln in enumerate(region) if _FENCE_RE.match(ln.strip())]

    title = ""
    help_lines: list[str]
    if len(fence_idx) >= 2:
        a, b = fence_idx[0], fence_idx[1]
        title = " ".join(
            _strip_comment(region[i]) for i in range(a + 1, b)
        ).strip()
        help_lines = region[b + 1:]
    else:
        help_lines = region

    out: list[str] = []
    for ln in help_lines:
        s = ln.strip()
        if not s:
            continue
        if not s.startswith("#"):
            continue
        out.append(_strip_comment(ln))
    # Trim leading / trailing blank lines.
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return title, "\n".join(out)


def _annotation_type(node: ast.AnnAssign) -> str | None:
    ann = node.annotation
    if isinstance(ann, ast.Name):
        return ann.id
    return None


def _literal(node: ast.AST) -> tuple[bool, Any]:
    """Return (is_literal, value) for an assignment RHS."""
    if isinstance(node, ast.Constant):
        return True, node.value
    return False, None


def _parse_nodes() -> tuple[list[str], list[ast.AnnAssign]]:
    src = SETTINGS_PATH.read_text(encoding="utf-8")
    lines = src.split("\n")
    tree = ast.parse(src)
    nodes: list[ast.AnnAssign] = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            nodes.append(node)
    return lines, nodes


def read_schema() -> list[dict[str, Any]]:
    """Ordered list of settings with metadata for the editor UI."""
    lines, nodes = _parse_nodes()
    # Module body in source order, to find each setting's preceding
    # statement (so the comment region is bounded correctly).
    tree = ast.parse("\n".join(lines))
    body = list(tree.body)

    # live values — used only to report whether the env-derived API
    # key is currently populated (its literal is never shown).
    try:
        from workflow_settings import settings as _live  # noqa: WPS433
    except Exception:  # pragma: no cover - settings import is required elsewhere
        _live = None

    schema: list[dict[str, Any]] = []
    current_group = ""
    for idx, node in enumerate(body):
        if not (isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)):
            continue
        name = node.target.id
        type_str = _annotation_type(node) or "str"
        prev_end = body[idx - 1].end_lineno if idx > 0 else 0
        group, help_text = _comment_block(
            lines, prev_end + 1, node.lineno - 1
        )
        if group:
            current_group = group

        readonly = name in DERIVED_READONLY
        is_lit, value = _literal(node.value)

        if readonly:
            control = "text"
            present = bool(getattr(_live, name, "")) if _live else False
            item: dict[str, Any] = {
                "name": name,
                "type": type_str,
                "control": control,
                "value": None,
                "readonly": True,
                "derived_note": "Set from the OPENAI_API_KEY environment "
                                "variable — edit it in your shell / .env, "
                                "not here.",
                "present": present,
            }
        else:
            if type_str == "bool":
                control = "toggle"
            elif name in ENUM_OPTIONS:
                control = "dropdown"
            else:
                control = "text"
            item = {
                "name": name,
                "type": type_str,
                "control": control,
                "value": value if is_lit else None,
                "readonly": False,
            }
            if name in ENUM_OPTIONS:
                item["options"] = ENUM_OPTIONS[name]

        item["group"] = current_group
        item["help"] = help_text
        schema.append(item)
    return schema


def _coerce(name: str, type_str: str, raw: Any) -> Any:
    """Coerce an incoming JSON value to the field's Python type."""
    try:
        if type_str == "bool":
            if isinstance(raw, bool):
                return raw
            return str(raw).strip().lower() in {"true", "1", "yes", "v", "on"}
        if type_str == "int":
            try:
                return int(raw)
            except (TypeError, ValueError):
                return int(float(raw))
        if type_str == "float":
            return float(raw)
        return str(raw)
    except (TypeError, ValueError) as exc:
        raise SettingsError(
            f"{name}: {raw!r} is not a valid {type_str}."
        ) from exc


def _to_literal(type_str: str, value: Any) -> str:
    if type_str == "bool":
        return "True" if value else "False"
    if type_str == "int":
        return str(int(value))
    if type_str == "float":
        return repr(float(value))
    return json.dumps(str(value))  # double-quoted, escaped


def _validate(merged: dict[str, Any]) -> None:
    """Enforce the same contract agents/loader.py checks up-front."""
    for name, opts in ENUM_OPTIONS.items():
        if name in merged and merged[name] not in opts:
            raise SettingsError(
                f"{name} must be one of {opts}, got {merged[name]!r}."
            )
    rps = merged.get("RATE_LIMIT_REQUESTS_PER_SECOND")
    enabled = merged.get("RATE_LIMIT_ENABLED")
    if enabled and rps is not None and rps <= 0:
        raise SettingsError(
            "RATE_LIMIT_REQUESTS_PER_SECOND must be > 0 when "
            "RATE_LIMIT_ENABLED is True."
        )
    for pos in ("EMBEDDING_VECTOR_DIMS", "EMBEDDING_MAX_RESPONSE_TOKENS"):
        if pos in merged and merged[pos] is not None and merged[pos] <= 0:
            raise SettingsError(f"{pos} must be a positive integer.")


def write_updates(updates: dict[str, Any]) -> None:
    """Validate ``updates`` and rewrite only the touched assignment
    lines in ``settings.py``, preserving everything else.

    Raises :class:`SettingsError` (a ``ValueError``) on any invalid or
    disallowed edit; the file is left untouched in that case.
    """
    if not isinstance(updates, dict):
        raise SettingsError("Expected an object of {name: value} edits.")

    lines, nodes = _parse_nodes()
    by_name = {n.target.id: n for n in nodes}

    # Build the post-edit value map (current literals overlaid with the
    # coerced edits) for cross-field validation.
    merged: dict[str, Any] = {}
    for n in nodes:
        is_lit, val = _literal(n.value)
        if is_lit:
            merged[n.target.id] = val

    coerced: dict[str, Any] = {}
    for name, raw in updates.items():
        if name not in by_name:
            raise SettingsError(f"Unknown setting {name!r}.")
        if name in DERIVED_READONLY:
            raise SettingsError(
                f"{name} is derived from the environment and is read-only."
            )
        type_str = _annotation_type(by_name[name]) or "str"
        value = _coerce(name, type_str, raw)
        coerced[name] = value
        merged[name] = value

    _validate(merged)

    # Rewrite each touched single-line assignment in place: keep the
    # exact left-hand side (``NAME: type ``) and replace only the RHS.
    for name, value in coerced.items():
        node = by_name[name]
        ln = node.lineno - 1  # 0-based
        original = lines[ln]
        head, _, _ = original.partition("=")
        type_str = _annotation_type(node) or "str"
        lines[ln] = f"{head}= {_to_literal(type_str, value)}"

    new_src = "\n".join(lines)

    # Safety net: never leave settings.py unparseable.
    try:
        ast.parse(new_src)
    except SyntaxError as exc:  # pragma: no cover - defensive
        raise SettingsError(
            f"Refusing to write — the result would not parse: {exc}"
        ) from exc

    # Atomic replace so a crash mid-write cannot corrupt the file.
    fd, tmp = tempfile.mkstemp(
        dir=str(SETTINGS_PATH.parent), prefix=".settings_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new_src)
        os.replace(tmp, SETTINGS_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
