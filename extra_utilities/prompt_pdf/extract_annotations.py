"""Emit per-agent, per-file cut tables from the PDF annotations."""
import io
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import pymupdf

REPO = Path(__file__).resolve().parents[2]   # <repo>/extra_utilities/prompt_pdf/x.py
ANN = sys.argv[1] if len(sys.argv) > 1 else None
if not ANN:
    raise SystemExit(
        "usage: extract_annotations.py <annotated.pdf>  (run build_html.py first, so provenance.json exists)")

NAME = {(0.859, 0.204, 0.145): "RED", (0.988, 0.957, 0.522): "YEL",
        (1.0, 0.757, 0.0): "DKYEL", (0.773, 0.984, 0.447): "GREEN"}

AGENT_PAGES = {
    "receptionist": range(5, 15),
    "orchestrator": range(15, 26),
    "planner": range(26, 41),
    "user_input_inspector": range(41, 53),
}

HERE = Path(__file__).resolve().parent
PROV = json.load(open(HERE / "provenance.json", encoding="utf-8"))

EXTRA = [
    "agents/shared/routing.py",
    "reduced7/agents/shared/routing.py",   # pre-promotion fork; skipped when absent
    "agents/shared/prompt_fragments/routing_planner_uii_first.md",
    "agents/shared/prompt_fragments/routing_user_input_inspector_uii_first.md",
    "agents/shared/prompt_fragments/routing_receptionist.md",
    "agents/shared/prompt_fragments/routing_orchestrator.md",
    "agents/shared/user_inputs_tool.py",
    "agents/shared/attempts_tool.py",
]


def norm(s):
    s = unicodedata.normalize("NFKC", s)
    for a, b in (("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'),
                 ("\u201d", '"'), ("\u2013", "-"), ("\u2014", "-"),
                 ("\u2212", "-"), ("\u00a0", " "), ("\u2009", " ")):
        s = s.replace(a, b)
    s = re.sub(r"[`*_]", "", s)
    return re.sub(r"\s+", "", s)


class Hay:
    def __init__(self, path):
        self.path = path
        self.lines = path.read_text(encoding="utf-8").splitlines()
        buf, idx = [], []
        for ln, line in enumerate(self.lines, 1):
            t = norm(line)
            if not t:
                continue
            buf.append(t)
            idx.extend([ln] * len(t))
        self.text = "".join(buf)
        self.idx = idx

    def line_of(self, pos):
        return self.idx[min(pos, len(self.idx) - 1)] if self.idx else 0


def candidates(agent):
    out, seen = [], set()
    p = PROV[agent]
    for rel in [p["prompt_file"]] + \
               [r["file"] for r in p["fragments"] if r["file"]] + EXTRA:
        if rel in seen:
            continue
        seen.add(rel)
        fp = REPO / rel
        if fp.is_file():
            out.append(Hay(fp))
    return out


def find(needle, hays):
    n = norm(needle)
    if len(n) < 5:
        return None
    best = None
    for h in hays:
        pos = h.text.find(n)
        if pos >= 0:
            return (h, pos, pos + len(n), 1.0)
        sm = SequenceMatcher(None, h.text, n, autojunk=False)
        m = sm.find_longest_match(0, len(h.text), 0, len(n))
        r = m.size / len(n)
        if r > 0.6 and (best is None or r > best[3]):
            best = (h, m.a, m.a + m.size, r)
    return best


doc = pymupdf.open(ANN)
rows = {}          # agent -> file -> list of (l0, l1, colour, pdfpage, text)
unmatched = {}

for agent, pages in AGENT_PAGES.items():
    hays = candidates(agent)
    rows[agent], unmatched[agent] = {}, []
    for pno in pages:
        if pno > doc.page_count:
            break
        page = doc[pno - 1]
        words = page.get_text("words")
        for a in sorted(page.annots() or [],
                        key=lambda a: (round(a.rect.y0), a.rect.x0)):
            c = a.colors.get("stroke")
            col = NAME.get(tuple(round(x, 3) for x in c), "?") if c else "?"
            v = a.vertices or []
            rects = [pymupdf.Quad(v[i:i + 4]).rect
                     for i in range(0, len(v) - 3, 4)] or [a.rect]
            pick = [w for w in words
                    if any(r.x0 - .5 <= (w[0] + w[2]) / 2 <= r.x1 + .5
                           and r.y0 - .5 <= (w[1] + w[3]) / 2 <= r.y1 + .5
                           for r in rects)]
            pick.sort(key=lambda w: (w[5], w[6], w[7]))
            txt = " ".join(w[4] for w in pick).strip()
            if not txt:
                continue
            if len(norm(txt)) < 15:
                unmatched[agent].append((col, pno, "SHORT: " + txt))
                continue
            hit = find(txt, hays)
            if hit is None:
                unmatched[agent].append((col, pno, txt))
                continue
            h, s, e, r = hit
            rel = str(h.path.relative_to(REPO)).replace("\\", "/")
            rows[agent].setdefault(rel, []).append(
                (h.line_of(s), h.line_of(e - 1), col, pno, txt, r))

out = io.open(HERE / "cuts.md", "w", encoding="utf-8")
for agent in AGENT_PAGES:
    out.write("\n## %s\n" % agent)
    for rel in sorted(rows[agent]):
        spans = sorted(set(rows[agent][rel]))
        # merge spans that touch or overlap AND share a colour
        merged = []
        for sp in spans:
            if merged and sp[2] == merged[-1][2] and sp[0] <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], sp[1]),
                              sp[2], merged[-1][3],
                              merged[-1][4] + " " + sp[4], min(merged[-1][5], sp[5]))
            else:
                merged.append(list(sp) and tuple(sp))
        out.write("\n### %s  (%d spans)\n\n" % (rel, len(merged)))
        out.write("| lines | colour | p. | text |\n|---|---|---|---|\n")
        for l0, l1, col, pno, txt, r in merged:
            flag = "" if r == 1.0 else " ~"
            t = txt.replace("|", "\\|")
            if len(t) > 300:
                t = t[:150] + " … " + t[-120:]
            out.write("| %d-%d%s | %s | %d | %s |\n"
                      % (l0, l1, flag, col, pno, t))
    if unmatched[agent]:
        out.write("\n### UNMATCHED (place by hand)\n\n")
        for col, pno, txt in unmatched[agent]:
            out.write("- [%s] p.%d — %s\n" % (col, pno, txt[:200].replace("|", "\\|")))
out.close()
print("wrote cuts.md")
for a in AGENT_PAGES:
    print(a, sum(len(v) for v in rows[a].values()), "matched,",
          len(unmatched[a]), "unmatched")
