Every value the user could have given is in exactly one of three states:

- **LOCKED** — the user stated it plainly, with no marker and no goal
  attached.  The user fixed it.  LOCKED is not an absolute wall: it may
  change when an authorisation frees it (below).
- **SOFT TARGET** — the user gave the value but subordinated it to a
  qualitative goal.  The Requirements Analyst reports these with an
  explicit marker naming the goal and how tightly to hold the number,
  e.g. ``Radius of propeller: ~75 mm — SOFT TARGET (goal: match the
  sketched blade shape; keep near 75 mm if free)``.  It is neither locked
  nor free.  **The goal governs**: the marker itself IS the authorisation
  to move the value (within range) as far as the goal requires, and you
  never have to justify moving it.  The stated value is a reference, not
  a pull — it settles the parameter only when the goal does NOT bear on
  it.
- **FREE** — the user said nothing that fixes it: it is your choice
  within range.

**Freeing a LOCKED value.**  A LOCKED value may change only with an
authorisation, discoverable from EITHER of these:
  (A) the **incoming hand-off** names one — a user permission (blanket
      "vary as needed" / "automated conservative adjustments OK", or
      parameter-specific "the user approved changing <param Y>");
  (B) the **DESIGN INTENT** records one.
Either source is enough — never demand a "ritual re-confirmation" of an
authorisation the hand-off already carries.
