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
import logging
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

# The session logger, so a schedule defect surfaces in the session log
# (and therefore in the R2-archived copy) rather than only on stderr.
logger = logging.getLogger("propeller_agent")

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent

# The schedule is PER TOPOLOGY.  Topology 7's row set names the
# Orchestrator and the DC Input Inspector — as an answering agent on
# four rows, and in most ``to_agents`` lists — and neither exists in
# topology 5.  A row whose ``from_agent`` the active hub does not build
# does not merely warn: ``_phase_3c_persist_chunk(..., is_error=True)``
# writes an ``ERROR:`` row into the R2 mirror and the Postgres
# ``chunks`` table, where it comes back at retrieval time.
#
# Two files rather than an alias at the lookup, on the owner's call.
# The infix goes on the BASE name, not via ``Path.stem`` —
# ``Path("dh_schedule.default.json").stem`` is ``"dh_schedule.default"``,
# so the naive form would yield ``dh_schedule.default_5agents.json``.
#
# Resolved per CALL, never captured: the Sessions Queue switches
# ``SYSTEM_TOPOLOGY`` between runs inside one process, so a module
# constant would pin whichever topology was active at import.  Topology 7
# resolves to exactly the historic paths, so it needs no migration.
_SCHEDULE_BY_TOPOLOGY = {5: "_5agents"}


def active_topology() -> int:
    """The topology number currently in force.

    Duplicates ``agents/shared/topology.py``'s ``topology()`` rather than
    importing it, because the dependency runs the other way: that module
    imports ``workflow_settings``, and reaching it from here would pull
    ``agents/__init__.py`` -- which eagerly imports every agent class, and
    with them langchain -- into the settings layer.  ``dh_schedule`` must
    stay importable without it.

    Public so the POST handler can compare against the SAME reading this
    module resolves its paths with, rather than a second opinion.
    """
    from workflow_settings import settings as _settings

    return int(getattr(_settings, "SYSTEM_TOPOLOGY", 7))


def _topology_infix() -> str:
    """``"_5agents"`` for a topology with its own schedule, else ``""``."""
    return _SCHEDULE_BY_TOPOLOGY.get(active_topology(), "")


def schedule_path() -> Path:
    """The active topology's per-deploy runtime file (gitignored).

    Holds the user's CURRENT customisations; written by the editor and
    the upload endpoint.  When absent, the system seeds it from
    :func:`default_schedule_path` — see :func:`_seed_default`.
    """
    return _THIS_DIR / f"dh_schedule{_topology_infix()}.json"


def default_schedule_path() -> Path:
    """The active topology's tracked default — ships with the repo.

    Whenever a deployment has no per-deploy runtime file yet (fresh
    install, deleted runtime file, image rebuild without a volume
    mount), this file becomes the seed for the editor's initial state.
    Treat it as the system's "factory" set of questions; edit it in the
    repo, not at runtime.
    """
    return _THIS_DIR / f"dh_schedule{_topology_infix()}.default.json"

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
    # 5-agent topology introduces no new keys -- its agents (planner,
    # user_input_inspector, dc_input_creator, tool_caller,
    # dc_output_inspector, receptionist) are all listed above.  The list
    # stays a cross-topology SUPERSET because it VALIDATES schedule entries
    # (``from_agent`` and each target); a topology that does not build an
    # agent simply never produces an entry naming it.
    # 3-agent topology.
    "architect",
    "designer",
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
    "architect":            "Architect",
    "designer":             "Designer",
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
    _default_path = default_schedule_path()
    if not _file_exists_and_nonempty(_default_path):
        return []
    try:
        raw = json.loads(_default_path.read_text(encoding="utf-8"))
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
    _path = schedule_path()
    if not _file_exists_and_nonempty(_path):
        return None
    try:
        return json.loads(_path.read_text(encoding="utf-8"))
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
          "types":  ["Semantic", "Quantitative"],
          "topology": 7
        }

    ``topology`` is the topology these rows were READ under.  The editor
    echoes it back on Save so a write cannot land in another topology's
    file — see :func:`schedule_path` and the POST handler in web_app.py.
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
        # NOT used to filter `agents` above: AGENT_KEYS lists `architect`
        # and `designer`, which no topology roster claims, so filtering
        # would drop them from topology 7's From dropdown.  This value
        # exists only to make the Save round-trip topology-safe.
        "topology": active_topology(),
    }


def _schedule_problem(questions: list[dict]) -> str | None:
    """The first contract violation in *questions*, or None when clean.

    :func:`_validate` raises on the first problem it finds; this wraps it
    so a caller can REPORT rather than refuse.
    """
    try:
        _validate(questions)
    except ScheduleError as exc:
        return str(exc)
    except Exception as exc:  # pragma: no cover — defensive
        return f"{type(exc).__name__}: {exc}"
    return None


def _reorder_children(questions: list[dict]) -> tuple[list[dict], int]:
    """Move every sub-row to sit directly below its parent.

    Returns ``(rows, n_shifted)``.  Stable: top-level rows keep their
    order, and a parent's children keep their order among themselves.
    A sub-row whose ``parent_id`` matches no row is left exactly where
    it is — quietly relocating an orphan would hide a real defect that
    :func:`_schedule_problem` has already reported.

    This is a REPAIR, not a validation: it recovers the sub-rows that
    the DH's forward-scanning collector would otherwise skip, and it
    cannot change meaning, because a schedule's row order carries no
    information beyond block membership and iteration sequence.
    """
    ids = {q.get("id") for q in questions}
    by_parent: dict[str, list[dict]] = {}
    for q in questions:
        pid = q.get("parent_id")
        if pid and pid in ids:
            by_parent.setdefault(pid, []).append(q)
    if not by_parent:
        return list(questions), 0

    out: list[dict] = []
    for q in questions:
        pid = q.get("parent_id")
        if pid and pid in ids:
            continue                      # emitted under its parent below
        out.append(q)
        out.extend(by_parent.get(q.get("id")) or [])

    shifted = sum(1 for a, b in zip(questions, out) if a is not b)
    return out, shifted


def read_for_dh() -> list[dict]:
    """Return the schedule entries in DH-iteration form.

    Each entry has the keys the DH already understands
    (``agent_key`` / ``field`` / ``type`` / ``description`` /
    ``requires_dcii_enabled``) plus the new ``scope`` /
    ``to_agents`` / ``parent_id`` / ``sub_index`` / ``id`` fields the
    attempt-binding logic uses.

    THIS IS THE ONLY PATH THE DH READS, and until now it was the only
    path with no validation at all: ``_validate`` runs on
    :func:`write_updates` and :func:`parse_uploaded` — the two HTTP
    write paths — so a hand-edited, migrated or freshly-seeded
    ``dh_schedule.json`` reached the DH completely unchecked.

    Two deliberate choices here:

    * **Report, never raise.**  A malformed schedule must not be able to
      block a save outright; losing one row's contract is bad, losing
      the whole session's answers is worse.  The problem is logged at
      ERROR so it is visible in the session log and in the R2-archived
      copy.
    * **Repair the one defect that silently destroys data.**
      Non-contiguous sub-rows are moved back under their parent (see
      :func:`_reorder_children`).  Every other violation is reported and
      left alone — repairing a bad ``scope`` or ``type`` would change
      which write path a row takes, which is a decision for the author,
      not for the loader.

    The file on disk is never modified by this function.
    """
    state = read_state()
    rows = state["questions"]

    problem = _schedule_problem(rows)
    if problem:
        logger.error(
            "[DH-SCHEDULE]  the schedule on disk violates its own "
            "contract: %s  Continuing with the rows as they are — fix "
            "this in the “Questions for Saved Sessions” view.",
            problem,
        )

    rows, n_shifted = _reorder_children(rows)
    if n_shifted:
        logger.warning(
            "[DH-SCHEDULE]  repaired sub-row placement: %d row(s) were "
            "not directly below their parent and would have been "
            "SILENTLY DROPPED from this save.  Moved back under their "
            "parent in memory; the file on disk is unchanged.",
            n_shifted,
        )

    out: list[dict] = []
    for q in rows:
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

    # Third pass — sub-rows must be CONTIGUOUS, immediately below their
    # parent.
    #
    # The Database Handler collects a block's sub-rows by walking
    # FORWARD from the parent and stopping at the first row whose
    # parent_id does not match.  So a row wedged into a Q(N) block makes
    # every sub-row from that point on invisible at save time: no .txt,
    # no chunks row, a single INFO line.  The DH's own comment claims
    # this validator enforces contiguity; until now it did not.
    for pid, child_idxs in parent_children.items():
        parent_idx = next(
            i for i, q in enumerate(questions) if q.get("id") == pid
        )
        expected = list(
            range(parent_idx + 1, parent_idx + 1 + len(child_idxs))
        )
        if sorted(child_idxs) != expected:
            raise ScheduleError(
                f"Row {parent_idx} ({questions[parent_idx].get('name')!r}): "
                f"its {len(child_idxs)} sub-row(s) must sit immediately "
                f"below it with nothing in between — found at rows "
                f"{sorted(child_idxs)}, expected {expected}.  A row "
                f"wedged into a Q(N) block makes the Database Handler "
                f"skip every sub-row from that point on."
            )


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def _atomic_write(payload: dict[str, Any]) -> None:
    _path = schedule_path()
    _path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(_path.parent),
        prefix=".dh_schedule_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, _path)
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
    _path = schedule_path()
    if _file_exists_and_nonempty(_path):
        return _path.read_bytes()
    state = read_state()
    payload = {
        "version": state["version"],
        "questions": state["questions"],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
