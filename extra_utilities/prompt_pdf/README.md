# prompt_pdf — assemble the agents' system prompts into a reviewable PDF

Two jobs live here:

1. **Build** a PDF of every agent's *fully assembled* system prompt — all
   fragments spliced, all conditional regions resolved, all runtime `{slot}`
   values filled — followed by the complete tool set bound to that agent
   (name + description + argument schema, in `bind_tools` order). Text that
   appears only when RAG is enabled is highlighted.
2. **Extract** a marked-up copy of that PDF back into source anchors, so a
   review round of highlights and comments becomes a list of file + line-range
   edits.

Nothing here is imported by the application. It is a review tool.

## Requirements

```
pip install pymupdf markdown pypdf requests
```

Plus Chrome or Edge for the HTML→PDF step. Everything else the scripts need
(langchain-core, the repo's own modules) is either already installed or stubbed
— see *Two traps* below.

## Build a PDF

Run from anywhere; paths are derived from the script location.

```bash
python extra_utilities/prompt_pdf/dump.py          # -> dump.json
python extra_utilities/prompt_pdf/provenance.py    # -> provenance.json
python extra_utilities/prompt_pdf/build_html.py    # -> system_prompts.html
```

Then render. Chrome is the only supported renderer:

```bash
chrome --headless=new --disable-gpu --no-pdf-header-footer --generate-pdf-document-outline --print-to-pdf=out.pdf --virtual-time-budget=30000 "file:///<abs path>/extra_utilities/prompt_pdf/system_prompts.html"
```

`dump.py` forces `SYSTEM_TOPOLOGY = 7` and reads every other workflow setting
from disk. It assembles each agent **twice**, with `RAG_ENABLED` false and true,
so `build_html.py` can diff the two and highlight what RAG adds. RAG is purely
additive in this system — no text is present with RAG off and absent with it on
— which is why there is only one highlight colour.

## Extract a marked-up PDF

After a reviewer highlights and comments on the built PDF:

```bash
python extra_utilities/prompt_pdf/extract_annotations.py <annotated.pdf>   # -> cuts.md
```

`cuts.md` lists every highlight grouped by agent and source file, with the line
range it maps to. It needs `provenance.json` from the build step, so run the
build first.

Matching works by normalising both sides — markdown syntax stripped, all
whitespace removed — then substring-searching the agent's prompt and its
fragments. Spans under ~15 characters, spans covering only a tool's name, and
text generated at runtime by `agents/shared/routing.py` do not match and are
listed separately for placing by hand.

Two things about reviewer annotations that are easy to get wrong: typed comments
may be **flattened into the page content** rather than stored as popup notes, so
recover them by diffing the annotated page's text against the original's; and a
highlight's covered words must be found by testing each word's **centre** against
the annotation's quads — `get_textbox()` on the annotation rect drags in
neighbouring lines and produces unusable text.

## Two traps

**The import shim.** `agents/shared/prompts.py` can be run without the LLM
stack, but two things block a naive import: `agents/__init__.py` pulls in the
Orchestrator (and with it all of langchain), and a dozen native/runtime packages
are not installed in a dev checkout. `bootstrap.py` replaces the `agents`
package with a bare namespace module and installs a meta-path finder that stubs
a fixed denylist of third-party roots. The denylist is deliberate, not a
catch-all: stubbing anything missing also stubs `chardet` and `simplejson`, which
breaks `requests` with a metaclass conflict. If an import fails after a
dependency change, add that one name to `STUB_ROOTS`.

**Chrome silently shrink-to-fits.** If any single element overflows the
printable width, Chrome's `--print-to-pdf` scales the *whole document* down
rather than reporting the overflow. It looks like a tighter, nicer layout — the
page count simply drops. One unbreakable file path in one appendix table once
rendered a 113-page document at 82%, turning 8.7 pt text into 7.14 pt. The CSS
therefore sets `overflow-wrap: anywhere` on table cells and code. To check a
build, read the real rendered size back out of the PDF:

```python
from collections import Counter
from pypdf import PdfReader
sizes = Counter()
def v(text, cm, tm, font, size):
    if text.strip():
        sizes[round(abs(size * tm[3] * cm[3]), 2)] += len(text.strip())
PdfReader("out.pdf").pages[29].extract_text(visitor_text=v)
print(sizes.most_common(1))       # must be 8.7 — anything lower means it shrank
```

The `cm[3]` factor is essential. Without it a shrunken and an unshrunken file
report the same number.

## Generated files

`dump.json`, `provenance.json`, `system_prompts.html`, `cuts.md` and any `.pdf`
are build artefacts and are gitignored.
