"""Catch a $slot spliced INSIDE a sentence instead of standing alone.

WHY THIS EXISTS.  ``string.Template.safe_substitute`` replaces EVERY occurrence
of a slot.  So when an author means a cross-reference and writes the slot —

    lives in the ``## Modelling Notes`` section above ($modelling_notes)

— the whole fragment expands there, mid-sentence, and the sentence never
closes.  The reader falls into a bullet list and the parenthesis resolves
thousands of characters later.

Nothing else catches it.  The prompt still assembles, every slot still
resolves, no marker is unbalanced, and no other test compares occurrence
counts.  Six live instances were found across four files in one sweep,
costing ~9,450 delivered characters — and THREE MORE a layer down, in
fragments that splice fragments (see ``_scan_targets``), costing 2,643:

    dc_input_inspector/prompt.md      $modelling_notes             2,659
    creator/prompt_5agents.md         $modelling_notes             2,659
    dc_input_creator/prompt.md        $output_file_locations       1,670
    creator/prompt_5agents.md         $output_file_locations       1,670
    receptionist/prompt.md            $invalid_parameter_examples    396
    5agent/receptionist/prompt_*.md   $invalid_parameter_examples    396
    shared/…/available_agents.md      $tool_inventory                881
    5agent/…/available_agents_5*.md   $tool_inventory (twice)      1,762

THE RULE, and why it is objective.  A slot that resolves to MULTI-LINE content
must stand alone on its line.  Scalars are exempt — ``$parameter_count``
renders to ``16`` and is meant to be read inline ("the $parameter_count named
parameters").  Whether a fragment is multi-line is measured from the fragment
file, not guessed, so there is no judgement call: a slot is either alone on its
line or it is not.

THE ONE LEGITIMATE EXCEPTION is a conditional region written inline, which the
marker syntax requires:

    <</BSV_ON>><<BSV_OFF>>$blade_sections_visualizer_off<</BSV_OFF>>
    <</DCII_ONLY>>- $tool_caller_capabilities

so markers and a leading list bullet are stripped before the aloneness test.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRAGMENT_DIRS = (
    ROOT / "DC_prompt_fragments",
    ROOT / "agents" / "shared" / "prompt_fragments",
)

SLOT_RE = re.compile(r"\$([a-z_][a-z0-9_]*)")
MARKER_RE = re.compile(r"<</?[A-Z_]+>>")


def _fragment_shapes() -> dict:
    """slot name -> (chars, lines) of what it resolves to."""
    shapes = {}
    for d in FRAGMENT_DIRS:
        if not d.is_dir():
            continue
        for f in d.rglob("*"):
            if f.is_file() and f.suffix in (".md", ".txt"):
                body = f.read_text(encoding="utf-8").rstrip()
                shapes[f.stem] = (len(body), body.count("\n") + 1 if body else 0)
    return shapes


def _is_alone(line: str, slot: str) -> bool:
    """True when the slot is the line's only content, markers/bullet aside."""
    bare = MARKER_RE.sub("", line).strip()
    if bare.startswith("- "):
        bare = bare[2:].strip()
    return bare == "$" + slot


def _scan_targets() -> list:
    """Every file that gets $slots substituted into it.

    Prompts are the obvious ones.  FRAGMENTS ARE NOT: a fragment may itself
    reference a slot, and ``_build_template`` runs a SECOND substitution pass
    (``prompts.py:1000-1001``) that expands it.  Scanning prompts alone reported
    PASS while three live splices sat one layer down — all three of
    ``$tool_inventory`` (881 chars) exploding inside an ``Available Agents``
    roster sentence, in the 7-agent shared copy and twice in the 5-agent one.

    Variant dirs (``agents/5agent``, ``agents/7agent_reduced``) are included:
    that is where two of the three lived.  Shape lookup still comes from the
    canonical dirs only — override files carry suffixed stems, so they define
    no slot of their own and would add nothing.
    """
    targets = set(ROOT.glob("agents/**/prompt*.md"))
    for d in list(FRAGMENT_DIRS) + sorted(
        p for p in ROOT.rglob("prompt_fragments") if p.is_dir()
    ) + sorted(
        p for p in ROOT.rglob("tools_config") if p.is_dir()
    ) + sorted(
        p for p in ROOT.rglob("dc_config") if p.is_dir()
    ):
        for f in d.rglob("*"):
            # README.md documents the slot syntax; it is prose ABOUT slots,
            # never a substitution target.
            if f.is_file() and f.suffix in (".md", ".txt") and f.name != "README.md":
                targets.add(f)
    return sorted(targets)


def main() -> int:
    shapes = _fragment_shapes()
    prompts = _scan_targets()
    failures = []
    checked = 0

    for p in prompts:
        rel = p.relative_to(ROOT).as_posix()
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for m in SLOT_RE.finditer(line):
                slot = m.group(1)
                chars, lines = shapes.get(slot, (0, 0))
                if lines <= 1:
                    continue          # scalar (or unknown) — inline use is fine
                checked += 1
                if not _is_alone(line, slot):
                    failures.append(
                        "[INLINE SPLICE] %s:%d — $%s resolves to %d chars / %d "
                        "lines but is spliced inside a line:\n"
                        "      %s\n"
                        "      An author writing a cross-reference should name the "
                        "section in prose, not use the slot." % (
                            rel, n, slot, chars, lines, line.strip()[:100])
                    )

    print("scanned %d substitution target(s) (prompts + fragments); "
          "%d multi-line slot reference(s) checked" % (len(prompts), checked))
    if failures:
        print("\nFAIL — %d problem(s):" % len(failures))
        for f in failures:
            print("  " + f)
        return 1
    print("\nPASS — every multi-line fragment slot stands alone on its own line.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
