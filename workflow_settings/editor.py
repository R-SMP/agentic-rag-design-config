"""Read and safely rewrite ``workflow_settings/settings.py`` for the
web Workflow Settings editor.

Only the right-hand side of each top-level ``NAME: type = value``
assignment is rewritten; the module docstring, every comment, blank
lines and ordering are preserved verbatim.  ``settings.py`` stays the
single source of truth (``agents/loader.py`` and the web / CLI
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
    "GEOMETRY_BACKEND": ["feg", "rhino"],
    "DCOI_COMPARISON_MODE": [1, 2, 3],
    # Agent topology — the value IS the agent count.  Adding a further
    # variant needs only a new agents/<N>agent/ folder and N here.
    "SYSTEM_TOPOLOGY": [7, 5, 3],
    "EMBEDDING_PROVIDER": ["OpenAI"],
    # Which LLM answers when the Database Handler interviews an agent.
    # "Original Agent" is a SENTINEL, not a provider: it means "each
    # agent answers on its own live model" (the historic behaviour) and
    # makes DH_INTERVIEW_MODEL inert.  The other four are the real
    # providers, matching agents/shared/llm_provider._API_KEY_ENV_VARS.
    "DH_INTERVIEW_PROVIDER": [
        "Original Agent", "openai", "anthropic", "google", "openrouter",
    ],
    # STITCHING_PROVIDER is locked to a single-option dropdown
    # (matches EMBEDDING_PROVIDER's pattern).  The Anthropic and
    # Google branches in db_writer.stitch_for_embedding are T16 /
    # T17 in the architecture doc — add their values here when
    # those branches land.
    "STITCHING_PROVIDER": ["OpenAI"],
    # Prompt caching (Anthropic only).  Scope = WHAT gets a cache
    # breakpoint; TTL = how long entries live.  Kept as two settings
    # because a system-only cache still has a lifetime.  See
    # workflow_settings/settings.py §29.
    "PROMPT_CACHE_SCOPE": ["off", "system", "system+history"],
    "PROMPT_CACHE_TTL": ["5m", "1h"],
    # Same two knobs for the post-session Database Handler save.  Same
    # values, same meaning, same machinery — separate only so the save
    # can be tuned without disturbing the session.  See §30.
    "PROMPT_CACHE_SCOPE_SAVE": ["off", "system", "system+history"],
    "PROMPT_CACHE_TTL_SAVE": ["5m", "1h"],
    # Which OpenAI endpoint the ``openai`` provider talks to, and how
    # hard its reasoning models think.  "provider default" is a
    # SENTINEL, not a value: it sends no effort field at all and lets
    # each model apply its own.  See workflow_settings/settings.py §32
    # for why chat/completions cannot carry tools AND reasoning.
    "OPENAI_API_STYLE": ["responses", "chat"],
    "OPENAI_REASONING_EFFORT": [
        "provider default", "none", "low", "medium", "high",
    ],
}

# Derived from the environment via os.getenv — show read-only, mask
# the value, never rewrite.
DERIVED_READONLY = {"EMBEDDING_API_KEY"}

# Hidden from the flag-list UI and rejected by ``write_updates``.
# Owned by a dedicated control surface (the LLM-routing panel via
# workflow_settings/llm_routing.py; the two render-compression degrees via
# the "Render compression" panel).  The internal write path
# ``write_internal`` is the only way to mutate these names.
#
# EMBEDDING_INPUT_MAX_CHARS and DATABASE_ENTRY_RETRY_BACKOFF_SECONDS
# are internal tuning knobs for db_writer.py — they live in settings.py
# for easier developer access but are NOT surfaced in the UI.  Change
# them via a code edit.
HIDDEN_FROM_FLAG_LIST = {
    "LLM_ROUTING_MODE",
    "EMBEDDING_INPUT_MAX_CHARS",
    "DATABASE_ENTRY_RETRY_BACKOFF_SECONDS",
    # Owned by the dedicated "Render compression" panel, which previews each
    # degree against sample renders with a slider.
    "IMAGE_COMPRESSION_CROSS_SECTIONS_DEGREE",
    "IMAGE_COMPRESSION_3D_RENDER_DEGREE",
}

_FENCE_RE = re.compile(r"^#+\s*=+\s*$")


# Settings that a TOPOLOGY renders meaningless.  The flag list still shows
# them, with their real stored value, but greyed out and refused by
# ``_do_write`` -- because the code already ignores them there and a live
# toggle that silently does nothing is worse than no toggle at all.
#
# name -> (topologies where the setting is INERT, why)
_INERT_UNDER_TOPOLOGY: dict[str, tuple[frozenset, str]] = {
    "DC_INSPECTOR_ENABLED": (
        frozenset({5, 3}),
        "Only meaningful in the 7-agent topology.  The DC Input Inspector "
        "was merged away in the reduced topologies, so there is no agent "
        "for this flag to switch on: prompts._dcii_effective() forces it "
        "False whenever SYSTEM_TOPOLOGY is not 7.",
    ),
    "PLANNER_FIRST": (
        frozenset({5, 3}),
        "Only meaningful in the 7-agent topology.  In the reduced "
        "topologies the hub IS the planner, so there is no Planner/UII "
        "ordering to choose: prompts._planner_first_effective() forces it "
        "False whenever SYSTEM_TOPOLOGY is not 7.",
    ),
    "CHAIN_ACCESS": (
        frozenset({5, 3}),
        "Only meaningful in the 7-agent topology.  Reading the other "
        "agents' traffic was the ORCHESTRATOR's power and left the system "
        "with it: Planner5 has no chain-access feed, and the Architect "
        "never had one.  Both hubs see only the hand-off addressed to "
        "them, whatever this flag says.",
    ),
}


def _inert_reason(name: str, topology: Any) -> str:
    """Why *name* is inert under *topology*, or "" if it is live."""
    entry = _INERT_UNDER_TOPOLOGY.get(name)
    if entry is None:
        return ""
    topologies, reason = entry
    try:
        topo = int(topology)
    except (TypeError, ValueError):
        return ""
    return reason if topo in topologies else ""

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

    # The topology the file currently declares, for the inert-setting
    # marking below.
    _topology_literal = None
    for _n in nodes:
        if _n.target.id == "SYSTEM_TOPOLOGY":
            _ok, _topology_literal = _literal(_n.value)
            break

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

        if name in HIDDEN_FROM_FLAG_LIST:
            continue

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

        # Inert-under-this-topology marking.  Computed from the file's own
        # SYSTEM_TOPOLOGY literal, not from the imported settings module,
        # so it agrees with what a save would actually write.
        reason = _inert_reason(name, _topology_literal)
        if reason:
            item["disabled"] = True
            item["disabled_note"] = reason

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


_LLM_ROUTING_MODES = {"individual", "openai", "anthropic", "google", "openrouter"}


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
    mode = merged.get("LLM_ROUTING_MODE")
    if mode is not None and mode not in _LLM_ROUTING_MODES:
        raise SettingsError(
            f"LLM_ROUTING_MODE must be one of "
            f"{sorted(_LLM_ROUTING_MODES)}, got {mode!r}."
        )


def write_updates(updates: dict[str, Any]) -> None:
    """Validate ``updates`` and rewrite only the touched assignment
    lines in ``settings.py``, preserving everything else.

    Raises :class:`SettingsError` (a ``ValueError``) on any invalid or
    disallowed edit; the file is left untouched in that case.

    Names in :data:`HIDDEN_FROM_FLAG_LIST` are rejected here — they are
    owned by a dedicated module and must use :func:`write_internal`.
    """
    _do_write(updates, allow_hidden=False)


def write_internal(updates: dict[str, Any]) -> None:
    """Trusted-caller variant of :func:`write_updates` that may also
    write names in :data:`HIDDEN_FROM_FLAG_LIST`.

    Callers must pass only fixed setting names with server-validated values.
    Used by the routing module (``workflow_settings/llm_routing.py``, which
    validates its own payload) and directly by the render-compression panel's
    ``POST /api/render_compression`` handler (web_app.py), which passes only
    the two ``IMAGE_COMPRESSION_*_DEGREE`` names clamped to [0, 100].
    """
    _do_write(updates, allow_hidden=True)


def _do_write(updates: dict[str, Any], *, allow_hidden: bool) -> None:
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
        if name in HIDDEN_FROM_FLAG_LIST and not allow_hidden:
            raise SettingsError(
                f"{name} is not editable via this endpoint."
            )
        # Refuse a change the active topology would ignore.  The UI greys
        # these out, but SettingsIn.values is an untyped dict, so without
        # this the grey-out would be cosmetic only.  The topology CHECKED is
        # the one this same write produces, so switching to 7 and flipping
        # PLANNER_FIRST in a single save is still allowed.
        effective_topology = updates.get(
            "SYSTEM_TOPOLOGY", merged.get("SYSTEM_TOPOLOGY"))
        reason = _inert_reason(name, effective_topology)
        if reason:
            raise SettingsError(f"{name} cannot be changed: {reason}")
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

    # Preserve the file's OWN line ending.  ``_parse_nodes`` reads with
    # universal newlines, so ``lines`` are \n-separated whatever is on disk;
    # writing them back through a hard-coded newline="\\n" rewrote a CRLF
    # settings.py to LF on the FIRST save, turning a one-toggle change into
    # a whole-file diff.
    newline = "\r\n" if b"\r\n" in SETTINGS_PATH.read_bytes() else "\n"
    # Atomic replace so a crash mid-write cannot corrupt the file.
    fd, tmp = tempfile.mkstemp(
        dir=str(SETTINGS_PATH.parent), prefix=".settings_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as fh:
            fh.write(new_src)
        os.replace(tmp, SETTINGS_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
