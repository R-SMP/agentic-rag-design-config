"""Standing-directives propagation (Component C).

A general mechanism so a verbose, free-form instruction the Planner issues
survives the whole agent chain intact.  The directive travels as a delimited
TEXT block inside the normal inter-agent hand-off messages (NOT a structured
flag), and a dispatcher-level backstop re-stamps it onto any hand-off that
dropped it.  This module holds only the pure text helpers; the wiring lives in
``orchestrator.dispatch`` (capture + re-stamp) and the agent prompts (the
"copy verbatim" rule for every chain agent + the Planner's "how to issue" rule).

Design decisions this implements (see extra_utilities/design_precision_sections_match.md §C):
  * Only the Planner registers directives; every other agent copies the block
    forward verbatim.
  * The Orchestrator/dispatcher backstop re-stamps ONLY on detected loss (it
    does not blindly duplicate an intact block).
  * Loss = the canonical directive text is no longer carried (verbatim, modulo
    whitespace) — this catches a full drop AND a paraphrase.

Pure stdlib — importable + unit-testable without the full app env.
"""

from __future__ import annotations

BLOCK_START = "=== STANDING DIRECTIVES (copy verbatim to the next agent) ==="
BLOCK_END = "=== END STANDING DIRECTIVES ==="


def format_block(text: str) -> str:
    """Wrap directive ``text`` in the reserved delimited block."""
    return f"{BLOCK_START}\n{(text or '').strip()}\n{BLOCK_END}"


def extract_directive(message: str) -> "str | None":
    """Return the directive text inside the block in ``message``, or ``None``
    when there is no block.  The LAST block wins: the Planner is the sole
    issuer, so its most recent block is the authoritative current directive —
    a change that leaves an older copy above the new one must not shadow it.
    Tolerant of a missing END delimiter (takes the rest of the message) so a
    slightly-mangled block still yields its text."""
    if not message or BLOCK_START not in message:
        return None
    after = message.rsplit(BLOCK_START, 1)[1]
    body = after.split(BLOCK_END, 1)[0] if BLOCK_END in after else after
    body = body.strip()
    return body or None


def _norm(s: str) -> str:
    """Collapse every run of whitespace so verbatim detection is not defeated
    by an agent reflowing the block."""
    return " ".join((s or "").split())


def is_present(message: str, directive: str) -> bool:
    """Loss-detection: is ``directive`` still carried in ``message`` (verbatim,
    modulo whitespace)?  An empty/absent directive is trivially 'present' so
    the backstop is a no-op when nothing is active."""
    if not directive:
        return True
    return _norm(directive) in _norm(message)


def ensure_present(message: str, directive: str) -> str:
    """Return ``message`` unchanged when ``directive`` is empty or already
    carried; otherwise re-stamp the block onto the end (the loss backstop)."""
    if is_present(message, directive):
        return message
    return f"{message}\n\n{format_block(directive)}"
