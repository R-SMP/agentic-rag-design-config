"""DC-parameter primer — a fixed image + text reference injected at invoke time.

The primer explains how the DC parameters couple with the design (top view,
section grid, camber / high-point / angle semantics).  It is delivered to the
DC-side agents — UII, DCIC, DCII, DCOI, and their 5/3-agent counterparts
Creator and Designer — as ONE ``HumanMessage`` spliced between the system
message and the live history:

    invoke_with_retry(
        self.llm,
        [make_system_message(self.system_prompt, self.provider)]
        + dc_primer_messages(self.provider)
        + self.messages,
        ...)

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

from langchain_core.messages import HumanMessage

from agents.shared.llm_provider import make_image_block, system_cache_control

_DC_CONFIG_DIR = (
    Path(__file__).resolve().parent.parent.parent / "DC_prompt_fragments" / "dc_config"
)
TEXT_PATH = _DC_CONFIG_DIR / "dc_params_primer_text.txt"
IMAGE_PATH = _DC_CONFIG_DIR / "images" / "dc_params_primer.png"

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
    "creator",       # 5-agent: absorbs DCIC + DCII
    "designer",      # 3-agent: absorbs the Creator
})

# Filled lazily; keys are provider names, values the single HumanMessage.
# Safe to share one instance across agents and turns: nothing downstream
# mutates message content (the strippers operate on ``self.messages`` only,
# which never contains this object).
_MESSAGE_CACHE: dict[str, HumanMessage] = {}
_TOKEN_ESTIMATE: "int | None" = None


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


def _build(provider: str) -> HumanMessage:
    text = TEXT_PATH.read_text(encoding="utf-8").rstrip()
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


def dc_primer_messages(provider: str) -> "list[HumanMessage]":
    """The primer as a (possibly empty) message list, ready to splice.

    Returns ``[]`` when ``DC_PARAMS_PRIMER_ENABLED`` is off or either asset
    is missing — a missing file degrades to "no primer", never to a broken
    invoke.  Splice the result directly after the system message.
    """
    if not _enabled():
        return []
    key = (provider or "").strip().lower()
    msg = _MESSAGE_CACHE.get(key)
    if msg is None:
        try:
            msg = _build(key)
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
    global _TOKEN_ESTIMATE
    if agent_key not in PRIMER_AGENT_KEYS or not _enabled():
        return 0
    if _TOKEN_ESTIMATE is None:
        try:
            w, h = _png_size(IMAGE_PATH)
            image_tok = (w * h + 749) // 750
            try:
                from agents.database_handler.token_utils import count_tokens
                text_tok = count_tokens(TEXT_PATH.read_text(encoding="utf-8"))
            except Exception:  # tokeniser unavailable — cheap fallback
                text_tok = len(TEXT_PATH.read_text(encoding="utf-8")) // 4
            _TOKEN_ESTIMATE = image_tok + text_tok
        except OSError:
            return 0
    return _TOKEN_ESTIMATE
