Every value the user could have given is in exactly one of three states,
read off the extraction's QUANTITATIVE INPUTS section:

- **LOCKED** — a value the user stated plainly there, with no marker.  The
  user fixed it.  LOCKED is not an absolute wall: it may change when an
  authorisation frees it (below).
- **SOFT TARGET** — a value marked ``SOFT TARGET (goal: …; keep near … if
  free)``.  The user subordinated it to that goal, so it is neither locked
  nor free.  **The goal governs**: the marker itself IS the authorisation to
  move the value (within range) as far as the goal requires, and you never
  have to justify moving it.  The stated value is a reference, not a pull —
  it settles the parameter only when the goal does NOT bear on it, and the
  "keep near … if free" strength then says how closely to follow it ("not as
  important" → your choice within range; "prefer X but the shape matters
  more" → use X).
- **FREE** — a parameter absent from QUANTITATIVE INPUTS: either the user never
  specified it, or they specified it and later released it (a value that is no
  longer constrained is simply OMITTED from the section).  Either way it is the
  system's choice within range.  A qualitative
  description that must be turned into a number is FREE for that parameter
  too — unless a directive holds a specific one fixed, which is then treated
  as LOCKED for that cycle.

**Freeing a LOCKED value.**  A LOCKED value may change only with an
authorisation, discoverable from ANY of these (one is enough):
  (A) the **incoming hand-off** names one — a user permission (blanket
      "vary as needed" / "automated conservative adjustments OK", scoped
      "except <param X>", or parameter-specific "the user approved changing
      <param Y>") or a strategy / recovery directive to change the value; a
      CLARIFY bounce may carry one too;
  (B) the **extraction's DESIGN INTENT section** records one — a user
      authorisation the UII wrote, standing every cycle until revoked; or
  (C) the value's own QUANTITATIVE INPUTS line carries an
      ``(unlocked by user)`` annotation, IF PRESENT — an older extraction may
      still carry this inline mark; today a released value is simply omitted
      from the section (which makes it FREE) rather than annotated.
One source is enough — never demand a "ritual re-confirmation" of an
authorisation the hand-off already carries.  A line literally saying
"user-locked" is only the DEFAULT lock and does NOT override a current
authorisation — the hand-off, DESIGN INTENT, and any inline annotation are
the current sources of truth.  How FAR an authorised (or soft) value may
move follows the wording: "as needed / only if necessary" = the smallest
change that restores viability, staying close to the user's number; "freely
/ as much as possible" (or nothing said) = as far as the goal requires,
bounded by range.
