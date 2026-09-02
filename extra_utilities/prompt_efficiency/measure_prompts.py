"""Prompt-efficiency measurement + integrity harness (standalone).

WHY THIS EXISTS
---------------
``agents/shared/prompts.py`` is the real prompt assembler, but it cannot
be imported in the worktree dev environment: it uses 3.9+ builtin-generic
annotations (``dict[str, str]`` at module scope) and pulls in the langchain
agent stack.  ``extra_utilities/smoke_test_prompt_format.py`` therefore
does not run here either (it imports ``agents.shared.prompts``).

This script is a **faithful, dependency-free replica** of
``_build_template`` — stdlib only, runs under Python 3.8 — so we can
measure and integrity-check the assembled per-agent system prompts while
editing the fragment library, and report the exact token delta of every
change.  It reads the real config fresh (``workflow_settings/settings.py``
booleans + ``database_access.json``) and parses the real
``PROMPT_MD_RUNTIME_SLOTS`` out of ``prompts.py`` via ``ast`` so the two
stay in lock-step without importing anything heavy.

The routing boilerplate emitted by ``agents/shared/routing.py:
routing_instructions`` is transcribed verbatim below (that module also
cannot be imported under 3.8 — it uses ``str | None`` annotations), so
absolute token counts match production.  Round-1 edits do not touch
routing.py; if it changes, re-sync ``_ROUTING_*`` here.

USAGE
-----
    python extra_utilities/prompt_efficiency/measure_prompts.py            # table + integrity + delta vs baseline
    python extra_utilities/prompt_efficiency/measure_prompts.py --matrix   # + fragment-multiplication matrix
    python extra_utilities/prompt_efficiency/measure_prompts.py --set-baseline
    python extra_utilities/prompt_efficiency/measure_prompts.py --dump OUTDIR

Exit code is non-zero if any integrity check fails, so it can gate a PR.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from string import Template

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
AGENTS_DIR = REPO_ROOT / "agents"
GEN_DIR = AGENTS_DIR / "shared" / "prompt_fragments"
DCF_DIR = REPO_ROOT / "DC_prompt_fragments"
DC_CONFIG = DCF_DIR / "dc_config"
TOOLS_CONFIG = DCF_DIR / "tools_config"
SETTINGS_PY = REPO_ROOT / "workflow_settings" / "settings.py"
DBA_JSON = REPO_ROOT / "workflow_settings" / "database_access.json"
PROMPTS_PY = AGENTS_DIR / "shared" / "prompts.py"
BASELINE = SCRIPT_DIR / "baseline_tokens.json"

AGENTS = [
    "receptionist", "orchestrator", "planner", "user_input_inspector",
    "dc_input_creator", "dc_input_inspector", "tool_caller",
    "dc_output_inspector", "database_handler",
]
CHAIN_AGENTS = set(AGENTS) - {"database_handler"}
FORMAT_AGENTS = {  # agents whose TEMPLATE is wired through str.format(...)
    "orchestrator", "planner", "user_input_inspector", "dc_input_creator",
    "dc_input_inspector", "tool_caller", "dc_output_inspector",
}


def _rd(p: Path) -> str:
    return p.read_text(encoding="utf-8").rstrip()


def approx_tokens(s: str) -> int:
    return round(len(s) / 4)


# --------------------------------------------------------------------------
# Config, read fresh (mirrors prompts.py reading settings + database_access)
# --------------------------------------------------------------------------
def _read_setting_bool(name: str, default: bool) -> bool:
    txt = SETTINGS_PY.read_text(encoding="utf-8")
    m = re.search(rf"^{name}\s*:\s*bool\s*=\s*(True|False)", txt, re.MULTILINE)
    return (m.group(1) == "True") if m else default


DCII_ON = _read_setting_bool("DC_INSPECTOR_ENABLED", True)
PF_ON = _read_setting_bool("PLANNER_FIRST", False)
BSV_ON = _read_setting_bool("BLADE_SECTIONS_VISUALIZER_ENABLED", True)
RAG_ON = _read_setting_bool("RAG_ENABLED", True)


def _dba_flags() -> dict:
    try:
        raw = json.loads(DBA_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    return {a: bool(raw.get(a, True)) for a in CHAIN_AGENTS}


DBA = _dba_flags()


def dba_on(agent: str) -> bool:
    return RAG_ON and DBA.get(agent, False)


# --------------------------------------------------------------------------
# Conditional-region filters (replica of prompts.py apply_* functions)
# --------------------------------------------------------------------------
def _rx(pat: str):
    return re.compile(pat, re.DOTALL)


_ONLY = {k: _rx(rf"<<{t}_ONLY>>(.*?)<</{t}_ONLY>>") for k, t in [("dcii", "DCII")]}
_R = {
    "dcii_only": _rx(r"<<DCII_ONLY>>(.*?)<</DCII_ONLY>>"),
    "dcii_off": _rx(r"<<DCII_OFF>>(.*?)<</DCII_OFF>>"),
    "pf_on": _rx(r"<<PF_ON>>(.*?)<</PF_ON>>"),
    "pf_off": _rx(r"<<PF_OFF>>(.*?)<</PF_OFF>>"),
    "bsv_on": _rx(r"<<BSV_ON>>(.*?)<</BSV_ON>>"),
    "bsv_off": _rx(r"<<BSV_OFF>>(.*?)<</BSV_OFF>>"),
    "has_dba": _rx(r"<<HAS_DBA>>(.*?)<</HAS_DBA>>"),
    "chain_only": _rx(r"<<CHAIN_ONLY>>(.*?)<</CHAIN_ONLY>>"),
}
_KEEP = lambda m: m.group(1)
_USER_FACING = frozenset({"receptionist", "orchestrator"})


def apply_flags(t: str) -> str:
    if DCII_ON:
        t = _R["dcii_off"].sub("", t); t = _R["dcii_only"].sub(_KEEP, t)
    else:
        t = _R["dcii_only"].sub("", t); t = _R["dcii_off"].sub(_KEEP, t)
    if PF_ON:
        t = _R["pf_off"].sub("", t); t = _R["pf_on"].sub(_KEEP, t)
    else:
        t = _R["pf_on"].sub("", t); t = _R["pf_off"].sub(_KEEP, t)
    if BSV_ON:
        t = _R["bsv_off"].sub("", t); t = _R["bsv_on"].sub(_KEEP, t)
    else:
        t = _R["bsv_on"].sub("", t); t = _R["bsv_off"].sub(_KEEP, t)
    return t


def apply_dba(t: str, has: bool) -> str:
    return _R["has_dba"].sub(_KEEP if has else "", t)


def apply_chain_only(t: str, agent: str) -> str:
    """Strip <<CHAIN_ONLY>> for user-facing agents; unwrap for the rest."""
    if agent in _USER_FACING:
        return _R["chain_only"].sub("", t)
    return _R["chain_only"].sub(_KEEP, t)


# --------------------------------------------------------------------------
# Slot map (replica of prompts._build_slots)
# --------------------------------------------------------------------------
def build_slots() -> dict:
    dc = lambda r: _rd(DCF_DIR / r)
    gn = lambda r: _rd(GEN_DIR / r)
    pf_flow = "pipeline_flow_planner_first.md" if PF_ON else "pipeline_flow_uii_first.md"
    return {
        "dc_name": dc("dc_config/name.txt").strip(),
        "domain_description": dc("dc_config/domain_description.txt").strip(),
        "parameter_count": dc("dc_config/parameter_count.txt").strip(),
        "dc_structure": dc("dc_config/structure.md"),
        "parameter_list": dc("dc_config/parameters.md"),
        "modelling_notes": dc("dc_config/modelling_notes.md"),
        "qualitative_examples": dc("dc_config/qualitative_examples.md"),
        "visual_inspection_guide": dc("dc_config/visual_inspection_guide.md"),
        "capabilities_can": dc("dc_config/capabilities_can.md"),
        "capabilities_cannot": dc("dc_config/capabilities_cannot.md"),
        "output_file_locations": dc("dc_config/output_file_locations.md"),
        "geometry_modification_rule": dc("dc_config/geometry_modification_rule.md"),
        "invalid_parameter_examples": dc("dc_config/invalid_parameter_examples.md"),
        "hard_constraints_dc": dc("dc_config/hard_constraints_dc.md"),
        "sketch_handling": dc("dc_config/user_input_types/sketch_handling.md"),
        "sketch_notes": dc("dc_config/user_input_types/sketch_notes.md"),
        "tool_inventory": dc("tools_config/tool_inventory.md"),
        "tool_caller_instructions": dc("tools_config/tool_caller_instructions.md"),
        "tool_caller_capabilities": dc("tools_config/tool_caller_capabilities.md"),
        "agent_tools_overview": dc("tools_config/agent_tools_overview.md"),
        "agent_tools_overview_brief": dc("tools_config/agent_tools_overview_brief.md"),
        "hard_constraints_tools": dc("tools_config/hard_constraints_tools.md"),
        "visualize_3d_model_tool": dc("tools_config/visualize_3d_model.md"),
        "propose_attempt_tool": dc("tools_config/propose_attempt.md"),
        "database_search_tool": dc("tools_config/database_search.md"),
        "retrieve_user_inputs_tool": dc("tools_config/retrieve_user_inputs.md"),
        "retrieve_attempt_tool": dc("tools_config/retrieve_attempt.md"),
        "blade_sections_visualizer": dc("tools_config/blade_sections_visualizer.md"),
        "blade_sections_visualizer_off": dc("tools_config/blade_sections_visualizer_off.md"),
        "hard_constraints_generic": gn("generic_constraints.md"),
        "routing_receptionist": gn("routing_receptionist.md"),
        "routing_orchestrator": gn("routing_orchestrator.md"),
        "pipeline_flow": gn(pf_flow),
        "available_agents": gn("available_agents.md"),
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-large",
        "embedding_vector_dims": "3072",
        "embedding_max_response_tokens": "8000",
    }


# --------------------------------------------------------------------------
# Routing block (verbatim transcription of routing.py:routing_instructions)
# --------------------------------------------------------------------------
def _natural_pipeline() -> str:
    head = ("Orchestrator → Planner → User Input Inspector → " if PF_ON
            else "Orchestrator → User Input Inspector → Planner → ")
    middle = ("DC Input Creator → DC Input Inspector → " if DCII_ON
              else "DC Input Creator → ")
    return head + middle + "Tool Caller → DC Output Inspector → Orchestrator"


_ROUTING_DECIDE = [
    "### How to decide where to route",
    "- If the Orchestrator's instruction in your incoming message told "
    "you to *continue the pipeline* (explicitly or by default, since "
    "no instruction to report back means continue), and your own "
    "work succeeded, route FORWARD to the next agent.",
    "- If the Orchestrator's instruction told you to *report back* or "
    "to *do X and return*, route to the Orchestrator once your work "
    "is done.",
    "- If you cannot do your job because the upstream message is "
    "ambiguous, missing data, or contains an error that the previous "
    "agent can fix, route to the previous agent with a clear "
    "clarification request (CLARIFY).",
    "- If something is fundamentally wrong and no agent in the chain "
    "can fix it, route to the Orchestrator (ESCALATE).",
    "",
]
_ROUTING_TAIL = [
    "",
    "### Do not loop — ESCALATE when stuck",
    "If you find yourself about to call the same tool with the same "
    "arguments you already called earlier in this turn, STOP.  Calling "
    "the same read tool twice on unchanged input, or re-thinking the "
    "same decision in a loop, will not give you new information.  "
    "Instead, ESCALATE to the Orchestrator with a short note describing "
    "what is ambiguous or missing and what you would need to proceed.  "
    "The Orchestrator can then re-dispatch you with new instructions, "
    "consult another agent, or ask the user.  Never silently loop.",
    "",
    "### Permission / authorisation issues → Orchestrator (not "
    "the previous agent)",
    "If a rule in your system prompt blocks an action unless some "
    "authorisation is present, READ THE INCOMING HAND-OFF (and any "
    "upstream file the hand-off points to, e.g. extracted_inputs.txt) "
    "ONCE MORE before escalating.  If the hand-off already names an "
    "authorisation that plausibly covers the action — even if the "
    "wording differs from a template you expected — act on it.  Do "
    "NOT bounce back to the previous agent in the chain for a ritual "
    "re-confirmation of something the hand-off already carries; that "
    "is a wasted round-trip.",
    "",
    "When an authorisation is truly missing or ambiguous, ESCALATE "
    "to the Orchestrator.  The previous agent in the chain typically "
    "CANNOT grant permission — authorisations come from the user "
    "(relayed by the Receptionist → Orchestrator), from the Planner "
    "(relayed by the Orchestrator), or from the Orchestrator itself.  "
    "CLARIFY back to the previous agent is appropriate for data / "
    "wording / format issues the previous agent can actually fix, "
    "NOT for permission questions.",
    "",
    "### Routing is a tool call — MANDATORY",
    "Every response that ends your turn MUST invoke exactly one of "
    "the routing tools listed above.  The tool's ``message`` argument "
    "IS the complete hand-off text the recipient will see — there "
    "is NO separate audit block to emit.  Do NOT write a "
    "``---ROUTING---`` / ``---MESSAGE---`` / ``---END---`` template; "
    "that format has been retired.  The tool call is the routing "
    "decision; its ``message`` argument is the hand-off.",
    "",
    "Write the ``message`` argument as free-form prose: no fixed "
    "template, no enumerated option menus, no placeholder phrasings.  "
    "Include everything the recipient genuinely needs (paths the "
    "recipient's tools require, context about what changed and why, "
    "authorship of any non-user-authored values) and nothing they do "
    "not.  Your verbose work product stays in your own history and "
    "(where applicable) on disk — do not duplicate it inside the "
    "``message`` argument.",
    "",
    "Do NOT describe or announce which tool you intend to call.  Do "
    "NOT wait for the next turn to invoke it.  Do NOT substitute the "
    "tool call with free-form prose that says \"routing to X\".  In "
    "the same response where you finish your work, invoke the tool.  "
    "Any ordinary response text you produce is for your own brief "
    "reasoning only — it is NOT delivered to the recipient; only the "
    "tool's ``message`` argument is.  Keep that reasoning terse "
    "(one or two lines is plenty).",
]


def _routing_fragment(name: str) -> str:
    return apply_flags(_rd(GEN_DIR / name))


def routing_block(agent_name, next_agent, prev_agent, fragment_name):
    lines = [
        "## Routing", "",
        "You are one agent in a decentralised pipeline.  The natural "
        "flow is:",
        f"  {_natural_pipeline()}", "",
        f"Your position: **{agent_name}**.",
    ]
    lines.append(f"- Your natural next in line is: **{next_agent}**." if next_agent
                 else "- You are the last agent in the natural flow; completing "
                      "normally means handing control back to the Orchestrator.")
    lines.append(f"- Your natural previous in line is: **{prev_agent}**." if prev_agent
                 else "- You are the first agent in the natural flow; if you need "
                      "to go 'back', that means handing control to the Orchestrator.")
    lines += [""]
    lines += _ROUTING_DECIDE
    lines.append(_routing_fragment(fragment_name))
    lines += _ROUTING_TAIL
    return "\n".join(lines)


def routing_for(agent: str):
    """Return the wired routing block for a chain routing agent, matching
    each agent module's routing_instructions(...) call (grepped from
    agents/<agent>/<agent>.py)."""
    dcii_next_for_dcic = "DC Input Inspector" if DCII_ON else "Tool Caller"
    tc_prev = "DC Input Inspector" if DCII_ON else "DC Input Creator"
    if agent == "planner":
        if PF_ON:
            return routing_block("Planner", "User Input Inspector", None,
                                 "routing_planner_planner_first.md")
        return routing_block("Planner", "DC Input Creator", "User Input Inspector",
                             "routing_planner_uii_first.md")
    if agent == "user_input_inspector":
        if PF_ON:
            return routing_block("User Input Inspector", "DC Input Creator", "Planner",
                                 "routing_user_input_inspector_planner_first.md")
        return routing_block("User Input Inspector", "Planner", None,
                             "routing_user_input_inspector_uii_first.md")
    if agent == "dc_input_creator":
        frag = ("routing_dc_input_creator_planner_first.md" if PF_ON
                else "routing_dc_input_creator_uii_first.md")
        prev = "User Input Inspector" if PF_ON else "Planner"
        return routing_block("DC Input Creator", dcii_next_for_dcic, prev, frag)
    if agent == "dc_input_inspector":
        return routing_block("DC Input Inspector", "Tool Caller", "DC Input Creator",
                             "routing_dc_input_inspector.md")
    if agent == "tool_caller":
        return routing_block("Tool Caller", "DC Output Inspector", tc_prev,
                             "routing_tool_caller.md")
    if agent == "dc_output_inspector":
        return routing_block("DC Output Inspector", None, "Tool Caller",
                             "routing_dc_output_inspector.md")
    return None


# --------------------------------------------------------------------------
# Template assembly (replica of prompts._build_template)
# --------------------------------------------------------------------------
def _per_agent_overlay(agent: str, prefix: str) -> str:
    f = TOOLS_CONFIG / f"{prefix}_{agent}.md"
    return _rd(f) if f.exists() else ""


# Mirrors agents/shared/prompts.py SCOPED_FRAGMENTS.  Kept as a transcription
# rather than an import for the same reason the rest of this module is one:
# measure_prompts deliberately does not import the app (no langchain).  If the
# real table gains a slot, add it here too or the measured token counts will
# silently ignore that agent's scoped copy and every before/after delta that
# touches it will be wrong.
_SCOPED_ROOTS = {"generic": GEN_DIR, "dc": DCF_DIR}
_SCOPED_FRAGMENTS = {
    "hard_constraints_generic": ("generic", "generic_constraints.md"),
    "available_agents":         ("generic", "available_agents.md"),
    "hard_constraints_dc":      ("dc", "dc_config/hard_constraints_dc.md"),
    "hard_constraints_tools":   ("dc", "tools_config/hard_constraints_tools.md"),
    "sketch_handling":          ("dc", "dc_config/user_input_types/sketch_handling.md"),
    "sketch_notes":             ("dc", "dc_config/user_input_types/sketch_notes.md"),
    "parameter_list":           ("dc", "dc_config/parameters.md"),
}


def _scoped(agent: str) -> dict:
    """Slot -> text for every shared fragment *agent* has its own copy of."""
    out = {}
    for slot, (root, rel) in _SCOPED_FRAGMENTS.items():
        p = Path(rel)
        f = _SCOPED_ROOTS[root] / (
            p.parent / f"{p.stem}_{agent}{p.suffix}"
        ).as_posix()
        if f.exists():
            out[slot] = _rd(f)
    return out


def build_template_only(agent: str) -> str:
    """Post $-substitution + flag/DBa filters, runtime {slots} still present."""
    raw = _rd(AGENTS_DIR / agent / "prompt.md")
    slots = dict(build_slots())
    slots["database_search_per_agent"] = _per_agent_overlay(agent, "database_search")
    slots["blade_sections_visualizer_per_agent"] = _per_agent_overlay(
        agent, "blade_sections_visualizer")
    # LAST, so a per-agent scoped copy wins over the shared fragment.
    slots.update(_scoped(agent))
    once = Template(raw).safe_substitute(slots)
    twice = Template(once).safe_substitute(slots)
    filtered = apply_flags(twice)
    filtered = apply_dba(filtered, dba_on(agent) if agent in CHAIN_AGENTS else False)
    return apply_chain_only(filtered, agent)


# Runtime {slots} other than routing_instructions get blanked for token
# accounting (their real content — chain_access_block, render library
# block, image/comparison blocks, path strings — is small and constant
# across edits, so it does not affect deltas).
_BLANK_RUNTIME = [
    "chain_access_block", "render_check_library_block", "image_persistence_block",
    "comparison_mode_block", "user_inputs_dir", "input_images_subdir",
    "extraction_output_file",
]


def build_filled(agent: str) -> str:
    t = build_template_only(agent)
    rb = routing_for(agent)
    if rb is not None:
        t = t.replace("{routing_instructions}", rb)
    for k in _BLANK_RUNTIME:
        t = t.replace("{" + k + "}", "")
    return t


# --------------------------------------------------------------------------
# Integrity checks
# --------------------------------------------------------------------------
class _Stub(dict):
    def __missing__(self, k):
        return f"<stub:{k}>"


def _parse_runtime_slots() -> dict:
    """Extract PROMPT_MD_RUNTIME_SLOTS from prompts.py via ast (no import)."""
    tree = ast.parse(PROMPTS_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        target = None
        value = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target.id, node.value
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    target = t.id
            value = node.value
        if target != "PROMPT_MD_RUNTIME_SLOTS" or not isinstance(value, ast.Dict):
            continue
        out = {}
        for k, v in zip(value.keys, value.values):
            agent = k.value if isinstance(k, ast.Constant) else None
            members = set()
            if isinstance(v, ast.Call) and v.args:
                arg = v.args[0]
                if isinstance(arg, (ast.Set, ast.List, ast.Tuple)):
                    members = {e.value for e in arg.elts if isinstance(e, ast.Constant)}
            if agent is not None:
                out[agent] = members
        return out
    return {}


_DOUBLED = re.compile(r"\{\{|\}\}")
_SINGLE_BRACE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_DOLLAR = re.compile(r"\$([a-zA-Z_][a-zA-Z0-9_]*)")


def integrity(known_slots: set, runtime_slots: dict):
    """Return (fails, doc_mentions).

    ``fails`` are real crash-class regressions ([] == all good):
      * brace/format errors (unescaped literal ``{``/``}`` in a
        ``.format()``-wired agent) — mirrors smoke_test_prompt_format;
      * a ``{runtime}`` slot referenced by an agent but absent from its
        ``PROMPT_MD_RUNTIME_SLOTS`` allow-list (would KeyError at wiring).

    ``doc_mentions`` are known ``$slot`` names that appear as LITERAL prose
    in the assembled output (e.g. the "NOTE for fragment editors" block in
    database_search.md, or sketch_notes.md's slot-doc preamble).  The real
    2-pass assembler ships these verbatim too, so they are NOT substitution
    bugs — they are editor cruft reaching the model and are surfaced as a
    (non-failing) cleanup signal.
    """
    fails = []
    doc_mentions = set()
    for agent in AGENTS:
        tmpl = build_template_only(agent)
        for name in set(_DOLLAR.findall(tmpl)):
            if name in known_slots:
                doc_mentions.add(name)
        if agent in FORMAT_AGENTS:
            try:
                build_filled(agent)  # fills routing; leftover {} exercised below
                tmpl.format_map(_Stub())
            except (IndexError, ValueError, KeyError) as exc:
                fails.append(f"{agent}: brace/format error: "
                             f"{type(exc).__name__}: {exc}")
            allowed = runtime_slots.get(agent, set())
            stripped = _DOUBLED.sub("", tmpl)
            for name in set(_SINGLE_BRACE.findall(stripped)):
                if name not in allowed:
                    fails.append(f"{agent}: runtime slot {{{name}}} not in "
                                 f"PROMPT_MD_RUNTIME_SLOTS[{agent}]")
    return fails, sorted(doc_mentions)


# --------------------------------------------------------------------------
# Fragment-multiplication matrix (top-level $slot references, DBa/flag-aware)
# --------------------------------------------------------------------------
def matrix(slots: dict) -> list:
    sizes = {k: len(v) for k, v in slots.items()}
    usage = {}
    for agent in AGENTS:
        raw = _rd(AGENTS_DIR / agent / "prompt.md")
        # Pre-filter so DBa-stripped / flag-stripped $slots aren't counted.
        pre = apply_dba(apply_flags(raw),
                        dba_on(agent) if agent in CHAIN_AGENTS else False)
        for name in set(_DOLLAR.findall(pre)):
            if name in sizes:
                usage.setdefault(name, []).append(agent)
    rows = [(sizes[s] * len(a), s, sizes[s], len(a)) for s, a in usage.items()]
    rows.sort(reverse=True)
    return rows


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--matrix", action="store_true", help="print fragment matrix")
    ap.add_argument("--set-baseline", action="store_true", help="write baseline_tokens.json")
    ap.add_argument("--dump", metavar="OUTDIR", help="write assembled prompts to OUTDIR")
    args = ap.parse_args()

    try:  # Windows consoles default to cp1252; assembled prompts contain → etc.
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    slots = build_slots()
    known = set(slots) | {"database_search_per_agent", "blade_sections_visualizer_per_agent"}
    runtime_slots = _parse_runtime_slots()

    print(f"config: PLANNER_FIRST={PF_ON} DCII={DCII_ON} BSV={BSV_ON} RAG={RAG_ON}")
    print(f"DBa-on agents: {sorted(a for a in CHAIN_AGENTS if dba_on(a))}\n")

    tokens = {a: approx_tokens(build_filled(a)) for a in AGENTS}
    base = {}
    if BASELINE.exists() and not args.set_baseline:
        try:
            base = json.loads(BASELINE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            base = {}

    print(f"{'agent':22} {'chars':>8} {'tokens':>8} {'delta':>8}")
    total = 0
    for a in AGENTS:
        chars = len(build_filled(a))
        tok = tokens[a]
        total += tok
        delta = ""
        if a in base:
            d = tok - base[a]
            delta = "0" if d == 0 else f"{d:+d}"
        print(f"{a:22} {chars:8d} {tok:8d} {delta:>8}")
    base_total = sum(base.values()) if base else 0
    dtot = "" if not base else ("0" if total - base_total == 0 else f"{total - base_total:+d}")
    print(f"{'FLEET TOTAL':22} {'':>8} {total:8d} {dtot:>8}")

    fails, doc_mentions = integrity(known, runtime_slots)
    print()
    if fails:
        print(f"INTEGRITY: {len(fails)} FAILURE(S)")
        for f in fails:
            print(f"  FAIL {f}")
    else:
        print(f"INTEGRITY: {len(AGENTS)}/{len(AGENTS)} assemble · "
              f"0 brace errors · 0 unknown runtime slots  OK")
    if doc_mentions:
        print("INFO: literal $slot doc-mentions shipping to the model "
              "(editor cruft, cleanup candidates): "
              + ", ".join("$" + d for d in doc_mentions))

    if args.matrix:
        print("\n=== fragment multiplication (top-level $slot refs, DBa/flag-aware) ===")
        print(f"{'slot':32} {'size':>6} {'xAgents':>7} {'total':>9}")
        for tot, slot, sz, n in matrix(slots):
            print(f"{slot:32} {sz:6d} {n:7d} {tot:9d}")

    if args.dump:
        out = Path(args.dump)
        out.mkdir(parents=True, exist_ok=True)
        for a in AGENTS:
            (out / f"{a}.txt").write_text(build_filled(a), encoding="utf-8")
        print(f"\nwrote {len(AGENTS)} assembled prompts to {out}")

    if args.set_baseline:
        BASELINE.write_text(json.dumps(tokens, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
        print(f"\nbaseline written: {BASELINE}")

    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
