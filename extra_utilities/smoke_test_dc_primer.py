# -*- coding: utf-8 -*-
"""DC-parameter primer — the invoke-time image+text reference.

What is worth pinning:

 1. ASSETS.  Both files exist; the PNG is the owner-approved 930x309
    downscale (~383 image tokens), not the 1094x364 generator output that
    someone regenerates and drops in without the resize step.
 2. LOCKSTEP.  The text block's high-point bullet quotes the canonical
    sentence from dc_config/parameters.md VERBATIM (whitespace-normalised).
    Two near-identical definitions of the same parameter drifting apart is
    the exact failure the 2026-08-21 *MaxPos correction fixed.
 3. MESSAGE SHAPE.  dc_primer_messages() returns one HumanMessage, text
    block first, provider-correct image block second; for Anthropic with
    caching on, a trailing TEXT block carries the cache_control marker
    (never the image block — langchain_anthropic only guarantees the field
    survives on text blocks); for OpenAI no marker and no trailing block.
 4. GATING.  The flag off => [], read fresh per call (a Workflow-Settings
    edit must not need a restart).
 5. INJECTION.  All six agent files splice dc_primer_messages BETWEEN the
    system message and self.messages — never appended to self.messages,
    where the image stripper / Context Pruner / session snapshot would eat
    it.
 6. ACCOUNTING.  primer_tokens_for() is >0 exactly for the six primer
    agents while the flag is on, 0 otherwise, and base_chain_agent's
    pruner arithmetic consumes it.

Offline: stubs langchain_core the same way smoke_test_topology_fragments
does; no network, no real models.
"""
import base64
import io
import re
import struct
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

# --- stubs: agents/* imports without langchain ----------------------------
for _name, _rel in (("agents", "agents"), ("agents.shared", "agents/shared"),
                    ("agents.database_handler", "agents/database_handler")):
    _m = types.ModuleType(_name)
    _m.__path__ = [str(ROOT / _rel)]
    sys.modules[_name] = _m

_lc = types.ModuleType("langchain_core")
_lc.__path__ = []
_lcm = types.ModuleType("langchain_core.messages")


class _Msg:
    def __init__(self, content=None, **kw):
        self.content = content
        for k, v in kw.items():
            setattr(self, k, v)


class HumanMessage(_Msg):
    pass


class SystemMessage(_Msg):
    pass


class AIMessage(_Msg):
    pass


class ToolMessage(_Msg):
    pass


class BaseMessage(_Msg):
    pass


for _n in ("HumanMessage", "SystemMessage", "AIMessage", "ToolMessage",
           "BaseMessage"):
    setattr(_lcm, _n, globals()[_n])
_lct = types.ModuleType("langchain_core.tools")


class _S:
    @staticmethod
    def from_function(*a, **k):
        return None


_lct.StructuredTool = _S
_lct.tool = lambda *a, **k: (lambda f: f)
_lcr = types.ModuleType("langchain_core.rate_limiters")


class InMemoryRateLimiter:  # imported at module level by llm_provider
    def __init__(self, *a, **k):
        pass


_lcr.InMemoryRateLimiter = InMemoryRateLimiter
sys.modules["langchain_core"] = _lc
sys.modules["langchain_core.messages"] = _lcm
sys.modules["langchain_core.tools"] = _lct
sys.modules["langchain_core.rate_limiters"] = _lcr

# dotenv + PIL, for llm_provider -> image_compression (worktree has neither;
# the primer path never touches PIL — it parses the PNG header itself).
_dotenv = types.ModuleType("dotenv")
_dotenv.dotenv_values = lambda *a, **k: {}
sys.modules.setdefault("dotenv", _dotenv)
try:
    import PIL  # noqa: F401
except ImportError:
    _pil = types.ModuleType("PIL")
    _pil.Image = types.ModuleType("PIL.Image")
    _pil.Image.LANCZOS = 1  # image_compression reads it at import time
    _pil.ImageOps = types.ModuleType("PIL.ImageOps")
    sys.modules["PIL"] = _pil
    sys.modules["PIL.Image"] = _pil.Image
    sys.modules["PIL.ImageOps"] = _pil.ImageOps

from workflow_settings import settings as st            # noqa: E402
from agents.shared import dc_primer                     # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool, detail: object = "") -> None:
    print(("  PASS  " if cond else "  FAIL  ") + name
          + ("" if cond else "\n          -> " + str(detail)[:300]))
    if not cond:
        FAILS.append(name)


def norm(s: str) -> str:
    return " ".join(s.split())


# --- 1. assets --------------------------------------------------------------
print("case 1 - assets")
check("text block exists", dc_primer.TEXT_PATH.is_file())
check("image exists", dc_primer.IMAGE_PATH.is_file())
w, h = dc_primer._png_size(dc_primer.IMAGE_PATH)
check("PNG is the approved 930x309 downscale (found %dx%d)" % (w, h),
      (w, h) == (930, 309))
tok = (w * h + 749) // 750
check("image ~383 anthropic tokens (found %d)" % tok, 380 <= tok <= 390)

# --- 2. lockstep with parameters.md -----------------------------------------
print("case 2 - the high-point sentence is VERBATIM from parameters.md")
params = (ROOT / "DC_prompt_fragments" / "dc_config" / "parameters.md"
          ).read_text(encoding="utf-8")
# Round 4 (9d164d2) SPLIT the old one-liner: the ``*MaxPos`` half kept its own
# paragraph ending "at zero camber.", and the thickness half became a longer
# paragraph of its own.  This check tracked the pre-split wording and has been
# failing silently since; it now checks each half where it actually lives.
m = re.search(r"``innerMaxPos``[^#]*?at zero camber\.", params)
check("parameters.md still carries the canonical *MaxPos sentence", m is not None)
if m:
    canonical = norm(m.group(0))
    body = norm(dc_primer.TEXT_PATH.read_text(encoding="utf-8"))
    check("text block quotes it verbatim (whitespace-normalised)",
          canonical in body, canonical)
# The primer paraphrases the thickness paragraph rather than quoting it, so
# check the load-bearing FACT rather than the wording — it is the sentence the
# DCII misread as a constraint in run ID254.
for what, src in (("parameters.md", params),
                  ("primer text",
                   dc_primer.TEXT_PATH.read_text(encoding="utf-8"))):
    check("%s states max thickness is fixed at ~30%% of chord" % what,
          "fixed at ~30% of chord" in norm(src))

# --- 2b. the hub is NOT the inner blade section -----------------------------
print("case 2b - hub 8 mm vs inner section 4 mm, kept distinct")
# The first version of this drawing labelled r = 4 mm "the hub".  They are
# two different things: the hub cylinder is ~8 mm (constants.js CONSTANTS.hub)
# and 4 mm is the inner blade section's station (innerRadiusFixed), which
# sits inside it and is the origin middlePos measures from.
body = norm(dc_primer.TEXT_PATH.read_text(encoding="utf-8"))
check("text names the hub as 8 mm", "radius 8 mm" in body, body[:160])
check("text puts the inner section at 4 mm",
      # body is whitespace-normalised, so the file's column alignment
      # ("inner section  = ...") collapses to one space here
      "inner section = blade root, at r = 4 mm" in body)
check("text says the inner section is NOT the hub radius",
      "NOT the hub radius" in body)
check("text no longer calls r = 4 mm 'the hub'",
      "0 = hub" not in body and "fixed at the hub" not in body, body[:200])
check("middlePos formula still measured from 4",
      "radius = 4 + middlePos x (impellerRadius - 4) mm" in body)

# The generator's ROOT_MM is load-bearing: it must equal the geometry's
# innerRadiusFixed, or the drawing teaches a span origin the code does not use.
gen = (ROOT / "extra_utilities" / "dc_params_primer"
       / "make_dc_params_primer.py").read_text(encoding="utf-8")
consts = (ROOT / "web" / "feg" / "constants.js").read_text(encoding="utf-8")
m_root = re.search(r"^ROOT_MM = ([\d.]+)", gen, re.M)
m_hub = re.search(r"^HUB_MM = ([\d.]+)", gen, re.M)
m_code = re.search(r"innerRadiusFixed:\s*([\d.]+)", consts)
check("generator defines ROOT_MM and HUB_MM",
      m_root is not None and m_hub is not None)
if m_root and m_code:
    check("ROOT_MM (%s) == constants.js innerRadiusFixed (%s)"
          % (m_root.group(1), m_code.group(1)),
          float(m_root.group(1)) == float(m_code.group(1)))
if m_root and m_hub:
    check("HUB_MM (%s) is larger than ROOT_MM (%s)"
          % (m_hub.group(1), m_root.group(1)),
          float(m_hub.group(1)) > float(m_root.group(1)))

# --- 3 + 4. message shape and gating ----------------------------------------
print("case 3 - message shape per provider")
st.DC_PARAMS_PRIMER_ENABLED = True
dc_primer._MESSAGE_CACHE.clear()

for provider, img_type in (("anthropic", "image"), ("openai", "image_url")):
    msgs = dc_primer.dc_primer_messages(provider)
    check("%s: exactly one message" % provider, len(msgs) == 1, msgs)
    if len(msgs) != 1:
        continue
    c = msgs[0].content
    check("%s: text block FIRST" % provider,
          isinstance(c, list) and c[0].get("type") == "text")
    check("%s: image block second, type %r" % (provider, img_type),
          len(c) >= 2 and c[1].get("type") == img_type, c[1].get("type"))
    if provider == "anthropic":
        # scope defaults to caching ON in settings; marker on a TEXT block
        from agents.shared.llm_provider import system_cache_control
        cc = system_cache_control("anthropic")
        if cc is None:
            check("anthropic: caching off in settings -> 2 blocks, no marker",
                  len(c) == 2)
        else:
            check("anthropic: trailing TEXT block carries cache_control",
                  len(c) == 3 and c[2].get("type") == "text"
                  and c[2].get("cache_control") == cc, c[-1])
            check("anthropic: the IMAGE block itself carries NO marker",
                  "cache_control" not in c[1])
        raw = base64.b64decode(c[1]["source"]["data"][:32])
        check("anthropic: payload is the PNG itself (uncompressed path)",
              raw[:8] == b"\x89PNG\r\n\x1a\n")
        ww, hh = struct.unpack(">II",
                               base64.b64decode(c[1]["source"]["data"])[16:24])
        check("anthropic: payload dims match the file (no compress_for_model)",
              (ww, hh) == (w, h), (ww, hh))
    else:
        check("openai: exactly 2 blocks (no cache marker ever)", len(c) == 2)
        check("openai: data-URI payload",
              c[1]["image_url"]["url"].startswith("data:image/png;base64,"))

print("case 4 - gating")
st.DC_PARAMS_PRIMER_ENABLED = False
check("flag off -> []", dc_primer.dc_primer_messages("anthropic") == [])
check("flag off -> tokens 0",
      dc_primer.primer_tokens_for("dc_input_creator") == 0)
st.DC_PARAMS_PRIMER_ENABLED = True
check("flag back on WITHOUT restart -> message returns",
      len(dc_primer.dc_primer_messages("anthropic")) == 1)

# --- 5. injection sites ------------------------------------------------------
print("case 5 - all six agents splice it between system and history")
SIX = ("user_input_inspector", "dc_input_creator", "dc_input_inspector",
       "dc_output_inspector", "creator", "designer")
PATTERN = ("[make_system_message(self.system_prompt, self.provider)] "
           "+ dc_primer_messages(self.provider, self.AGENT_KEY) "
           "+ self.messages,")
for a in SIX:
    src = norm((ROOT / "agents" / a / (a + ".py")).read_text(encoding="utf-8"))
    check("%s: splice present, system-first order" % a, PATTERN in src)
    check("%s: never appended to self.messages" % a,
          "self.messages.append(dc_primer" not in src
          and "messages += dc_primer" not in src)

# --- 6. token accounting ------------------------------------------------------
print("case 6 - pruner accounting")
dc_primer._TOKEN_ESTIMATE.clear()
got = {a: dc_primer.primer_tokens_for(a) for a in SIX}
check("all six primer agents count >0", all(v > 0 for v in got.values()), got)
check("UII gets the parameter-free variant, and it is shorter",
      got["user_input_inspector"] < got["dc_input_creator"], got)
n = got["user_input_inspector"]
check("estimate is ~1k (image %d + text; found %d)" % (tok, n),
      tok + 300 <= n <= tok + 900, n)
for a in ("planner", "orchestrator", "receptionist", "tool_caller",
          "database_handler"):
    check("%s counts 0" % a, dc_primer.primer_tokens_for(a) == 0)
src = norm((ROOT / "agents" / "shared" / "base_chain_agent.py"
            ).read_text(encoding="utf-8"))
check("base_chain_agent consumes primer_tokens_for",
      "primer_tokens_for(self.AGENT_KEY)" in src)

print()
if FAILS:
    print("FAIL - %d assertion(s): %s" % (len(FAILS), FAILS))
    sys.exit(1)
print("PASS - the primer's assets, lockstep wording, per-provider shape, "
      "gating, six injection sites and pruner accounting all hold.")
