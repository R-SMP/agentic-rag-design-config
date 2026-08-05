# UII cuts — verification of the "the Routing block already says it" claim

**Date:** 2026-08-05 · **Method:** 6 independent finders, each adversarially
refuted by a second agent instructed to default to *refuted* when uncertain,
then synthesised. 13 agents, ~968k tokens, 186 tool calls. Every claim was
checked against the **assembled** UII prompt (49,162 chars), not against
`prompt.md` alone.

**Why this file exists.** Eleven of the proposal's UII cuts share one rationale:
*the generated Routing block already states this.* Three of them are safe on
that basis and three would break something. Re-deriving that costs ~968k tokens,
so the evidence is recorded here rather than in a commit message.

---

## Bottom line

**The claim is true for 3 of 11 cuts.** It fails in three distinct ways:

1. **Zero-hit claims.** `STANDING DIRECTIVES` occurs 3 times in the whole
   49,162-char assembled prompt and **all 3 are inside `UII-28`'s own cut
   target**. The routing block has none. The cut deletes the only copy.

2. **Direction confusion.** `UII-43` claims the routing block covers "don't
   answer permission questions". It does not: the routing block fires when
   *your own* action is blocked ("If a rule in your system prompt blocks an
   action…"); the cut fires when a question is put *to* the UII. Opposite
   directions.

3. **Scope error — the two agents most at risk have no routing block at all.**
   Four of these cuts edit `generic_constraints.md`, which is spliced into
   **8** agents. Only **6** have a generated routing block:

   ```
   receptionist           {routing_instructions} = 0
   orchestrator           {routing_instructions} = 0
   planner … dc_output_inspector                 = 1   (six agents)
   ```

   The Receptionist and Orchestrator use the static `$routing_receptionist` /
   `$routing_hub` fragments instead. For them "the Routing block already says
   it" is not merely wrong — it is unverifiable.

---

## Per-cut verdicts

`copies` = how many places in the assembled prompt state the same operative
instruction, counted (not estimated).

| cut | target file | copies | verdict | disposition |
|---|---|---:|---|---|
| `UII-46` | `prompt.md` | 3 | TRUE_DUPLICATE | **apply as written** |
| `UII-31` | `routing.py` | 2 | PARTIAL | **apply — but see F59; this is a generator fix, not a prompt cut** |
| `UII-27` | `routing.py` | 2 | PARTIAL | **apply INVERTED** — see below |
| `UII-36` | `generic_constraints.md` | 9 restatements / 3 locations | PARTIAL | **repair first** — carries the ⚠5 defect |
| `UII-47` | `generic_constraints.md` | 2 | PARTIAL | **repair first** |
| `UII-40` | `generic_constraints.md` | 4 | PARTIAL | **repair first** |
| `UII-44` | `routing_..._uii_first.md` | 3 | PARTIAL | **safe once F59's generator fix lands** |
| `UII-37` | `prompt.md` | 3 | PARTIAL | **repair first** |
| `UII-28` | `generic_constraints.md` | 1 | NOT_A_DUPLICATE | **REJECT** |
| `UII-43` | `prompt.md` | 1 | NOT_A_DUPLICATE | **REJECT** |
| `UII-14` | `prompt.md` | 1 | NOT_A_DUPLICATE | **REJECT** |

Five of eleven finder verdicts were overturned by the refutation pass
(`UII-28`, `UII-43`, `UII-47`, `UII-37`, `UII-44`, `UII-27`, `UII-31`), all in
the direction of *less* duplication than claimed.

---

## The three rejections, with evidence

### `UII-28` — deletes the only copy of the STANDING DIRECTIVES rule

`copies=1`. The claimed "4-copy cluster" is one 4-copy bullet (FORWARD) plus two
1-copy bullets. Load-bearing beyond the prose:

* `agents/shared/standing_directives.py:24-25` defines `BLOCK_START` /
  `BLOCK_END` **byte-identically** to the delimiters quoted in the prompt.
* `extract_directive` is documented as "Tolerant of a missing END delimiter
  (takes the rest of the message)" — a **named, already-observed failure mode**.
* `agents/orchestrator/orchestrator.py:82-85` lists `user_input_inspector` in
  `_DIRECTIVE_CARRIERS`, and re-stamps the block on hops to it — so the UII
  really does receive these blocks; the rule is not decorative there.

The proposal's replacement also silently drops the word "translate" from "never
alter, summarise, translate, re-order, or omit it". Not cosmetic: the same DOs
list contains "DO answer in English; do not substitute words from other
languages or scripts", which is exactly the pressure that would make an agent
render a foreign-language directive into English.

**If savings are wanted here, cut only the FORWARD bullet** — that one genuinely
has 4 copies.

### `UII-43` — the rationale is false

`copies=1`. Three of the four non-answerable classes it covers are not
permission questions at all. Filing it in a "permissions" cluster as PARTIAL is
what makes it dangerous: it reads as redundant when it is a net deletion of the
UII's only inbound-CLARIFY handler.

### `UII-14` — converts a prompt cut into a pipeline break

`copies=1`. Deletes the `Extracted inputs file:` emit contract.
`agents/dc_input_creator/dc_input_creator.py:319` names that label **verbatim**
in its runtime error string, and `agents/planner/planner.py:95-103` names it in
the `read_extracted_inputs` docstring.

**Precision worth keeping:** nothing *regex-parses* these labels. They are named
verbatim in tool docstrings and error strings, so the convention is coupled to
code text and the model honours it. That makes the label names load-bearing
while the surrounding prose carries no mechanical risk — compressing the prose
around them is safe; renaming or dropping the labels is not.

---

## `UII-27` is inverted

The cut deletes the routing block's `### Do not loop — ESCALATE when stuck` and
keeps the `generic_constraints` bullet. That is backwards: the routing-block
version is the **richer** copy. It uniquely carries

* the escalation **target** ("ESCALATE to the `<hub>`" — the generic bullet says
  only "STOP and ESCALATE", naming no recipient),
* the required **content** of the escalation note ("what is ambiguous or missing
  and what you would need to proceed"),
* what happens next ("The `<hub>` can then re-dispatch you with new
  instructions, consult another agent, or ask the user"),
* the *reasoning*-loop trigger, not just the repeated-tool-call trigger.

**Apply it the other way round:** cut the generic bullet, keep the generated one.

---

## Repairs required before applying

| cut | string that MUST survive the replacement |
|---|---|
| `UII-36` | `Every chain agent is bound by this; the only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up.` — plus the named error string `"no routing tool call"`. Also fix the recorded `quote_end`: the fragment line has two leading spaces, so the anchor will not match verbatim. |
| `UII-47` | `do not substitute words from other languages or scripts`, and `— and nothing more.` (the only counterweight to the Orchestrator's own "Lose no useful context"). Resolve the span conflict with `UII-28` in the same file. |
| `UII-40` | `so the Planner can pick a different angle` and the positive destination `Route your content to the Orchestrator`. **See F61** — do not inline "the Planner" as an authorisation source. |
| `UII-37` | The recorded span runs through `quote_end: "DCIC.<</PF_ON>>"` and silently truncates the `PF_ON` branch. Re-scope the cut to end before `<<PF_ON>>`, or restore "badly ambiguous sketch, contradictory instructions" and "routine extractions go to the DCIC". |
| `UII-44` | Safe **only after** F59's generator fix; before it, the cut removes the redirect (`anything that would otherwise be a "back" routes to the Orchestrator instead`) with nothing replacing it. Note also that the stated rationale is false: `routing_tools.py::_TOOL_DESCRIPTIONS["call_planner"]` is one sentence carrying no precondition, so the schemas do **not** already cover the fragment's content. |

---

## ⚠5 (the systematic defect) — confirmed, and defused

`UII-36`'s auditor id is `REC-36`, one of the exact five cuts §9 flags as
sharing the systematic defect. Verified at source: `generic_constraints.md:46-56`
is a single `DON'T` bullet, and `<</CHAIN_ONLY>>` closes **immediately before
it**, so the Receptionist and Orchestrator both receive it. Dropping the
carve-out forbids the Receptionist's only way to answer a user.

**But these four cuts are dangerous only because they rewrite a SHARED file.**
With the per-agent scoped-fragment mechanism (`prompts.SCOPED_FRAGMENTS`,
commit `3c0b4a6`) each can be applied to one agent at a time: the UII never
replies to a user, so the carve-out is genuinely dead weight *there*, while the
Receptionist and Orchestrator keep it intact. The mechanism turns ⚠5 from a
blocker into a non-issue.

---

## Method notes, for anyone repeating this

* Measure against the **assembled** prompt. `{routing_instructions}` is a
  runtime slot filled at wiring time, so `_build_template` alone omits ~4,700
  chars sitting 90% of the way through the prompt — and all of the generated
  duplication lives there.
* Rebuild it with
  `prompts._build_template(agent).format(routing_instructions=routing.routing_instructions(...))`.
  For the UII under `PLANNER_FIRST=False`: `next_agent="Planner"`,
  `prev_agent=None`, `fragment_name="routing_user_input_inspector_uii_first.md"`.
* Substring searches under-count. "natural next step" splits across a newline in
  `prompt.md`; "first agent" appears as both "in the chain" and "in the natural
  flow". Two of my own regex counts were wrong for exactly these reasons before
  reading the source.
* Duplications the proposal misses are recorded as **F60**.
