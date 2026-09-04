"""Which fragment FILES feed each agent's prompt, per topology.

Resolution is done by the loader itself: the two fragment readers are
patched to return a sentinel naming the file they resolved to, so the
answer honours topology overrides, variant overrides and per-agent scoped
copies without re-implementing any of those rules here.

Usage
-----
    py -3.13 provenance.py                 # topology 7 -> provenance.json
    py -3.13 provenance.py --topology 5    # topology 5 -> provenance5.json

Run ``dump.py`` for the SAME topology first: the agent roster is read
from that dump rather than hard-coded here, so the two stages cannot
disagree about which agents a topology builds.
"""
import io
import json
import re
import sys

import bootstrap

REPO = bootstrap.install()

TOPOLOGY = 7
if "--topology" in sys.argv:
    TOPOLOGY = int(sys.argv[sys.argv.index("--topology") + 1])
SUFFIX = "" if TOPOLOGY == 7 else str(TOPOLOGY)

import workflow_settings.settings as S
S.SYSTEM_TOPOLOGY = TOPOLOGY
S.RAG_ENABLED = True          # widest set of slots

from agents.shared import prompts as P

_DUMP = REPO / "extra_utilities" / "prompt_pdf" / ("dump%s.json" % SUFFIX)
if not _DUMP.is_file():
    raise SystemExit(
        "%s not found - run  py -3.13 dump.py%s  first."
        % (_DUMP.name, (" --topology %d" % TOPOLOGY) if SUFFIX else "")
    )
with io.open(_DUMP, encoding="utf-8") as _f:
    AGENTS = list(json.load(_f)["agents"])

_real_dc = P._read_dc_fragment
_real_generic = P._read_generic_fragment


def rel(p):
    return str(p).replace(str(REPO), "").lstrip("\\/").replace("\\", "/")


def _resolved_dc(rel_path):
    p = P._topology_override(rel_path) or (P.DC_FRAGMENTS_DIR / rel_path)
    return p


def _resolved_generic(rel_path):
    p = (P._topology_override("prompt_fragments/" + rel_path)
         or P.GENERIC_FRAGMENTS_DIR / rel_path)
    return p


# slot -> resolved file, by running the real slot builder with sentinel readers
P._read_dc_fragment = lambda rp: "@@" + rel(_resolved_dc(rp)) + "@@"
P._read_generic_fragment = lambda rp: "@@" + rel(_resolved_generic(rp)) + "@@"
SLOT_FILE = {}
for slot, val in P._build_slots().items():
    m = re.fullmatch(r"@@(.*)@@", str(val))
    SLOT_FILE[slot] = m.group(1) if m else None
P._read_dc_fragment = _real_dc
P._read_generic_fragment = _real_generic

# slot -> real text, for the nested-slot pass
SLOT_TEXT = P._build_slots()

SLOT_RE = re.compile(r"\$([a-z_][a-z0-9_]*)")

out = {}
for agent in AGENTS:
    prompt_path = P._prompt_path(agent)
    raw = prompt_path.read_text(encoding="utf-8")

    # per-agent overlays + scoped copies, resolved exactly as _build_template does
    files = {}
    scoped = {}
    for slot in P.SCOPED_FRAGMENTS:
        sp = P.scoped_fragment_path(slot, agent)
        if sp is not None:
            scoped[slot] = rel(sp)

    dbs_rel = "tools_config/database_search_%s.md" % agent
    dbs = P._topology_override(dbs_rel) or (P.TOOLS_CONFIG_DIR /
                                            ("database_search_%s.md" % agent))
    bsv_rel = "tools_config/blade_sections_visualizer_%s.md" % agent
    bsv = P._topology_override(bsv_rel) or (P.TOOLS_CONFIG_DIR /
                                            ("blade_sections_visualizer_%s.md" % agent))
    overlay = {}
    if dbs.exists():
        overlay["database_search_per_agent"] = rel(dbs)
    if bsv.exists():
        overlay["blade_sections_visualizer_per_agent"] = rel(bsv)

    def file_for(slot):
        if slot in scoped:
            return scoped[slot]
        if slot in overlay:
            return overlay[slot]
        return SLOT_FILE.get(slot)

    def text_for(slot):
        if slot in scoped:
            return (REPO / scoped[slot]).read_text(encoding="utf-8")
        if slot in overlay:
            return (REPO / overlay[slot]).read_text(encoding="utf-8")
        return SLOT_TEXT.get(slot, "")

    direct = [s for s in dict.fromkeys(SLOT_RE.findall(raw))
              if s in SLOT_TEXT or s in scoped or s in overlay
              or s in ("database_search_per_agent",
                       "blade_sections_visualizer_per_agent")]
    nested = []
    for s in direct:
        for n in SLOT_RE.findall(text_for(s)):
            if n not in direct and n not in nested and n in SLOT_TEXT:
                nested.append(n)

    rows = []
    for s in direct:
        f = file_for(s)
        rows.append({"slot": s, "file": f, "nested": False,
                     "scoped": s in scoped})
    for s in nested:
        rows.append({"slot": s, "file": file_for(s), "nested": True,
                     "scoped": False})

    out[agent] = {
        "prompt_file": rel(prompt_path),
        "fragments": rows,
    }

_OUT = REPO / "extra_utilities" / "prompt_pdf" / ("provenance%s.json" % SUFFIX)
with io.open(_OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print("wrote %s  (topology %d, %d agents)" % (_OUT.name, TOPOLOGY, len(AGENTS)))
for a in AGENTS:
    r = out[a]
    print("%-22s %s" % (a, r["prompt_file"]))
    for row in r["fragments"]:
        mark = "  (nested)" if row["nested"] else ""
        mark += "  [scoped]" if row["scoped"] else ""
        print("      $%-38s %s%s" % (row["slot"], row["file"], mark))
