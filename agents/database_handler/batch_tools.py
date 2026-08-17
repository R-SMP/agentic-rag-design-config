"""Forced-tool definitions and pure helpers for the Database Handler's
BATCHED interview.

Why this exists
---------------
The DH used to walk its schedule one row at a time: for every row it made
three LLM calls (write the question, ask the agent, decide ASK-or-SAVE).
Batching asks an agent several NEIGHBOURING questions in ONE call, so a
group of N rows costs three calls instead of ``3 x N``.

That only works if each answer can be mapped back to the right schedule
row, because a row's identity decides its filename, its ``field`` /
``type`` / ``to_agents`` metadata and whether its ``chunks`` row is
session- or attempt-scoped.  Getting that mapping wrong is worse than not
batching at all: the database has no reliable backstop for it (a
session-scoped duplicate inserts TWICE, an attempt-scoped one is
discarded at INFO — see F59 in ``extra_utilities/TODO_known_issues.md``),
so the mapping has to be right here, before anything is written.

Hence the two design choices this module encodes:

**1. Structured tool calls, not text parsing.**  Every DH decision that
used to be prose (``ASK:`` / ``SAVE:`` with ``QUESTION:`` / ``ANSWER:`` /
``ATTEMPT:`` headers) becomes a forced tool call with a schema.  The old
text protocol failed in ways that were invisible: an ``ATTEMPT:`` header
with markdown on it silently became answer text, and an untagged block
inherited the previous block's attempt id.

**2. Labels, not names or uuids.**  Each tool call carries short,
save-local labels (``R1`` for the plan, ``A``/``B``/``C`` inside a batch)
that this module maps back to the row's stable ``id``.  Row NAMES look
like the obvious key — they are validated unique — but that uniqueness is
string-level, while the DH files by ``_slugify``, so ``Bad Attempt`` and
``bad attempt`` are two distinct names that write to one file.  Uuids
survive that but cost tokens on every question and answer and cannot be
checked when mis-echoed.  A short local label is unique by construction
within the call that uses it, and a wrong one fails the coverage check
instead of quietly landing under another row.

Tool binding
------------
None of these is ever left bound on the DH.  Each is bound for ONE turn
via ``base_llm.bind_tools([tool], tool_choice=<name>)`` and discarded —
the W18 / W20 invariant that ``submit_feedback_dispatch`` already
follows.  The DH's LLM therefore only ever sees one tool schema at a
time.

Every ``@tool`` body returns ``""``.  The DH reads the arguments off the
response's ``tool_calls`` and does the real work itself, the same pattern
``dh_tools.save_attempt_data`` uses.

NOT YET WIRED.  Nothing calls anything in this module: ``populate_database``
still runs the one-row-at-a-time loop.  This is step 3a of the batching
build (additive only); 3b wires the session-scoped path, 3c the
attempt-identifying one.
"""

from __future__ import annotations

from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# Tool names — referenced by the DH when it binds each tool with
# ``tool_choice``, so they live next to the definitions rather than being
# spelled out again at the call site.
# ---------------------------------------------------------------------------

SUBMIT_BATCH_PLAN_TOOL_NAME = "submit_batch_plan"
SUBMIT_QUESTIONS_TOOL_NAME = "submit_questions"
SUBMIT_BATCH_TOOL_NAME = "submit_batch"


@tool
def submit_batch_plan(batches: list[dict]) -> str:
    """Decide which schedule rows are asked together in one call.

    You are shown the whole schedule split into CANDIDATE RUNS.  A run is
    a stretch of consecutive rows that go to the same agent about the
    same kind of thing; you may only group rows that sit in the SAME run,
    because rows in different runs cannot physically share one call.

    Group aggressively — every group of N rows saves 2 x (N-1) LLM calls
    — but only where one combined answer would be as good as N separate
    ones.  Questions on a shared topic batch well.  So do questions on
    unrelated but independent topics.  Do NOT batch questions that pull
    in OPPOSITE directions (for example "what was the best attempt?" with
    "what was the worst attempt?"): a single reply covering both tends to
    blur them, and a blurred answer is worse than an extra call.  A group
    of one is a perfectly good answer.

    Args:
        batches: One entry per group, in any order, as
            ``{"labels": ["R3", "R4"]}``.  Use the ``R<n>`` labels
            exactly as shown.  EVERY label in every run must appear in
            exactly one group.

    Returns:
        Empty string — the Database Handler reads your arguments directly.
    """
    return ""


@tool
def submit_questions(questions: list[dict]) -> str:
    """Write the question for each row in the batch you are about to ask.

    One entry per row, using the row's batch label.  Each question is
    delivered to the agent in a single message and is also stored
    verbatim next to the answer in the database, so write it as a
    self-contained question, not as "and also, for B, ...".

    Args:
        questions: ``[{"label": "A", "question": "..."}, ...]`` — one per
            label in the batch, no extras, no omissions.

    Returns:
        Empty string — the Database Handler reads your arguments directly.
    """
    return ""


@tool
def submit_batch(
    saves: list[dict],
    followups: list[dict],
    skips: list[str],
) -> str:
    """Record what to do with each row in the batch you just asked.

    Every label in the batch must appear in exactly one of the three
    lists (a label may appear MORE than once in ``saves`` when the
    agent's reply contains several distinct items worth storing
    separately — each becomes its own database entry).

    Args:
        saves: Entries to store, as ``{"label", "question", "answer"}``.
            ``question`` and ``answer`` are what actually get saved and
            embedded, so apply the rewrite rules from your system prompt
            to BOTH.  Add ``"attempt"`` only for a row about one specific
            design attempt, naming that attempt.
        followups: Rows you cannot settle yet, as
            ``{"label", "question"}`` — the question is put to the agent
            in the next round.  Rows already in ``saves`` or ``skips``
            are never re-asked.
        skips: Labels with nothing worth storing this session, as a plain
            list of label strings.  Use this instead of saving a
            "nothing to report" sentence: an empty negation adds nothing
            to the database and competes with real content at search
            time.

    Returns:
        Empty string — the Database Handler reads your arguments directly.
    """
    return ""


# ---------------------------------------------------------------------------
# Candidate runs
# ---------------------------------------------------------------------------

def is_identifying(entry: dict) -> bool:
    """True when *entry* is an attempt-IDENTIFYING row.

    Structural, never by name: any top-level row whose scope is
    ``attempt``.  Its job is to pin down WHICH design attempt the rows
    beneath it describe.
    """
    return (
        entry.get("scope") == "attempt"
        and entry.get("parent_id") is None
    )


def candidate_runs(entries: list[dict]) -> list[list[dict]]:
    """Split *entries* into the runs a batch may not reach outside of.

    A run is a maximal stretch of CONSECUTIVE rows agreeing on three
    stored fields — ``agent_key``, ``scope`` and ``parent_id``.  None of
    the three is a matter of judgement, which is why they are decided
    here and everything else is left to the DH:

    * **agent_key** — a different agent has to answer, so one call
      physically cannot cover both.
    * **scope** — session- and attempt-scoped rows take different write
      paths (an attempt row carries an attempt id, a ``__NNN`` filename
      suffix and an attempt-scoped ``chunks`` row), so mixing them in one
      answer set risks filing a row against the wrong one.
    * **parent_id** — a sub-row cannot even be ASKED until its parent has
      resolved which attempt it is about.  That is a data dependency, not
      a preference.

    IDENTIFYING rows are additionally forced into runs of their own.
    Such a row must bind an attempt before anything attempt-scoped can be
    written, and a reply that also covers unrelated questions is a reply
    that can name the wrong attempt — which would then mis-file every
    child under it.

    Returns runs in schedule order, each preserving its rows' order.
    Rows are never dropped: ``sum(len(r) for r in runs) == len(entries)``.
    """
    runs: list[list[dict]] = []
    prev_key = None
    for entry in entries:
        if is_identifying(entry):
            runs.append([entry])
            prev_key = None            # nothing may join an identifying run
            continue
        key = (
            entry.get("agent_key"),
            entry.get("scope"),
            entry.get("parent_id"),
        )
        if runs and prev_key == key:
            runs[-1].append(entry)
        else:
            runs.append([entry])
        prev_key = key
    return runs


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

def _plan_label(index: int) -> str:
    """``R1``, ``R2``, ... — the label used across the whole plan call."""
    return f"R{index + 1}"


def _batch_label(index: int) -> str:
    """``A``, ``B``, ... ``Z``, ``AA``, ``AB``, ... — used inside one batch.

    Letters rather than numbers because a batch is small and adjacent
    letters are harder to transpose than adjacent digits; the plan call,
    which has to name every row in the schedule at once, uses ``R<n>``
    instead since 36 letters would run past ``Z``.
    """
    label = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        label = chr(ord("A") + rem) + label
    return label


def label_rows(rows: list[dict], style: str = "batch") -> dict[str, dict]:
    """Map a fresh label onto each row, in order.

    ``style="plan"`` gives ``R1..Rn`` (the whole schedule in one call);
    ``style="batch"`` gives ``A..Z, AA..`` (one group).  Labels are
    computed per call and never persisted, so they cannot go stale.

    Returns an ordered ``{label: row}`` dict — insertion order is the
    rows' order, so callers can render the list without re-sorting.
    """
    make = _plan_label if style == "plan" else _batch_label
    return {make(i): row for i, row in enumerate(rows)}


# ---------------------------------------------------------------------------
# Batch-result validation
# ---------------------------------------------------------------------------

def read_batch_result(
    args: dict, open_labels: set[str],
) -> tuple[dict[str, list[dict]], dict[str, str], set[str], list[str]]:
    """Parse + check one ``submit_batch`` result.

    Returns ``(saves_by_label, followups_by_label, skipped, problems)``.

    The coverage rule is what makes a mis-mapped answer impossible to
    miss: every still-open label must appear in exactly one of the
    three lists (``saves`` may repeat a label — that is the
    multi-answer split).  A label the DH invented, and a label it
    forgot, are both reported by name so the retry can be specific.
    """
    saves: dict[str, list[dict]] = {}
    followups: dict[str, str] = {}
    skipped: set[str] = set()
    problems: list[str] = []
    seen: set[str] = set()

    for item in (args.get("saves") or []):
        if not isinstance(item, dict):
            problems.append("a 'saves' entry is not an object.")
            continue
        label = str(item.get("label") or "").strip()
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if label not in open_labels:
            problems.append(
                f"saves names {label!r}, which is not a label in "
                f"this batch."
            )
            continue
        if not question or not answer:
            problems.append(
                f"the save for {label} is missing its question or "
                f"its answer."
            )
            continue
        attempt = str(item.get("attempt") or "").strip() or None
        saves.setdefault(label, []).append(
            {"question": question, "answer": answer, "attempt": attempt}
        )
        seen.add(label)

    for item in (args.get("followups") or []):
        if not isinstance(item, dict):
            problems.append("a 'followups' entry is not an object.")
            continue
        label = str(item.get("label") or "").strip()
        question = str(item.get("question") or "").strip()
        if label not in open_labels:
            problems.append(
                f"followups names {label!r}, which is not a label "
                f"in this batch."
            )
            continue
        if not question:
            problems.append(f"the follow-up for {label} has no question.")
            continue
        if label in seen:
            problems.append(
                f"{label} is both saved and followed up; pick one."
            )
            continue
        followups[label] = question
        seen.add(label)

    for raw in (args.get("skips") or []):
        label = str(
            raw.get("label") if isinstance(raw, dict) else raw
        ).strip()
        if label not in open_labels:
            problems.append(
                f"skips names {label!r}, which is not a label in "
                f"this batch."
            )
            continue
        if label in seen:
            problems.append(
                f"{label} is skipped as well as saved or followed "
                f"up; pick one."
            )
            continue
        skipped.add(label)
        seen.add(label)

    missing = sorted(open_labels - seen)
    if missing:
        problems.append(
            "these labels were not covered at all: "
            + ", ".join(missing)
        )
    return saves, followups, skipped, problems


# ---------------------------------------------------------------------------
# Plan validation
# ---------------------------------------------------------------------------

def validate_plan(
    batches: list,
    runs: list[list[dict]],
    labels: dict[str, dict],
) -> tuple[list[list[dict]], list[str]]:
    """Turn the DH's proposed ``batches`` into concrete groups of rows.

    Returns ``(groups, problems)``.  ``problems`` is a list of
    human-readable complaints for the retry prompt; it is empty when the
    plan was accepted exactly as proposed.

    Enforced:

    * every label is one this plan call actually offered;
    * no label is used twice;
    * every row is covered;
    * a group never spans two runs.

    A group that breaks the last rule is SPLIT along run boundaries
    rather than discarded — the DH's intent to batch those rows is still
    honoured as far as it legally can be — and the split is reported.

    Rows the DH failed to mention are returned as singleton groups, so a
    partial plan degrades to "ask that row on its own" rather than losing
    it.  The caller decides whether the reported problems are worth one
    retry before accepting the result.
    """
    # Keyed on id() rather than equality: rows are plain dicts, and two
    # schedule rows with the same content would otherwise collapse into
    # one entry and mis-report which run a label belongs to.
    label_of = {id(row): label for label, row in labels.items()}
    run_of: dict[str, int] = {
        label_of[id(row)]: run_idx
        for run_idx, run in enumerate(runs)
        for row in run
        if id(row) in label_of
    }

    problems: list[str] = []
    groups: list[list[dict]] = []
    seen: set[str] = set()

    for pos, batch in enumerate(batches or []):
        if isinstance(batch, dict):
            raw = batch.get("labels") or []
        elif isinstance(batch, list):
            raw = batch                      # tolerate a bare list of labels
        else:
            problems.append(
                f"batch #{pos + 1} is not an object with a 'labels' list."
            )
            continue

        wanted: list[str] = []
        for label in raw:
            label = str(label).strip()
            if label not in labels:
                problems.append(
                    f"batch #{pos + 1} names {label!r}, which is not a "
                    f"label in this schedule."
                )
                continue
            if label in seen:
                problems.append(
                    f"{label} appears in more than one batch; a row can "
                    f"only be asked once."
                )
                continue
            seen.add(label)
            wanted.append(label)

        if not wanted:
            continue

        # Split along run boundaries, preserving order within each part.
        by_run: dict[int, list[str]] = {}
        for label in wanted:
            by_run.setdefault(run_of[label], []).append(label)
        if len(by_run) > 1:
            problems.append(
                f"batch #{pos + 1} mixes rows that cannot share one call "
                f"(different agent, scope or parent): "
                f"{', '.join(wanted)}.  Split into {len(by_run)} groups."
            )
        for part in by_run.values():
            groups.append([labels[label] for label in part])

    missing = [label for label in labels if label not in seen]
    if missing:
        problems.append(
            f"these rows were left out of the plan and will each be "
            f"asked on their own: {', '.join(missing)}."
        )
        for label in missing:
            groups.append([labels[label]])

    # Emit groups in schedule order so the save still walks the schedule
    # top-to-bottom, whatever order the DH listed its batches in.
    order = {id(row): i for i, row in enumerate(labels.values())}
    groups.sort(key=lambda g: min(order[id(r)] for r in g))
    return groups, problems


def no_batching_plan(runs: list[list[dict]]) -> list[list[dict]]:
    """Every row on its own — the fallback when planning cannot be trusted.

    Used when the plan call fails outright or its retry still does not
    validate.  Produces exactly today's behaviour (one conversation per
    row), so a broken planner costs money, never correctness.
    """
    return [[row] for run in runs for row in run]
