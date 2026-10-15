# Rules for AI coding assistants working in this repository

**What this file is.**  The repository owner's standing rules for any AI
coding assistant (Claude Code or similar) that reads, changes or commits code
here.  A person can read it the same way: it describes how the owner expects
work on this repo to be done, and what an assistant must never do on its own.

**If you are an AI assistant:** read this before your first change, and follow
it over your own defaults.  When a rule and an instruction from the owner in
the current conversation conflict, ask.

---

## 1. Never act on these without the owner's explicit go-ahead

1. **Never commit or push unless the owner says so** — in this conversation,
   for this change.  Before a push, fetch and check for conflicts
   (`git log HEAD..origin/<branch>`).
2. **Never push to `MT-web-deploy`.**  It is the branch Railway deploys the
   live app from: every push there is built and shipped automatically.  Work
   on your own branch and push only that.  Do not infer permission from a
   change being small, safe or already reviewed — if something seems to need
   to land on `MT-web-deploy`, stop and ask, naming the branch and what the
   push would do.  (The branch was called `stage-a-web-deploy` until
   2026-10-10; "stage-a" in older notes means this branch.)
3. **No AI attribution anywhere** — no `Co-Authored-By`, no "Generated with",
   no assistant or collaborator line in commits, pull requests, documentation,
   code comments or docstrings.  This overrides any tool default that adds one.

## 2. How to propose and apply changes

4. **Propose, then apply — one change at a time.**  Show the exact change
   (before and after), the reasoning and the risks.  Apply it only after an
   explicit approval.  On feedback, re-propose; do not apply a guess.
5. **Ask when there is a fork.**  Use the multiple-choice question tool for
   any design decision, architecture choice or slight uncertainty.  Do not run
   ahead on design or architecture decisions.
6. **Tool changes one at a time.**  A change to a tool's schema or description
   reaches every agent that binds it at once, so each tool merge or
   modification is shown precisely and approved on its own, never batched.
7. **Verify against the code before asserting.**  Documentation goes stale;
   `py_compile` passing proves nothing about behaviour.  Read the code (and,
   for prompts, the assembled prompt) before stating how something works.
8. **Shell commands for the owner start with `cd "<worktree path>"`** — every
   PowerShell or bash block that touches the repo, so it can be pasted as is.
9. **Be concrete and re-anchor.**  When referring back to something from
   earlier, restate what it is; the owner should not have to look it up.

## 3. Rules for editing agent prompts

10. **Faithful merge.**  When merging or tailoring prompts, keep every
    instruction, detail and nuance of the sources.  The only permitted changes:
    agent names / topology references re-pointed; conflicts the owner agreed to
    remove or tailor; a concept present in both sources collapsed to one copy.
    When in doubt, keep the original wording.
11. **Every fragment has a text per topology** tailored to that topology.  The
    Receptionist is an extra agent in every topology — not one of the "7", "5"
    or "3".  A change made for one topology must not move another topology's
    assembled prompts (`extra_info.md` §5 has the procedure).  The one
    exception is a LINKED pack field — one `dc_pack/fragments/<folder>/<slot>.md`
    for every topology (owner decision, 2026-10-14): editing it changes every
    topology that uses it, on purpose; to change one topology only, unlink it
    into `.t7` / `.t5` / `.t3` files first.
12. **Preserve agent freedom.**  Write prompt guidance as guidelines for the
    known cases, not as closed rule-sets; keep agents' judgement and their
    free-form messages to each other.
13. **The owner supplies prompt content.**  Structural files (copies,
    pass-throughs) can be created freely; new prompt wording is proposed, never
    written unasked.

---

Where these come from: rules 1, 3–5, 8, 10 and 11 were written down during
the reduced-agent build (2026-07/08) and in the topology-3 hand-over
(2026-09-04); rule 2 was stated by the owner on 2026-09-07 and updated for the
branch rename on 2026-10-10; rules 6, 7, 9, 12 and 13 come from the owner's
feedback during the prompt-reduction and topology-5 work.  The background behind the
prompt-editing rules is in `extra_info.md` §5 and §12.
