"""DC-parameter primer — a fixed image + text reference injected at invoke time.

The primer explains how the DC parameters couple with the design (top view,
section grid, camber / high-point / angle semantics).  It is delivered to the
DC-side agents — UII, DCIC, DCII, DCOI, and their 5/3-agent counterparts
Creator and Designer — as ONE ``HumanMessage`` spliced between the system
message and the live history:

    invoke_with_retry(
        self.llm,
        [make_system_message(self.system_prompt, self.provider)]
        + primed_history(self.provider, self.AGENT_KEY, self.messages),
        ...)

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
vanished would re-bill ~1k tokens per turn with no error.  OpenAI caches
prefixes automatically, so no marker is emitted and the trailing block is
omitted entirely.

COMPRESSION.  The image is read directly from disk and base64-encoded here —
deliberately NOT through ``encode_image``/``compress_for_model``.  The PNG in
the repo is already the owner-approved 85 % downscale (930x309, ~383 image
tokens); a second, sidecar-driven downscale would blur the 9 pt labels.  See
``extra_utilities/dc_params_primer/README.md``.

The assembled message is cached per provider for the process lifetime (the
assets are fixed); the ``DC_PARAMS_PRIMER_ENABLED`` flag is read fresh per
call, so a Workflow-Settings edit takes effect on the next invoke without a
restart — same contract as every other flag.
"""

from __future__ import annotations

import base64
import struct
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from agents.shared.llm_provider import make_image_block, system_cache_control

_DC_CONFIG_DIR = (
    Path(__file__).resolve().parent.parent.parent / "DC_prompt_fragments" / "dc_config"
)
TEXT_PATH = _DC_CONFIG_DIR / "dc_params_primer_text.txt"
IMAGE_PATH = _DC_CONFIG_DIR / "images" / "dc_params_primer.png"

# Agents that get a DIFFERENT primer text.  The IMAGE is always the same.
#
# The UII records what the user said in the user's own words and never maps
# anything onto a configurator parameter, so the default text — which names
# every parameter, gives the middlePos formula and its 0.3-0.7 band — would
# hand it back the vocabulary ``UII_PARAMETER_LIST_ENABLED`` exists to remove.
# Its variant keeps the geometry (hub vs 4 mm root, span-fraction, mid-wall
# diameter, section orientation) and drops the names, formulas and ranges.
# Note the diagram itself still carries labels; this narrows the leak, it does
# not close it.
_TEXT_NAME_BY_AGENT = {
    "user_input_inspector": "dc_params_primer_text_user_input_inspector.txt",
}

_TEXT_NAME_DEFAULT = "dc_params_primer_text.txt"


def _text_path(agent_key: "str | None") -> Path:
    """The primer text this agent gets — its variant, or the default.

    Resolved through ``prompts._topology_override`` so a topology can own
    its own primer text, exactly as it owns its own prompt fragments.

    This matters more here than anywhere else in the prompt layer: the
    primer is injected at INVOKE time, not spliced into the system prompt,
    so it bypasses every prompt-level filter.  Before this, a
    ``agents/<N>agent/dc_config/dc_params_primer_text*_<N>agents.txt``
    could sit on disk and be silently inert -- the paths were built
    absolute from ``_DC_CONFIG_DIR`` and never consulted the resolver.

    Imported lazily, the way ``routing._load_routing_fragment`` does it:
    ``prompts`` pulls in this module's neighbours at its own import time,
    so a module-level import here would be circular.  Topology 7 has no
    ``agents/7agent/``, so the override always misses there and the shared
    file is read exactly as before.
    """
    from agents.shared.prompts import _topology_override

    name = _TEXT_NAME_BY_AGENT.get(agent_key or "", _TEXT_NAME_DEFAULT)
    return _topology_override(f"dc_config/{name}") or (_DC_CONFIG_DIR / name)

# The agents that receive the primer.  The injection sites are explicit in
# each agent file; this set exists for the OTHER consumer — the Context
# Pruner's token accounting (``primer_tokens_for``), which must know whether
# an agent's real context carries the primer's ~1k tokens outside
# ``self.messages``.
PRIMER_AGENT_KEYS = frozenset({
    "user_input_inspector",
    "dc_input_creator",
    "dc_input_inspector",
    "dc_output_inspector",
    "designer",      # 3-agent: absorbs the Creator
})

# Filled lazily; keys are (provider, text-file name), values the single
# HumanMessage.  The text file is part of the key because agents with a
# variant text must not share the default's cached message.
# Safe to share one instance across agents and turns: nothing downstream
# mutates message content (the strippers operate on ``self.messages`` only,
# which never contains this object).
_MESSAGE_CACHE: dict[tuple, HumanMessage] = {}
# Keyed by text-file name, for the same reason as _MESSAGE_CACHE.
_TOKEN_ESTIMATE: dict[str, int] = {}


def _enabled() -> bool:
    from workflow_settings import settings as _ws
    return bool(getattr(_ws, "DC_PARAMS_PRIMER_ENABLED", True))


def _png_size(path: Path) -> "tuple[int, int]":
    """(width, height) from the PNG IHDR — no imaging library needed."""
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError(f"{path} is not a PNG")
    w, h = struct.unpack(">II", head[16:24])
    return int(w), int(h)


def _build(provider: str, text_path: Path) -> HumanMessage:
    text = text_path.read_text(encoding="utf-8").rstrip()
    b64 = base64.b64encode(IMAGE_PATH.read_bytes()).decode()
    content: list[dict] = [
        {"type": "text", "text": text},
        make_image_block(b64, provider, media_type="image/png"),
    ]
    cc = system_cache_control(provider)
    if cc is not None:
        # Anthropic with caching on: extend the cached prefix through the
        # image.  The marker must sit on a text block (see module docstring).
        content.append({
            "type": "text",
            "text": "END OF REFERENCE DIAGRAM.",
            "cache_control": cc,
        })
    return HumanMessage(content=content)


def dc_primer_messages(provider: str,
                       agent_key: "str | None" = None) -> "list[HumanMessage]":
    """The primer as a (possibly empty) message list, ready to splice.

    Returns ``[]`` when ``DC_PARAMS_PRIMER_ENABLED`` is off or either asset
    is missing — a missing file degrades to "no primer", never to a broken
    invoke.  Splice the result directly after the system message.
    """
    if not _enabled():
        return []
    text_path = _text_path(agent_key)
    key = ((provider or "").strip().lower(), text_path.name)
    msg = _MESSAGE_CACHE.get(key)
    if msg is None:
        try:
            msg = _build(key[0], text_path)
        except (OSError, ValueError):
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
    if agent_key not in PRIMER_AGENT_KEYS or not _enabled():
        return 0
    text_path = _text_path(agent_key)
    cached = _TOKEN_ESTIMATE.get(text_path.name)
    if cached is None:
        try:
            w, h = _png_size(IMAGE_PATH)
            image_tok = (w * h + 749) // 750
            try:
                from agents.database_handler.token_utils import count_tokens
                text_tok = count_tokens(text_path.read_text(encoding="utf-8"))
            except Exception:  # tokeniser unavailable — cheap fallback
                text_tok = len(text_path.read_text(encoding="utf-8")) // 4
            cached = image_tok + text_tok
        except OSError:
            return 0
        _TOKEN_ESTIMATE[text_path.name] = cached
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
