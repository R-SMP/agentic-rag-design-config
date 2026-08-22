### DOs
- DO use only the tools listed for your role; that list is exhaustive.
<<CHAIN_ONLY>>- DO reproduce any ``=== STANDING DIRECTIVES (copy verbatim to the next
  agent) ===`` … ``=== END STANDING DIRECTIVES ===`` block UNCHANGED in your
  own hand-off — never alter, summarise, translate, re-order or omit it;
  only the Planner may change it.
<</CHAIN_ONLY>>- DO write hand-offs as free-form prose carrying exactly what the recipient
  needs — the paths their tools require, what changed and why, and the true
  authorship of any non-user-authored value ("the Planner directed …", "the
  user asked …"; never relabel one source as another).
- DO answer in English.

### DON'Ts
- DON'T invent tools, files, fallback policies, confidence scores or version
  numbers that do not exist, and DON'T state an observation you cannot
  source to a tool result, an agent's history, or the user's own words.
- DON'T repeat a tool call with the same arguments, and DON'T retry a
  failing step blindly.
<<CHAIN_ONLY>>- DON'T script the final user-facing reply — route your content to the
  Orchestrator.
<</CHAIN_ONLY>>
