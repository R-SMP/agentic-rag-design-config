"""The primer — one picture and its text, injected at invoke time.

The primer explains how the configurator's parameters couple with the
design (for the propeller: top view, section grid, camber / high-point /
angle semantics).  The setup says what it is and who gets it
(``engine/primer.py``: ``primer`` in ``dc_pack/pack.yaml``, edited on the
Studio's Primer page): a picture in ``assets/``, the text field
``$dc_params_primer_text``, and per topology the agents that receive it --
by default the DC-side agents, UII, DCIC, DCII, DCOI, and the 3-agent
Design Engineer and Requirements Analyst that merge them.  Every agent's
call site splices it, as ONE ``HumanMessage`` between the system message
and the live history:

    invoke_with_retry(
        self.llm,
        [make_system_message(self.system_prompt, self.provider)]
        + primed_history(self.provider, self.AGENT_KEY, self.messages),
        ...)

and it is empty for an agent the setup does not name.

Use ``primed_history``, not ``dc_primer_messages``, at a call site.  The
Context Pruner replaces ``self.messages`` with one or two
``SystemMessage``s AT THE HEAD, and Anthropic rejects system messages
that are not consecutive: splicing the primer straight after the system
prompt puts a ``HumanMessage`` between them and the call dies with
"Received multiple non-consecutive system messages".  ``primed_history``
inserts the primer AFTER any leading system messages instead, which is
exactly the shape every non-primer agent already sends.

WHY A MESSAGE, AND WHY NOT IN ``self.messages``.  Anthropic's ``system``
field takes text blocks only and OpenAI allows image parts only in ``user``
messages, so an image reference cannot live in the system prompt.  And it
must NOT be appended to ``self.messages``, which fails three separate ways:
``strip_image_blocks_from_messages`` deletes image blocks after every turn
(``KEEP_IMAGES_IN_CONTEXT`` defaults False), the Context Pruner summarises
the history prefix away, and ``AgentState.messages`` would persist it into
the session snapshot.  Injected per-invoke, it is immune to all three — and
because the prefix ``[system, primer]`` is byte-identical every turn, it
caches as well as the system prompt does.

CACHING.  For Anthropic (when prompt caching is on) the primer carries an
explicit ``cache_control`` breakpoint so the cached prefix extends through
the image instead of stopping at the system block.  The marker rides on a
tiny trailing TEXT block rather than on the image block itself:
``langchain_anthropic`` is only known to preserve ``cache_control`` on text
blocks (``_format_text_block`` keeps it in its allow-list — the same
guarantee ``make_system_message`` relies on), and a marker that silently
vanished would re-bill ~1k tokens per turn with no error.  A primer without
a picture carries the marker on its text block.  OpenAI caches prefixes
automatically, so no marker is emitted and the trailing block is omitted
entirely.

COMPRESSION.  The image is read directly from disk and base64-encoded here —
deliberately NOT through ``encode_image``/``compress_for_model``.  The
propeller's PNG is already the owner-approved 85 % downscale (930x309, ~383
image tokens); a second, sidecar-driven downscale would blur the 9 pt
labels.  See ``extra_utilities/dc_params_primer/README.md``.

The assembled message is kept per provider, cache marker, text file and
picture while their files are unchanged; the setup's ``primer`` section and the
``DC_PARAMS_PRIMER_ENABLED`` flag are read fresh per call, so an edit
takes effect on the next invoke without a restart — same contract as every
other flag.
"""

from __future__ import annotations

import base64
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from agents.shared.llm_provider import make_image_block, system_cache_control
from agents.shared.topology import topology as _topology
from engine import pack as _pack
from engine import primer as _primer

# Agents that get a DIFFERENT primer text own a copy of the pack's
# ``dc_params_primer_text`` (``dc_params_primer_text@<agent>...md``).  The
# IMAGE is always the same.
#
# The UII records what the user said in the user's own words and never maps
# anything onto a configurator parameter, so the default text — which names
# every parameter, gives the middlePos formula and its 0.3-0.7 band — would
# hand it back the vocabulary its parameter-access cell (``none`` by default,
# engine/parameter_access.py) keeps from it.
# Its variant keeps the geometry (hub vs 4 mm root, span-fraction, mid-wall
# diameter, section orientation) and drops the names, formulas and ranges.
# Note the diagram itself still carries labels; this narrows the leak, it does
# not close it.
#
# 3-agent: the Requirements Analyst absorbs the UII, so it has the UII's
# variant text.  The Design Engineer has none: of its two parents only the DC
# Input Creator receives the primer, and it takes the default text.


def _text_path(agent_key: "str | None") -> "Path | None":
    """The primer text this agent gets — its own copy, or the default.

    Resolved through the pack for the ACTIVE topology, so a topology can own
    its own primer text exactly as it owns its own prompt fragments.  That
    matters more here than anywhere else in the prompt layer: the primer is
    injected at INVOKE time, not spliced into the system prompt, so it
    bypasses every prompt-level filter.
    """
    return _pack.fragment_path(_primer.TEXT_SLOT, _topology(), agent_key)


def _receives(agent_key: "str | None") -> bool:
    """Whether the setup gives *agent_key* the primer in the active topology."""
    return bool(agent_key) and _primer.gets(agent_key, _topology())


def _stamp(path: "Path | None") -> "tuple | None":
    if path is None:
        return None
    try:
        st = path.stat()
    except OSError:
        return None
    return (str(path), st.st_size, st.st_mtime_ns)


# Filled lazily; keys are (provider, its cache marker, the text file's
# stamp, the picture's stamp), values the single HumanMessage.  The text
# file is part of the key because agents with a variant text must not share
# the default's cached message; the stamps, because the Studio may change
# either file; the marker, because Workflow Settings may switch caching.
# Safe to share one instance across agents and turns: nothing downstream
# mutates message content (the strippers operate on ``self.messages`` only,
# which never contains this object).
_MESSAGE_CACHE: dict[tuple, HumanMessage] = {}
# Keyed by the same stamps, for the same reason as _MESSAGE_CACHE.
_TOKEN_ESTIMATE: dict[tuple, int] = {}


def _enabled() -> bool:
    from workflow_settings import settings as _ws
    return bool(getattr(_ws, "DC_PARAMS_PRIMER_ENABLED", True))


def _read_text(text_path: "Path | None") -> str:
    if text_path is None:
        return ""
    try:
        return text_path.read_text(encoding="utf-8").rstrip()
    except OSError:
        return ""


def _build(provider: str, text: str, image: "Path | None") -> "HumanMessage | None":
    content: list[dict] = []
    if text:
        content.append({"type": "text", "text": text})
    if image is not None:
        b64 = base64.b64encode(image.read_bytes()).decode()
        content.append(make_image_block(b64, provider, media_type="image/png"))
    if not content:
        return None
    cc = system_cache_control(provider)
    if cc is not None:
        # Anthropic with caching on: extend the cached prefix through the
        # image.  The marker must sit on a text block (see module docstring).
        if image is not None:
            content.append({
                "type": "text",
                "text": "END OF REFERENCE DIAGRAM.",
                "cache_control": cc,
            })
        else:
            content[-1] = {**content[-1], "cache_control": cc}
    return HumanMessage(content=content)


def dc_primer_messages(provider: str,
                       agent_key: "str | None" = None) -> "list[HumanMessage]":
    """The primer as a (possibly empty) message list, ready to splice.

    Returns ``[]`` when ``DC_PARAMS_PRIMER_ENABLED`` is off, when the setup
    does not give *agent_key* the primer in the active topology, or when it
    has neither a picture nor a text -- a missing file degrades to "no
    picture" (or "no text"), never to a broken invoke.  Splice the result
    directly after the system message.
    """
    if not _enabled() or not _receives(agent_key):
        return []
    text_path = _text_path(agent_key)
    image = _primer.image_path()
    prov = (provider or "").strip().lower()
    key = (prov, repr(system_cache_control(prov)), _stamp(text_path), _stamp(image))
    msg = _MESSAGE_CACHE.get(key)
    if msg is None:
        try:
            msg = _build(prov, _read_text(text_path), image)
        except OSError:
            return []
        if msg is None:
            return []
        _MESSAGE_CACHE[key] = msg
    return [msg]


def primer_tokens_for(agent_key: str) -> int:
    """Tokens the primer adds OUTSIDE ``self.messages`` for this agent.

    Consumed by ``base_chain_agent.prune_history_if_needed``, whose estimate
    otherwise reads only the history plus the system prompt: without this
    the primer's ~1k tokens would sit invisibly outside the threshold
    arithmetic.  0 for agents that never receive the primer, when the flag
    is off, or when the assets are absent.

    The image term uses Anthropic's tokens = width x height / 750; OpenAI
    bills tiles differently, but the pruner's whole count is an estimate and
    this is the conservative figure.
    """
    if not _enabled() or not _receives(agent_key):
        return 0
    text_path = _text_path(agent_key)
    image = _primer.image_path()
    key = (_stamp(text_path), _stamp(image))
    cached = _TOKEN_ESTIMATE.get(key)
    if cached is None:
        cached = 0
        if image is not None:
            try:
                cached += _primer.image_tokens(*_primer.png_size(image))
            except (OSError, ValueError):
                pass
        text = _read_text(text_path)
        if text:
            try:
                from agents.database_handler.token_utils import count_tokens
                cached += count_tokens(text)
            except Exception:  # tokeniser unavailable — cheap fallback
                cached += len(text) // 4
        _TOKEN_ESTIMATE[key] = cached
    return cached


def primed_history(provider: str, agent_key: "str | None",
                   messages: list) -> list:
    """*messages* with the primer spliced in after any leading system ones.

    A call site composes ``[system_prompt] + primed_history(...)``.  Before
    the Context Pruner has ever fired, ``messages`` starts with a
    ``HumanMessage``, the scan stops at 0, and the result is byte-identical
    to the old ``primer + messages`` -- so OpenAI runs and every unpruned
    turn are completely unaffected.

    After a prune, ``messages`` begins with the Pruner's summary
    ``SystemMessage``(s).  Putting the primer after them keeps every system
    message consecutive, which is what Anthropic requires and what every
    non-primer agent already sends.

    Only LEADING system messages are skipped.  That covers every shape the
    Pruner produces (tier 1 ``[coarse] + tail``, tier 2 ``[coarse, fine]``,
    tier 3 ``[super]``, all at the head).  A system message buried deeper is
    left where it is: nothing puts one there, and hoisting it would silently
    reorder the conversation.
    """
    primer = dc_primer_messages(provider, agent_key)
    if not primer:
        return list(messages)
    i = 0
    while i < len(messages) and isinstance(messages[i], SystemMessage):
        i += 1
    return list(messages[:i]) + primer + list(messages[i:])
