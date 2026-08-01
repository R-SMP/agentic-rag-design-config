<!-- DRAFT — 5-agent system · the routing LAYER (not a $slot fragment).
     Source: agents/shared/routing.py (NATURAL_PIPELINE + routing_instructions()).
     That file is LIVE and drives the 7-agent system, so nothing here is applied
     to it — the eventual home is a topology-selected variant, pending the
     topology-selector discussion. This file records the exact 5-agent strings
     so the port is mechanical when that lands. -->

# 1. NATURAL_PIPELINE (5-agent)

The 7-agent string starts and ends at the hub and omits the Receptionist,
because there the Receptionist hands to the Orchestrator rather than into the
chain.  In the 5-agent flow the Receptionist routes straight to the UII, so it
IS the UII's natural previous and belongs in the string:

    Receptionist → User Input Inspector → Conductor → Creator →
    Tool Caller → DC Output Inspector → Conductor

Per-agent positions passed to ``routing_instructions(agent, next, prev, frag)``:

| agent                | previous      | next                |
|----------------------|---------------|---------------------|
| User Input Inspector | Receptionist  | Conductor           |
| Creator              | Conductor     | Tool Caller         |
| Tool Caller          | Creator       | DC Output Inspector |
| DC Output Inspector  | Tool Caller   | Conductor (last)    |

The Conductor is NOT built by ``routing_instructions()`` — it is the hub and
uses the static ``$routing_conductor`` fragment, exactly as the Orchestrator
uses ``$routing_orchestrator`` today.  The Receptionist likewise uses its own
static ``$routing_receptionist`` fragment.

# 2. Boilerplate re-points inside routing_instructions()

Every "Orchestrator" in the shared boilerplate becomes "Conductor".  The
mechanical ones:

  * "If the **Orchestrator's** instruction in your incoming message told you
    to *continue the pipeline*…" → **Conductor's**
  * "If the **Orchestrator's** instruction told you to *report back*… route to
    the **Orchestrator** once your work is done." → **Conductor's** / **Conductor**
  * "…no agent in the chain can fix it, route to the **Orchestrator**
    (ESCALATE)." → **Conductor**
  * "You are the last agent in the natural flow; completing normally means
    handing control back to the **Orchestrator**." → **Conductor**
  * "You are the first agent in the natural flow; if you need to go 'back',
    that means handing control to the **Orchestrator**." → **Conductor**.
    NOTE: this branch never fires in the 5-agent system — every chain agent
    has a previous, since the UII's is the Receptionist.
  * "ESCALATE to the **Orchestrator** with a short note…  The **Orchestrator**
    can then re-dispatch you…" → **Conductor** (twice)
  * "### Permission / authorisation issues → **Orchestrator** (not the
    previous agent)" → **Conductor**

## The one substantive change, NOT a rename

The authorisation paragraph names the Planner as a separate source.  With the
Planner merged into the Conductor, the list collapses.  Current text:

> "The previous agent in the chain typically CANNOT grant permission —
> authorisations come from the user (relayed by the Receptionist →
> Orchestrator), from the Planner (relayed by the Orchestrator), or from the
> Orchestrator itself."

5-agent text:

> "The previous agent in the chain typically CANNOT grant permission —
> authorisations come from the user (relayed by the Receptionist →
> Conductor), or from the Conductor itself."

Everything else in that paragraph — read the hand-off once more before
escalating, act on an authorisation that plausibly covers the action even if
the wording differs, do NOT bounce back for a ritual re-confirmation, CLARIFY
back only for data / wording / format issues — is unchanged.

The remaining boilerplate sections ("Do not loop — ESCALATE when stuck" beyond
the rename, and "Routing is a tool call — MANDATORY" in full) are
topology-agnostic and carry over verbatim.

# 3. REQUIRED WIRING — the Receptionist needs two runtime slots (F1)

The UII reads and writes files ONLY via paths given in its hand-off — its tool
handlers refuse without them (*"Error: no directory path provided"*) and its
prompt says "don't guess".  In the 5-agent flow the **Receptionist** is the
UII's entry point, so it must emit:

    Input directory: {user_inputs_dir}
    Extraction output file: {extraction_output_file}

That text is in `draft_prompt_receptionist.md`.  Two code changes must land
WITH it, or prompt assembly fails:

  * `agents/shared/prompts.py` — `"receptionist": frozenset()` becomes
    `frozenset({"user_inputs_dir", "extraction_output_file"})`.
  * `agents/receptionist/receptionist.py:88` — `_build_template("receptionist")`
    becomes `.format(user_inputs_dir=..., extraction_output_file=...)`,
    mirroring `agents/planner/planner.py:224-229`.

**⚠ HAZARD this introduces.** The Receptionist is currently the ONLY agent
whose template takes no runtime slots, so it has never been `.format()`ed.
Once it is, a literal `{` or `}` in ANY of its 22 spliced fragments breaks
assembly at import — the codebase's top recorded gotcha.  Verified clean as of
2026-07-31 (the only fragment-tree braces are in README files, which are not
spliced).  Re-check on every fragment edit.

## ⚠ RELATED LIVE FINDING — the 7-agent uii-first flow has the same hole

Traced 2026-07-31, code-conclusive: the ONLY place those labels are emitted is
`agents/planner/prompt.md:38-39` — and that block sits inside `<<PF_ON>>`.  The
live default is **PF_OFF (uii-first)**, so the block is STRIPPED and **no agent
in the live system emits the labels at all**.  Confirmed further: only
`planner.py:225-227` populates the slots; `prompts.py:499` grants them to the
Planner alone; the Orchestrator's allow-list is only `chain_access_block`; the
UII's is only `routing_instructions`; nothing injects them at runtime; and both
UII tool handlers error out without a path, their messages still saying
"supplied by the Planner" (fossil wording from when planner-first was default).

Since real runs (ID228 / ID229) succeed, the UII must be INFERRING the
conventional paths and happening to be right.  That is a latent fragility, not
a working design — it breaks if a path convention changes or a model guesses
differently.  **Fixing the 7-agent needs its own change** (Orchestrator prompt
text + its allow-list + `orchestrator.py`); NOT yet proposed to the owner.

# 4. Conditional filters

``_load_routing_fragment`` resolves ``<<DCII_ONLY>>`` / ``<<DCII_OFF>>`` and
``<<PF_ON>>`` / ``<<PF_OFF>>``.  The 5-agent fragments contain NONE of these:
the DCII no longer exists as a separate agent, and the flow is fixed as
uii-first rather than being a runtime choice.  Both pairs were resolved at
authoring time — DCII pairs to the **DCII_OFF** branch (re-pointed to the
Creator), PF pairs to the **PF_OFF** branch.

> Authoring trap, caught by the Creator audit: the DCIC's line
> ``<<PF_ON>>the UII<</PF_ON>><<PF_OFF>>the Planner<</PF_OFF>>`` was first
> resolved to the PF_ON branch by mistake, pointing the Creator's CLARIFY at
> the UII.  The 5-agent flow is **PF_OFF**, so the correct resolution is "the
> Planner" → **the Conductor**.  Check the flag direction on every PF pair.
