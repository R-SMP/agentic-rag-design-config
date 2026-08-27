"""Render dump.json + provenance.json into a print-ready HTML document."""
import difflib
import html
import io
import json
import re
from pathlib import Path

from markdown_it import MarkdownIt

HERE = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[2]   # <repo>/extra_utilities/prompt_pdf/x.py

D = json.load(open(HERE / "dump.json", encoding="utf-8"))
PROV = json.load(open(HERE / "provenance.json", encoding="utf-8"))
CFG = D["config"]
GRID = D["dba_grid"]

def _git(*args):
    import subprocess
    try:
        return subprocess.run(["git", "-C", str(REPO), *args],
                              capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return "unknown"


COMMIT = _git("rev-parse", "--short", "HEAD")
COMMIT_DATE = _git("log", "-1", "--format=%cd", "--date=short")

AGENTS = ["receptionist", "orchestrator", "planner", "user_input_inspector",
          "dc_input_creator", "dc_input_inspector", "tool_caller",
          "dc_output_inspector", "database_handler"]

DISPLAY = {
    "receptionist": "Receptionist",
    "orchestrator": "Orchestrator",
    "planner": "Planner",
    "user_input_inspector": "User Input Inspector",
    "dc_input_creator": "DC Input Creator",
    "dc_input_inspector": "DC Input Inspector",
    "tool_caller": "Tool Caller",
    "dc_output_inspector": "DC Output Inspector",
    "database_handler": "Database Handler",
}

ROLE = {
    "receptionist": "Interface \u2014 fields the user's questions, forwards design requests, delivers the final answer. Not a link in the design chain.",
    "orchestrator": "Route \u2014 the dispatch hub. Every hand-off returns here; it relays and decides the next hop.",
    "planner": "Plan \u2014 chooses the strategy, issues the standing directive, and is the final approver before anything reaches the user.",
    "user_input_inspector": "Perceive \u2014 reads the user's text and images and writes the structured extraction. Vision.",
    "dc_input_creator": "Create \u2014 translates intent into the concrete numeric parameter set. Deliberately image-blind.",
    "dc_input_inspector": "Validate \u2014 independent audit of the created parameters before anything is rendered.",
    "tool_caller": "Execute \u2014 calls the geometry/render tool and passes the render paths on. The most mechanical agent.",
    "dc_output_inspector": "Critique \u2014 compares the render against the intent/sketch and drives the refine loop. Vision.",
    "database_handler": "Post-session \u2014 runs after the user saves; never part of the dispatch loop and never speaks to the user.",
}

# Agents whose bound tool set includes retrieve_attempt while their prompt
# never mentions it (verified: 0 occurrences of "retrieve_attempt" in each).
UNDOCUMENTED_TOOL = {
    "dc_input_creator": "retrieve_attempt",
    "dc_input_inspector": "retrieve_attempt",
    "dc_output_inspector": "retrieve_attempt",
}

# The prompts are CommonMark, and python-markdown is not CommonMark: it will
# not let a bullet interrupt a paragraph, so a sibling list item written
# directly under the previous item's closing paragraph -- the Planner's
# "Your common moves" is the worst case -- was absorbed into that item and
# rendered as prose with a literal "*".  It also needs a blank line before a
# list that follows a bold lead-in ("**CAN do:**" + a spliced fragment).
# Neither is a defect in the prompts: the model reads the raw markdown and
# sees ordinary lists, and a strict CommonMark parser reads them the same way.
# So the renderer moves to markdown-it-py, which is CommonMark by construction.
# 372 list items became 461 -- and, unlike the blank-line normaliser this
# replaces, the text handed to the renderer is the assembled prompt verbatim,
# so the PDF stays byte-faithful to what the agent is actually given.
#
# html=False makes "<param X>" render as text instead of vanishing as a tag,
# in code spans too, which is what the old private-use-sentinel dance was for.
# Tables are enabled although no prompt currently uses one, so a future table
# in a prompt or a tool description does not silently render as prose.
_MD = MarkdownIt("commonmark", {"html": False}).enable("table")


def md(text):
    """Markdown -> HTML, CommonMark semantics, "<" treated as literal text."""
    return _MD.render(text)


def md_inline(text):
    """Same, flattened for a table cell: paragraphs become line breaks."""
    h = md(text).strip()
    h = re.sub(r"</p>\s*<p>", "<br>", h)
    h = re.sub(r"^\s*<p>", "", h)
    h = re.sub(r"</p>\s*$", "", h)
    return h


def esc(s):
    return html.escape(str(s), quote=False)


def approx_tokens(s):
    return round(len(s) / 4)


def fmt_int(n):
    return "{:,}".format(n).replace(",", "\u2009")


# ---------------------------------------------------------------------------
# Prompt body: render markdown chunk-by-chunk so RAG-only runs can be tinted.
# Every RAG insertion in this variant is exactly one complete "##" section
# bounded by blank lines, so chunk boundaries never split a markdown block.
# ---------------------------------------------------------------------------
def prompt_html(rec):
    off = rec["rag_off"]["prompt"].splitlines()
    on = rec["rag_on"]["prompt"].splitlines()
    ops = difflib.SequenceMatcher(None, off, on, autojunk=False).get_opcodes()
    parts = []
    for tag, i1, i2, j1, j2 in ops:
        chunk = "\n".join(on[j1:j2])
        if not chunk.strip():
            continue
        if tag == "equal":
            parts.append(md(chunk))
        else:
            parts.append(
                '<div class="rag"><div class="rag-tag">added by RAG</div>'
                + md(chunk) + "</div>"
            )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Tool cards
# ---------------------------------------------------------------------------
def type_of(spec):
    if "type" in spec:
        t = spec["type"]
        if t == "array":
            items = spec.get("items") or {}
            inner = items.get("type")
            return "array of " + inner if inner else "array"
        return t
    if "anyOf" in spec:
        return " | ".join(
            (s.get("type") or "null") for s in spec["anyOf"]
        )
    if "$ref" in spec or "allOf" in spec:
        return "object"
    return "any"


def tool_card(t, rag_only, undocumented):
    tags = []
    if rag_only:
        tags.append('<span class="tag tag-rag">RAG only</span>')
    if undocumented:
        tags.append('<span class="tag tag-warn">not described in this '
                    'agent&#39;s prompt</span>')
    args = t.get("args") or {}
    required = set(t.get("required") or [])
    if args:
        rows = []
        for name, spec in args.items():
            desc = spec.get("description", "")
            default = spec.get("default", "\u2014")
            if default is None:
                default = "null"
            elif isinstance(default, bool):
                default = "true" if default else "false"
            elif default != "\u2014":
                default = json.dumps(default, ensure_ascii=False)
            rows.append(
                "<tr><td class=\"m\">{}</td><td class=\"m\">{}</td>"
                "<td class=\"m\">{}</td><td>{}</td><td>{}</td></tr>".format(
                    esc(name), esc(type_of(spec)),
                    "yes" if name in required else "no",
                    esc(default),
                    md_inline(desc) if desc
                    else "<span class=\"dim\">\u2014</span>",
                )
            )
        argtable = (
            '<table class="args"><thead><tr><th>argument</th><th>type</th>'
            '<th>required</th><th>default</th><th>description</th></tr>'
            '</thead><tbody>' + "".join(rows) + "</tbody></table>"
        )
    else:
        argtable = '<p class="dim">No arguments.</p>'
    cls = "tool-card" + (" tool-rag" if rag_only else "")
    return (
        '<div class="{}"><div class="tool-head"><code>{}</code>{}</div>'
        '<div class="tool-desc">{}</div>{}</div>'
    ).format(cls, esc(t["name"]), "".join(tags), md(t["description"]), argtable)


def tools_html(agent, rec):
    off_names = {t["name"] for t in rec["rag_off"]["tools"]}
    tools = rec["rag_on"]["tools"]
    cards = []
    for t in tools:
        rag_only = t["name"] not in off_names
        undoc = UNDOCUMENTED_TOOL.get(agent) == t["name"]
        cards.append(tool_card(t, rag_only, undoc))
    return "\n".join(cards)


# ---------------------------------------------------------------------------
# Front matter
# ---------------------------------------------------------------------------
CFG_ROWS = [
    ("SYSTEM_TOPOLOGY", CFG["SYSTEM_TOPOLOGY"], "seven design-workflow agents"),
    ("database-access profile", '"' + CFG["dba_profile"] + '"',
     "which DB tools each agent gets when RAG is on"),
    ("RAG_ENABLED", CFG["RAG_ENABLED_default"],
     "the committed default \u2014 the highlighted text is what turning this "
     "on would add"),
    ("DC_INSPECTOR_ENABLED", CFG["DC_INSPECTOR_ENABLED"],
     "DC Input Inspector is in the chain"),
    ("PLANNER_FIRST", CFG["PLANNER_FIRST"],
     "UII runs before the Planner"),
    ("MESH_CHECKS", CFG["MESH_CHECKS"],
     "no watertightness / volume metrics; the Tool Caller gets the "
     "\u201cchecks off\u201d render fragment"),
    ("RENDER_LIBRARY", '"' + CFG["RENDER_LIBRARY"] + '"', "render backend"),
    ("GEOMETRY_BACKEND", '"' + CFG["GEOMETRY_BACKEND"] + '"',
     "headless-Node FEG rather than RhinoCompute"),
    ("BLADE_SECTIONS_VISUALIZER_ENABLED", CFG["BLADE_SECTIONS_VISUALIZER_ENABLED"],
     "render_blade_sections bound to the Tool Caller"),
    ("OCR_ENABLED", CFG["OCR_ENABLED"],
     "view_images carries OCR text; ocr_regions exists"),
    ("CHAIN_ACCESS", CFG["CHAIN_ACCESS"],
     "the Orchestrator's chain-access block is the ON variant"),
    ("KEEP_IMAGES_IN_CONTEXT", CFG["KEEP_IMAGES_IN_CONTEXT"],
     "DCOI image-persistence block is the OFF variant"),
    ("DCOI_COMPARISON_MODE", CFG["DCOI_COMPARISON_MODE"],
     "selects the DCOI comparison-mode block"),
]


def config_table():
    rows = "".join(
        '<tr><td class="m">{}</td><td class="m val">{}</td><td>{}</td></tr>'
        .format(esc(k), esc(v), esc(note))
        for k, v, note in CFG_ROWS
    )
    return ('<table class="cfg"><thead><tr><th>setting</th><th>value</th>'
            '<th>effect on these prompts</th></tr></thead><tbody>'
            + rows + "</tbody></table>")


def grid_table():
    head = ('<tr><th>agent</th><th>database_search</th>'
            '<th>retrieve_user_inputs</th><th>retrieve_attempt</th>'
            '<th>prompt changed by RAG?</th></tr>')
    rows = []
    for a in AGENTS:
        g = GRID.get(a)
        rec = D["agents"][a]
        changed = len(rec["rag_on"]["prompt"]) != len(rec["rag_off"]["prompt"])
        if g is None:
            cells = '<td colspan="3" class="dim">not DBa-eligible</td>'
        else:
            cells = "".join(
                '<td class="{}">{}</td>'.format(
                    "yes" if g[k] else "no", "\u25cf" if g[k] else "\u25cb")
                for k in ("search", "user_inputs", "attempt")
            )
        rows.append(
            '<tr><td class="m">{}</td>{}<td>{}</td></tr>'.format(
                esc(a), cells,
                "yes \u2014 one section added" if changed else "no \u2014 identical")
        )
    return ('<table class="grid"><thead>' + head + "</thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def contents():
    items = []
    n = 1
    for a in AGENTS:
        items.append('<li><span class="num">{}</span>'
                     '<a href="#{}">{}</a></li>'.format(n, a, DISPLAY[a]))
        n += 1
    return "<ol class=\"toc\">" + "".join(items) + "</ol>"


def provenance_html():
    out = []
    for a in AGENTS:
        p = PROV[a]
        rows = []
        for row in p["fragments"]:
            f = row["file"]
            if f is None:
                if row["slot"].startswith("embedding_"):
                    f = ('<span class="dim">(a settings value, not a file)'
                         '</span>')
                else:
                    f = ('<span class="dim">(no per-agent overlay \u2014 the '
                         'slot resolves to empty)</span>')
            else:
                f = '<span class="m">' + esc(f) + "</span>"
            notes = []
            if row["scoped"]:
                notes.append("scoped copy")
            if row["nested"]:
                notes.append("nested")
            rows.append(
                '<tr><td class="m">${}</td><td>{}</td><td>{}</td></tr>'.format(
                    esc(row["slot"]), f, esc(", ".join(notes)) or "")
            )
        out.append(
            '<h3 id="prov-{}">{}</h3>'
            '<p class="src">Prompt file: <span class="m">{}</span></p>'
            '<table class="frag"><thead><tr><th>slot</th><th>resolved file</th>'
            '<th>notes</th></tr></thead><tbody>{}</tbody></table>'.format(
                esc(a), esc(DISPLAY[a]), esc(p["prompt_file"]), "".join(rows))
        )
    return "\n".join(out)


ROLE4 = (REPO / "agents" / "orchestrator" /
         "role4_feedback_instructions.md").read_text(encoding="utf-8")

CSS = """
@page { size: A4; margin: 17mm 15mm 16mm 15mm; }
* { box-sizing: border-box; }
body { font-family: "Segoe UI","Helvetica Neue",Arial,sans-serif;
       font-size: 8.7pt; line-height: 1.5; color: #1a1a1a; margin: 0; }
.m, code, pre { font-family: Consolas,"Cascadia Mono",Menlo,monospace; }
code { font-size: 0.93em; background: #f2f3f5; padding: 0.05em 0.28em;
       border-radius: 2px; }
pre { background: #f6f7f9; border: 1px solid #e2e5ea; border-left: 3px solid #c4cad4;
      padding: 6px 9px; overflow-x: auto; font-size: 8.0pt; line-height: 1.4;
      white-space: pre-wrap; word-break: break-word; }
pre code { background: none; padding: 0; }
h1,h2,h3,h4 { break-after: avoid; page-break-after: avoid; }
a { color: #1a1a1a; text-decoration: none; }

/* ---------- cover ---------- */
.cover { height: 247mm; display: flex; flex-direction: column;
         justify-content: center; break-after: page; }
.cover .kicker { font-size: 10pt; letter-spacing: .18em; text-transform: uppercase;
                 color: #6b7280; margin-bottom: 10mm; }
.cover h1 { font-size: 30pt; line-height: 1.12; margin: 0 0 6mm 0;
            font-weight: 650; letter-spacing: -0.01em; }
.cover .sub { font-size: 12pt; color: #374151; max-width: 130mm;
              line-height: 1.5; }
.cover .meta { margin-top: 14mm; font-size: 9pt; color: #6b7280; }
.cover .meta div { margin: 1.5mm 0; }
.rule { height: 3px; background: #111; width: 34mm; margin: 8mm 0; }

/* ---------- generic sections ---------- */
section { break-before: page; page-break-before: always; }
section.first { break-before: auto; page-break-before: auto; }
h2.sec { font-size: 15pt; margin: 0 0 1mm 0; font-weight: 650;
         letter-spacing: -0.01em; }
.sec-kicker { font-size: 7.6pt; letter-spacing: .16em; text-transform: uppercase;
              color: #8a919c; margin-bottom: 1.5mm; }
.lead { color: #374151; max-width: 165mm; }

table { border-collapse: collapse; width: 100%; margin: 4mm 0;
        font-size: 8.1pt; }
th { text-align: left; font-weight: 600; border-bottom: 1.5px solid #333;
     padding: 3px 6px 3px 0; vertical-align: bottom; }
td { border-bottom: 1px solid #e6e8ec; padding: 3px 6px 3px 0;
     vertical-align: top; }
td.val { white-space: nowrap; }
.dim { color: #9aa1ac; }
.grid td.yes { color: #15803d; font-size: 10pt; text-align: center; }
.grid td.no  { color: #c9ced6; font-size: 10pt; text-align: center; }
.grid th:not(:first-child) { text-align: center; }

.note { border-left: 3px solid #b45309; background: #fdf6ec;
        padding: 5px 10px; margin: 4mm 0; }
.note .h { font-weight: 650; color: #92400e; }

/* ---------- agent sections ---------- */
.agent-head { border-bottom: 2px solid #111; padding-bottom: 3mm;
              margin-bottom: 4mm; }
.agent-head h2 { font-size: 19pt; margin: 0; font-weight: 650;
                 letter-spacing: -0.015em; }
.agent-head .role { color: #4b5563; margin: 1.5mm 0 0 0; max-width: 165mm; }
.stats { display: flex; flex-wrap: wrap; gap: 0 9mm; margin-top: 3mm;
         font-size: 7.9pt; color: #4b5563; }
.stats b { color: #111; font-weight: 600; }
.stats .m { font-size: 7.6pt; }
.subhead { font-size: 10.5pt; font-weight: 650; margin: 6mm 0 2mm 0;
           padding-bottom: 1mm; border-bottom: 1px solid #d5d9df; }

/* ---------- prompt body ---------- */
.prompt h1 { font-size: 12.5pt; margin: 5mm 0 2mm; font-weight: 650; }
.prompt h2 { font-size: 10.8pt; margin: 5mm 0 1.5mm; font-weight: 650; }
.prompt h3 { font-size: 9.6pt; margin: 4mm 0 1.5mm; font-weight: 650; }
.prompt h4 { font-size: 9pt; margin: 3.5mm 0 1mm; font-weight: 650; }
.prompt p { margin: 0 0 2.4mm 0; }
.prompt ul, .prompt ol { margin: 0 0 2.4mm 0; padding-left: 5mm; }
.prompt li { margin: 0.6mm 0; }
.prompt table { font-size: 7.7pt; }
.prompt blockquote { margin: 0 0 2.4mm 4mm; color: #4b5563;
                     border-left: 2px solid #d5d9df; padding-left: 3mm; }
.prompt hr { border: none; border-top: 1px solid #dfe3e8; margin: 4mm 0; }

/* ---------- RAG highlight ---------- */
.rag { background: #fff6c2; border-left: 3px solid #e0b300;
       padding: 3mm 4mm 1.5mm 4mm; margin: 3mm 0; position: relative;
       break-inside: auto; }
.rag-tag { font-size: 6.8pt; letter-spacing: .13em; text-transform: uppercase;
           color: #8a6d00; font-weight: 700; margin-bottom: 1.5mm; }
.rag h2:first-of-type { margin-top: 0; }
.rag code { background: #f7ecb8; }
.rag pre { background: #fbf3cf; border-color: #e6d38f; border-left-color: #d9be5c; }

/* ---------- tool cards ---------- */
.tool-card { border: 1px solid #dfe3e8; border-radius: 3px; padding: 3mm 4mm;
             margin: 3mm 0; break-inside: avoid; page-break-inside: avoid; }
.tool-card.tool-rag { background: #fffdf2; border-color: #e5cf7d;
                      border-left: 3px solid #e0b300; }
.tool-head { font-size: 10pt; font-weight: 700; margin-bottom: 1.5mm; }
.tool-head code { background: #eef0f3; font-size: 9.4pt; padding: 0.1em 0.4em; }
.tool-card.tool-rag .tool-head code { background: #f7ecb8; }
.tag { font-size: 6.6pt; letter-spacing: .1em; text-transform: uppercase;
       font-weight: 700; padding: 1px 5px; border-radius: 8px;
       margin-left: 2mm; vertical-align: 1.5px; }
.tag-rag { background: #f5df8f; color: #7a5f00; }
.tag-warn { background: #fde2e2; color: #9b1c1c; }
.tool-desc p { margin: 0 0 2mm 0; }
.tool-desc { margin-bottom: 2mm; }
table.args { font-size: 7.6pt; margin: 2mm 0 0 0; }
table.args td.m { white-space: nowrap; }
table.args td:nth-child(5) { width: 55%; }

/* ---------- toc ---------- */
ol.toc { list-style: none; padding: 0; margin: 4mm 0; font-size: 10pt; }
ol.toc li { padding: 1.8mm 0; border-bottom: 1px dotted #d5d9df; }
ol.toc .num { display: inline-block; width: 9mm; color: #8a919c;
              font-variant-numeric: tabular-nums; }
.src { font-size: 7.9pt; color: #4b5563; margin: 0 0 2mm 0; }
h3 { font-size: 10.5pt; margin: 6mm 0 1mm; }
table.frag { font-size: 7.6pt; }
table.frag td:nth-child(1) { width: 23%; }
table.frag td:nth-child(3) { width: 12%; color: #6b7280; }

/* NOTHING may exceed the printable width.  Chrome's print-to-PDF silently
   shrink-to-fits the WHOLE document when any element overflows, which
   scales every page down and hides the overflow instead of reporting it --
   so a single unbreakable file path in one appendix table was rendering
   all 113 pages at ~85% size.  Long unbreakable runs (file paths, dotted
   identifiers) must therefore be allowed to break anywhere. */
td, th { overflow-wrap: anywhere; }
td.m, th.m, .prompt code, .tool-head code { overflow-wrap: anywhere; }
table.args td.m { white-space: normal; }
"""


def agent_section(a, idx):
    rec = D["agents"][a]
    off_p, on_p = rec["rag_off"]["prompt"], rec["rag_on"]["prompt"]
    off_t, on_t = rec["rag_off"]["tools"], rec["rag_on"]["tools"]
    changed = len(on_p) != len(off_p)
    if changed:
        chars = "{} \u2192 {} chars".format(fmt_int(len(off_p)), fmt_int(len(on_p)))
        toks = "\u2248{} \u2192 \u2248{} tokens".format(
            fmt_int(approx_tokens(off_p)), fmt_int(approx_tokens(on_p)))
    else:
        chars = "{} chars (RAG changes nothing)".format(fmt_int(len(off_p)))
        toks = "\u2248{} tokens".format(fmt_int(approx_tokens(off_p)))
    ntools = ("{} tools".format(len(off_t)) if len(off_t) == len(on_t)
              else "{} tools ({} with RAG)".format(len(off_t), len(on_t)))
    is_dh = a == "database_handler"
    dh_note = (
        '<div class="note"><span class="h">These four are never bound at the '
        'same time.</span> The Database Handler keeps no tools on its LLM: for '
        'each step it binds exactly one of them with <code>tool_choice</code> '
        'forcing that call, reads the arguments, and unbinds. It is listed here '
        'because these are the only tool schemas the model is ever shown.</div>'
        if is_dh else "")
    undoc = UNDOCUMENTED_TOOL.get(a)
    undoc_note = (
        '<div class="note"><span class="h">One tool below is bound but never '
        'described.</span> With RAG on this agent holds <code>{}</code>, yet the '
        'string \u201cretrieve_attempt\u201d does not appear anywhere in its '
        'assembled system prompt. See the consistency note in the front '
        'matter.</div>'.format(esc(undoc)) if undoc else "")
    variant_note = ""
    return """
<section id="{key}" class="agent">
  <div class="agent-head">
    <div class="sec-kicker">Agent {idx} of 9</div>
    <h2>{name}</h2>
    <p class="role">{role}</p>
    <div class="stats">
      <span><b>{chars}</b></span>
      <span>{toks}</span>
      <span><b>{ntools}</b></span>
      <span class="m">{src}</span>
    </div>
  </div>
  {variant_note}
  <div class="subhead">System prompt</div>
  <div class="prompt">{body}</div>
  <div class="subhead">Tools bound to this agent &mdash; in bind order</div>
  {dh_note}
  {undoc_note}
  {tools}
</section>
""".format(
        key=esc(a), idx=idx, name=esc(DISPLAY[a]), role=esc(ROLE[a]),
        chars=esc(chars), toks=esc(toks), ntools=esc(ntools),
        src=esc(rec["prompt_path"]),
        variant_note=variant_note,
        body=prompt_html(rec), dh_note=dh_note, undoc_note=undoc_note,
        tools=tools_html(a, rec),
    )


parts = ["<style>%s</style>" % CSS]

parts.append("""
<div class="cover">
  <div class="kicker">Propeller design configurator &middot; v9</div>
  <h1>The 7-Agent Reduced-Prompt System</h1>
  <div class="rule"></div>
  <div class="sub">Every system prompt exactly as the model receives it &mdash;
  fully assembled, all fragments spliced in, all conditional regions resolved
  &mdash; followed by the complete tool set bound to each agent.
  Text that appears <mark style="background:#fff6c2;padding:0 3px">only when
  RAG is switched on</mark> is highlighted.</div>
  <div class="meta">
    <div><b>Configuration</b> &nbsp; SYSTEM_TOPOLOGY = 7 &nbsp;&middot;&nbsp;
         all settings at their committed defaults</div>
    <div><b>Source</b> &nbsp; commit {commit} &nbsp;&middot;&nbsp; {date}</div>
    <div><b>Agents</b> &nbsp; 9 &nbsp;&middot;&nbsp; ~{chars} characters of
         assembled prompt</div>
  </div>
</div>
""".format(
    commit=COMMIT, date=COMMIT_DATE,
    chars=fmt_int(sum(len(D["agents"][a]["rag_off"]["prompt"]) for a in AGENTS)),
))

# --- how it was produced -----------------------------------------------------
parts.append("""
<section class="first">
  <div class="sec-kicker">Front matter</div>
  <h2 class="sec">What this document is, and how it was produced</h2>
  <p class="lead">Nothing here was transcribed by hand. Each prompt below is the
  output of the repository&rsquo;s own assembler
  (<span class="m">agents/shared/prompts.py</span>), executed against the working
  tree at commit {commit} with <span class="m">SYSTEM_TOPOLOGY&nbsp;=&nbsp;7</span>.
  That means every layer a real session applies has been applied:</p>
  <ul>
    <li>each agent&rsquo;s own <span class="m">prompt.md</span>, plus any topology override that applies;</li>
    <li>all <span class="m">$slot</span> fragments spliced in, over two
        substitution passes, so fragments that reference other fragments
        resolve too;</li>
    <li>per-agent <em>scoped copies</em> of shared fragments, which silently
        replace the shared text for one agent only;</li>
    <li>every conditional region resolved for the settings in force &mdash;
        <span class="m">&lt;&lt;DCII_ONLY&gt;&gt;</span>,
        <span class="m">&lt;&lt;PF_ON/OFF&gt;&gt;</span>,
        <span class="m">&lt;&lt;BSV_ON/OFF&gt;&gt;</span>,
        <span class="m">&lt;&lt;MESH_ON/OFF&gt;&gt;</span>,
        <span class="m">&lt;&lt;CHAIN_ONLY&gt;&gt;</span>,
        <span class="m">&lt;&lt;HAS_DBA&gt;&gt;</span>;</li>
    <li>the runtime <span class="m">{{slot}}</span> values each agent fills in at
        wiring time &mdash; the routing section built by
        <span class="m">agents/shared/routing.py</span>, the
        Orchestrator&rsquo;s chain-access block, the Tool Caller&rsquo;s
        render-backend block, the DC Output Inspector&rsquo;s image-persistence
        and comparison-mode blocks, and the file paths.</li>
  </ul>
  <p>The assembled prompts were checked for leftovers: <b>zero</b> unresolved
  <span class="m">$slots</span>, <span class="m">{{slots}}</span> or
  <span class="m">&lt;&lt;markers&gt;&gt;</span> remain in any of the nine.</p>

  <p><b>Paths.</b> Absolute paths are shown as they resolve in the deployed
  Railway container, whose working directory is
  <span class="m">/app</span> &mdash; so the inputs directory reads
  <span class="m">/app/inputs</span>. A local checkout would show its own
  repository root in the same positions.</p>

  <p><b>Tools.</b> Each agent&rsquo;s tool list is the real
  <span class="m">langchain</span> tool objects, in the exact order they are
  passed to <span class="m">bind_tools</span>, with the description string and
  the argument schema the model is actually given. Tools shared between agents
  are printed in full under every agent that holds them, so each agent&rsquo;s
  pages stand alone.</p>

  <h3>The highlighting</h3>
  <p>The committed default is <span class="m">RAG_ENABLED = False</span>. Every
  agent was therefore assembled <em>twice</em> &mdash; once with RAG off, once
  with it on &mdash; and the two versions diffed. The result is that RAG in this
  system is <b>purely additive</b>: not one character of any prompt is present
  with RAG off and absent with RAG on. So there is nothing to mark in a second
  colour, and the scheme is simply:</p>
  <ul>
    <li><b>Plain text</b> &mdash; the prompt as it stands today, with RAG off.</li>
    <li><mark style="background:#fff6c2;padding:0 3px"><b>Yellow</b></mark> &mdash;
        text and tools that appear <em>only</em> when RAG is switched on.</li>
  </ul>
  <p>Highlighting reflects the real per-agent distribution in the
  <span class="m">&ldquo;7-reduced&rdquo;</span> database-access profile, not a
  hypothetical all-on state &mdash; which is why three agents carry no yellow at
  all (see the grid overleaf).</p>

</section>
""".format(commit=COMMIT))

# --- contents ----------------------------------------------------------------
parts.append("""
<section>
  <div class="sec-kicker">Front matter</div>
  <h2 class="sec">Contents</h2>
  <p class="lead">Each agent starts on its own page: the assembled system prompt
  first, then every tool bound to it, in the order the model receives them. Two
  appendices follow the nine agents.</p>
  {toc}
  <h3>Appendices</h3>
  <ol class="toc">
    <li><span class="num">A</span>Which files fed which prompt</li>
    <li><span class="num">B</span>Orchestrator &mdash; Role-4 feedback
        instructions</li>
  </ol>
</section>
""".format(toc=contents()))

# --- configuration -----------------------------------------------------------
parts.append("""
<section>
  <div class="sec-kicker">Front matter</div>
  <h2 class="sec">Configuration these prompts were assembled under</h2>
  <p class="lead">Every value below is the one committed in
  <span class="m">workflow_settings/settings.py</span> at the stated commit,
  except the two that select the variant. Change any of them and the assembled
  text changes with it.</p>
  {cfg}

  <h3>Database-tool distribution &mdash; profile &ldquo;7-reduced&rdquo;</h3>
  <p class="lead">These flags only take effect when
  <span class="m">RAG_ENABLED</span> is true; the master switch overrides them
  all. <span class="m">&#9679;</span> = held, <span class="m">&#9675;</span> =
  not held.</p>
  {grid}

  <div class="note">
    <span class="h">Consistency note &mdash; three tools bound but never
    described.</span>
    The profile grants <code>retrieve_attempt</code> to the DC Input Creator,
    the DC Input Inspector and the DC Output Inspector. None of those three
    prompts contains the string &ldquo;retrieve_attempt&rdquo; anywhere: their
    prompt files carry no <span class="m">$retrieve_attempt_tool</span> slot and
    no prose description. With RAG on, those agents would be handed a tool the
    system prompt never mentions. The inverse case is clean &mdash; the User
    Input Inspector, Planner and Orchestrator <em>do</em> carry the slot but have
    the flag off, so the loader blanks it and no stale reference survives. The
    affected tools are flagged again in the agents&rsquo; own tool lists.
  </div>
</section>
""".format(cfg=config_table(), grid=grid_table()))

for i, a in enumerate(AGENTS, 1):
    parts.append(agent_section(a, i))

# --- appendix A --------------------------------------------------------------
parts.append("""
<section id="appendix-a">
  <div class="sec-kicker">Appendix A</div>
  <h2 class="sec">Which files fed which prompt</h2>
  <p class="lead">The assembled prompts above are seamless by design &mdash; a
  reader cannot tell where one fragment ends and the next begins. This appendix
  restores that information without marking up the prompt text. For each agent
  it lists every <span class="m">$slot</span> its prompt file consumes and the
  file the loader actually resolved that slot to, honouring the reduced
  variant&rsquo;s overrides and per-agent scoped copies. Slots marked
  <em>nested</em> are referenced by another fragment rather than by the prompt
  file directly.</p>
  {prov}
</section>
""".format(prov=provenance_html()))

# --- appendix B --------------------------------------------------------------
parts.append("""
<section id="appendix-b">
  <div class="sec-kicker">Appendix B</div>
  <h2 class="sec">Orchestrator &mdash; Role-4 feedback instructions</h2>
  <div class="note"><span class="h">Not part of any system prompt.</span>
  This file is read by the Orchestrator at end of session and injected as a
  conversation message during the feedback round, so it never appears in the
  system prompt printed in section 2. It is reproduced here because it is the
  only other authored instruction text the Orchestrator receives. Source:
  <span class="m">agents/orchestrator/role4_feedback_instructions.md</span>.</div>
  <div class="prompt">{body}</div>
</section>
""".format(body=md(ROLE4)))

html_doc = "\n".join(parts)
out = HERE / "system_prompts.html"
with io.open(out, "w", encoding="utf-8") as f:
    f.write("<!doctype html><html><head><meta charset='utf-8'>"
            "<title>7-Agent Reduced-Prompt System</title></head><body>")
    f.write(html_doc)
    f.write("</body></html>")
print("wrote", out, "-", len(html_doc), "chars")
