"""Read / write the Database Handler's question schedule.

The DH used to iterate a hardcoded ``SCHEDULE: list[dict]`` defined in
``agents/database_handler/database_handler.py``.  This module makes the
schedule USER-EDITABLE: the developer's "Questions for Saved Sessions"
web view reads + writes a JSON file
(``workflow_settings/dh_schedule.json``, gitignored) through these
helpers, and the DH itself loads the same JSON at save time (falling
back to the hardcoded list when the file is missing or malformed).

Data model — one entry per row of the editor table::

    {
      "id":          "<uuid4>",          # stable across sessions
      "name":        "Planner Problem",  # filename slug source
      "description": "...",              # what to ask; DH rephrases
      "from_agent":  "planner",          # agent_key, dropdown
      "to_agents":   ["receptionist"],   # future-RAG metadata only
      "scope":       "session" | "attempt",
      "type":        "Semantic" | "Quantitative",
      "parent_id":   null | "<uuid4>",   # the identifying Q(N)'s id
      "sub_index":   null | 1,           # 1, 2, 3 within parent
      "requires_dcii_enabled": false     # legacy seed flag
    }

The displayed ``Q1`` / ``Q4.2`` numbers are NOT stored; they are
computed at render time from the row's position and ``parent_id``.

Concurrency: writes are atomic via tempfile + rename (same pattern as
the settings editor).  The session-active lock is enforced at the HTTP
layer; this module assumes single-writer.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent

# Per-developer / per-deploy runtime file (gitignored).  Holds the
# user's CURRENT customisations; written by the editor + the
# upload endpoint.  When absent, the system seeds it from
# DEFAULT_SCHEDULE_PATH (tracked in the repo as the system's
# standard set of questions) — see :func:`_seed_default`.
SCHEDULE_PATH = _THIS_DIR / "dh_schedule.json"

# Tracked default — ships with the repo.  Whenever a deployment has
# no per-deploy ``dh_schedule.json`` yet (fresh install, deleted
# runtime file, image rebuild without a volume mount), this file
# becomes the seed for the editor's initial state.  Treat it as
# the system's "factory" set of questions; edit it in the repo, not
# at runtime.
DEFAULT_SCHEDULE_PATH = _THIS_DIR / "dh_schedule.default.json"

# Mirrors ``llm_routing.AGENT_KEYS`` order so the dropdowns line up
# across views.  The 10th key (``context_pruner``) is included but
# flagged ``wired=False`` in the agent metadata exposed to the UI.
AGENT_KEYS: list[str] = [
    "receptionist",
    "orchestrator",
    "user_input_inspector",
    "planner",
    "dc_input_creator",
    "dc_input_inspector",
    "dc_output_inspector",
    "tool_caller",
    "database_handler",
    "context_pruner",
    # 5-agent topology.  Listed for EVERY topology because this list
    # VALIDATES schedule entries (``from_agent`` and each target): omit
    # them and a schedule naming the Conductor or Creator is rejected,
    # so the DH could never interview the two agents that do all the
    # work in a 5-agent run.  A topology that does not build them simply
    # never produces a schedule entry naming them.
    "conductor",
    "creator",
]

# Short labels (the same as the LOG-and-Status chart uses on its boxes).
# Surfaced to the To-column popover so the user picks recognisable
# names instead of the canonical underscored keys.
AGENT_SHORT_LABELS: dict[str, str] = {
    "receptionist":         "Receptionist",
    "orchestrator":         "Orchestrator",
    "user_input_inspector": "UII",
    "planner":              "Planner",
    "dc_input_creator":     "DCIC",
    "dc_input_inspector":   "DCII",
    "dc_output_inspector":  "DCOI",
    "tool_caller":          "TC",
    "database_handler":     "DH",
    "context_pruner":       "CP",
    # 5-agent topology — without these the To-column popover would
    # fall back to the raw underscored keys for the two agents a
    # 5-agent run actually uses.
    "conductor":            "Conductor",
    "creator":              "Creator",
}

# Valid enum values.
SCOPES = ("session", "attempt")
TYPES = ("Semantic", "Quantitative")

# Filename slug helper — mirrors database_handler._slugify EXCEPT the
# editor uses underscores between Word_Like_Capitals so "Planner
# Problem" -> "Planner_Problem.txt".  The DH writer applies its own
# slugify on save; this is just the value we display in the UI.
_NON_FILENAME_SAFE = re.compile(r"[^\w]+")


def display_filename(name: str) -> str:
    """``Planner Problem`` -> ``Planner_Problem.txt`` (UI hint only)."""
    s = _NON_FILENAME_SAFE.sub("_", (name or "").strip()).strip("_")
    if not s:
        s = "entry"
    return f"{s}.txt"


class ScheduleError(ValueError):
    """Raised on an invalid edit; surfaced to the UI as HTTP 400."""


# ---------------------------------------------------------------------------
# Seed sources
# ---------------------------------------------------------------------------
#
# The "factory" set of questions ships in
# ``workflow_settings/dh_schedule.default.json``; ``_seed_default``
# loads it.  As a defence-in-depth fallback, ``_seed_from_hardcoded``
# rebuilds an equivalent list from the in-code ``SCHEDULE`` constant
# in ``agents/database_handler/database_handler.py`` — used only when
# the default JSON is missing or unparseable on disk.
#
# Resolution order in :func:`_seed_and_write`:
#   1. ``dh_schedule.default.json`` (tracked in repo)
#   2. hardcoded ``SCHEDULE`` constant
#   3. empty list (last-resort: at least the read API returns sanely)
# ---------------------------------------------------------------------------

def _seed_default() -> list[dict]:
    """Load the system's factory question set from
    ``dh_schedule.default.json``.

    Returns an empty list if the file is missing or unreadable — the
    caller then falls back to :func:`_seed_from_hardcoded`.  Light
    validation only: each entry is normalised through the same
    ``_normalise_for_write`` path the upload endpoint uses, so a
    malformed default never reaches disk as the runtime file.
    """
    if not _file_exists_and_nonempty(DEFAULT_SCHEDULE_PATH):
        return []
    try:
        raw = json.loads(DEFAULT_SCHEDULE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(raw, dict):
        return []
    questions = raw.get("questions")
    if not isinstance(questions, list):
        return []
    try:
        return _normalise_for_write(questions)
    except ScheduleError:
        return []


def _seed_from_hardcoded() -> list[dict]:
    """Last-resort seed built from the in-code ``SCHEDULE`` constant.

    Used only when ``dh_schedule.default.json`` is missing or
    unparseable.  Imported lazily so this module can still be loaded
    in environments where the agents package's heavy dependencies
    (langchain, etc.) are not available — e.g. a future schema
    migration tool.
    """
    try:
        from agents.database_handler.database_handler import SCHEDULE as _HARDCODED
    except Exception:  # pragma: no cover - defensive
        return []

    out: list[dict] = []
    for entry in _HARDCODED:
        agent_key = entry.get("agent_key", "")
        out.append({
            "id": _new_id(),
            "name": str(entry.get("field", "")).strip(),
            "description": str(entry.get("description", "")).strip(),
            "from_agent": agent_key,
            "to_agents": [],  # future-RAG metadata; user fills in later
            "scope": "session",
            "type": str(entry.get("type", "Semantic")).strip() or "Semantic",
            "parent_id": None,
            "sub_index": None,
            "requires_dcii_enabled": bool(
                entry.get("requires_dcii_enabled", False)
            ),
        })
    return out


def _new_id() -> str:
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def _file_exists_and_nonempty(path: Path) -> bool:
    try:
        return path.exists() and path.stat().st_size > 0
    except OSError:
        return False


def _load_raw() -> dict[str, Any] | None:
    if not _file_exists_and_nonempty(SCHEDULE_PATH):
        return None
    try:
        return json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _seed_and_write() -> dict[str, Any]:
    """Produce the initial runtime ``dh_schedule.json`` from the most
    authoritative source available.

    Resolution order:
      1. The tracked ``dh_schedule.default.json`` (factory standard).
      2. The in-code ``SCHEDULE`` constant (defence in depth).
      3. An empty list (last resort).
    """
    questions = _seed_default()
    source = "default.json"
    if not questions:
        questions = _seed_from_hardcoded()
        source = "hardcoded SCHEDULE"
        if not questions:
            source = "empty (no seed source available)"
    payload = {"version": 1, "questions": questions}
    _atomic_write(payload)
    try:
        import logging as _logging
        _logging.getLogger("propeller_agent").info(
            f"[dh_schedule] seeded runtime file with {len(questions)} "
            f"questions from {source}"
        )
    except Exception:
        pass
    return payload


def read_state() -> dict[str, Any]:
    """Return the schedule + the agent metadata the UI needs.

    Shape::

        {
          "version":   1,
          "questions": [<row>, ...],
          "agents": [
            {"key": "receptionist", "label": "Receptionist"},
            ...
          ],
          "scopes": ["session", "attempt"],
          "types":  ["Semantic", "Quantitative"]
        }
    """
    payload = _load_raw()
    if payload is None or not isinstance(payload, dict):
        payload = _seed_and_write()

    questions = payload.get("questions") or []
    if not isinstance(questions, list):
        questions = []

    # Backfill missing fields on legacy entries so the UI never sees a
    # row with absent keys.
    normalised: list[dict] = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        normalised.append({
            "id":           q.get("id") or _new_id(),
            "name":         str(q.get("name", "")).strip(),
            "description":  str(q.get("description", "")).strip(),
            "from_agent":   q.get("from_agent") or "",
            "to_agents":    list(q.get("to_agents") or []),
            "scope":        q.get("scope") or "session",
            "type":         q.get("type") or "Semantic",
            "parent_id":    q.get("parent_id") or None,
            "sub_index":    q.get("sub_index") or None,
            "requires_dcii_enabled": bool(q.get("requires_dcii_enabled", False)),
        })

    return {
        "version": int(payload.get("version", 1)),
        "questions": normalised,
        "agents": [
            {"key": k, "label": AGENT_SHORT_LABELS.get(k, k)}
            for k in AGENT_KEYS
        ],
        "scopes": list(SCOPES),
        "types": list(TYPES),
    }


def read_for_dh() -> list[dict]:
    """Return the schedule entries in DH-iteration form.

    Each entry has the keys the DH already understands
    (``agent_key`` / ``field`` / ``type`` / ``description`` /
    ``requires_dcii_enabled``) plus the new ``scope`` /
    ``to_agents`` / ``parent_id`` / ``sub_index`` / ``id`` fields the
    attempt-binding logic uses.
    """
    state = read_state()
    out: list[dict] = []
    for q in state["questions"]:
        out.append({
            "id":          q["id"],
            "agent_key":   q["from_agent"],
            "field":       q["name"],
            "description": q["description"],
            "type":        q["type"],
            "scope":       q["scope"],
            "parent_id":   q["parent_id"],
            "sub_index":   q["sub_index"],
            "to_agents":   list(q["to_agents"]),
            "requires_dcii_enabled": bool(q.get("requires_dcii_enabled", False)),
        })
    return out


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate(questions: list[dict]) -> None:
    """Enforce the contract the UI and the DH both rely on."""
    if not isinstance(questions, list):
        raise ScheduleError("'questions' must be a list.")

    ids: set[str] = set()
    names: dict[str, int] = {}  # name -> first index using it

    # First pass — per-row shape + uniqueness.
    for idx, q in enumerate(questions):
        if not isinstance(q, dict):
            raise ScheduleError(f"Row {idx}: not an object.")
        qid = q.get("id")
        if not isinstance(qid, str) or not qid.strip():
            raise ScheduleError(f"Row {idx}: missing 'id'.")
        if qid in ids:
            raise ScheduleError(f"Row {idx}: duplicate 'id' {qid!r}.")
        ids.add(qid)

        name = (q.get("name") or "").strip()
        if not name:
            raise ScheduleError(f"Row {idx}: 'name' is required.")
        prev = names.get(name)
        if prev is not None:
            raise ScheduleError(
                f"Row {idx}: 'name' {name!r} is already used by row "
                f"{prev}.  Pick a unique name (filenames would collide)."
            )
        names[name] = idx

        if not (q.get("description") or "").strip():
            raise ScheduleError(
                f"Row {idx} ({name!r}): 'description' is required."
            )

        from_agent = q.get("from_agent")
        if from_agent not in AGENT_KEYS:
            raise ScheduleError(
                f"Row {idx} ({name!r}): 'from_agent' must be one of "
                f"{AGENT_KEYS}, got {from_agent!r}."
            )

        to_agents = q.get("to_agents") or []
        if not isinstance(to_agents, list):
            raise ScheduleError(
                f"Row {idx} ({name!r}): 'to_agents' must be a list."
            )
        for t in to_agents:
            if t not in AGENT_KEYS:
                raise ScheduleError(
                    f"Row {idx} ({name!r}): 'to_agents' contains "
                    f"unknown agent {t!r}."
                )

        scope = q.get("scope")
        if scope not in SCOPES:
            raise ScheduleError(
                f"Row {idx} ({name!r}): 'scope' must be one of "
                f"{list(SCOPES)}, got {scope!r}."
            )

        qtype = q.get("type")
        if qtype not in TYPES:
            raise ScheduleError(
                f"Row {idx} ({name!r}): 'type' must be one of "
                f"{list(TYPES)}, got {qtype!r}."
            )

    # Second pass — parent / child structural rules.
    parent_children: dict[str, list[int]] = {}
    for idx, q in enumerate(questions):
        pid = q.get("parent_id")
        if pid is None:
            # Top-level row.  If scope is attempt, this is an
            # identifying Q(N).  Children attach below.
            continue
        if pid not in ids:
            raise ScheduleError(
                f"Row {idx} ({q.get('name')!r}): 'parent_id' "
                f"{pid!r} does not exist."
            )
        parent_children.setdefault(pid, []).append(idx)

    for idx, q in enumerate(questions):
        pid = q.get("parent_id")
        scope = q.get("scope")
        if pid is None:
            # Identifying Q(N) — must have at least one child.
            if scope == "attempt" and not parent_children.get(q["id"]):
                raise ScheduleError(
                    f"Row {idx} ({q.get('name')!r}): an attempt-"
                    f"specific Q(N) row must have at least one "
                    f"Q(N).1 child.  Add a sub-row or change scope "
                    f"to 'session'."
                )
        else:
            # Sub-row — must itself be attempt-scoped, and its parent
            # must also be attempt-scoped.
            if scope != "attempt":
                raise ScheduleError(
                    f"Row {idx} ({q.get('name')!r}): a sub-row "
                    f"(parent_id set) must have scope='attempt'."
                )
            parent = next(p for p in questions if p["id"] == pid)
            if parent.get("scope") != "attempt":
                raise ScheduleError(
                    f"Row {idx} ({q.get('name')!r}): parent row is "
                    f"not attempt-scoped — sub-row would be "
                    f"orphaned."
                )


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def _atomic_write(payload: dict[str, Any]) -> None:
    SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(SCHEDULE_PATH.parent),
        prefix=".dh_schedule_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, SCHEDULE_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _normalise_for_write(questions_in: list[Any]) -> list[dict]:
    """Coerce incoming JSON into the canonical row shape."""
    if not isinstance(questions_in, list):
        raise ScheduleError("'questions' must be a list.")

    out: list[dict] = []
    for idx, q in enumerate(questions_in):
        if not isinstance(q, dict):
            raise ScheduleError(f"Row {idx}: not an object.")
        out.append({
            "id":           (q.get("id") or _new_id()),
            "name":         str(q.get("name", "")).strip(),
            "description":  str(q.get("description", "")).strip(),
            "from_agent":   (q.get("from_agent") or "").strip(),
            "to_agents":    [str(x) for x in (q.get("to_agents") or [])],
            "scope":        (q.get("scope") or "session").strip(),
            "type":         (q.get("type") or "Semantic").strip(),
            "parent_id":    (q.get("parent_id") or None),
            "sub_index":    (
                int(q["sub_index"]) if isinstance(q.get("sub_index"), int)
                else None
            ),
            "requires_dcii_enabled": bool(q.get("requires_dcii_enabled", False)),
        })
    return out


def write_updates(payload: Any) -> None:
    """Validate + atomically write the schedule.

    *payload* is the full replacement schedule (the editor sends the
    table state on every Save).  Raises :class:`ScheduleError` on any
    invalid input — the file is left untouched in that case.
    """
    if not isinstance(payload, dict):
        raise ScheduleError("Expected a JSON object.")
    version = int(payload.get("version", 1))
    questions = _normalise_for_write(payload.get("questions") or [])
    _validate(questions)
    _atomic_write({"version": version, "questions": questions})


def parse_uploaded(raw_bytes: bytes) -> dict[str, Any]:
    """Parse + validate an uploaded JSON file.

    Returns the canonical payload that the UI uses to replace its
    in-memory table state.  Does NOT write to disk — the user must
    click Save to persist.  Raises :class:`ScheduleError` on parse or
    validation failure.
    """
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ScheduleError(
            f"Uploaded file is not valid UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ScheduleError("Uploaded JSON must be an object.")
    questions = _normalise_for_write(payload.get("questions") or [])
    _validate(questions)
    return {
        "version": int(payload.get("version", 1)),
        "questions": questions,
    }


def download_payload() -> bytes:
    """Return the on-disk JSON for the Download button.

    Falls back to the live ``read_state`` shape (minus the read-only
    UI metadata) when the file is missing, so the user always gets a
    valid JSON.
    """
    if _file_exists_and_nonempty(SCHEDULE_PATH):
        return SCHEDULE_PATH.read_bytes()
    state = read_state()
    payload = {
        "version": state["version"],
        "questions": state["questions"],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
