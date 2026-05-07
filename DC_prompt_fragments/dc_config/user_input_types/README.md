# User-input-type fragments

This subfolder describes the kinds of user inputs THIS particular
design configurator (DC) accepts as references — beyond plain text
in `user_query.txt` — and how every reasoning agent in the system
should treat each one.

Different DCs accept different reference types:

  * One DC may accept hand-drawn **sketches** (qualitative,
    imperfect, not dimensioned).
  * Another may accept **real-life photographs** of physical
    examples (precise visually but possibly with lighting / angle
    artifacts).
  * Another may accept **2D engineering drawings** (precise,
    dimensioned, intended for literal matching).
  * Another may accept **3D renderings / CAD screenshots** (clean,
    geometric, intended for literal matching).
  * Another may accept some combination of the above, or none at
    all (text-only).

Whatever input types this DC accepts, document each one in this
folder as a pair of files:

| File suffix | What goes in it | Slot syntax |
| --- | --- | --- |
| `<type>_handling.md` | Definition of the input type, when to recognise it, and the rules every reasoning agent must follow when working with one. Spliced into the per-agent prompts that interpret / compare user inputs. | `$<type>_handling` |
| `<type>_notes.md` | Operator-curated patterns specific to how users typically draw / capture / supply this input type for THIS DC, plus DC-specific quirks the generic rules cannot capture. | `$<type>_notes` |

When the operator wires a new input type into the system:

  1. Add `<type>_handling.md` and `<type>_notes.md` to this folder.
  2. Register both as new slots in
     `agents/shared/prompts.py` (read with `_read_dc_fragment`,
     add to `_SLOTS` and `__all__`).
  3. Splice `$<type>_handling` and `$<type>_notes` into every
     per-agent template that should know about the input type
     (typically the User Input Inspector, DC Input Creator,
     DC Input Inspector, DC Output Inspector, Planner, and —
     for handling-only — the Receptionist).

When the DC does NOT accept a particular input type (e.g. a
photo-only DC won't accept sketches), simply do not create that
type's fragment files; the per-agent prompts won't reference
slots that don't exist for the current DC.

## Currently registered input types for this DC

| Type | Handling fragment | Notes fragment |
| --- | --- | --- |
| Sketch (hand-drawn, qualitative) | `sketch_handling.md` | `sketch_notes.md` |
