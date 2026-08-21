# Working agreements — standing rules for this repo

These are the user's standing instructions for how development on this
repo is carried out.  They were written down during the reduced-agent
build and lived at the top of
`docs/archive/agent_count_variants_build_tracker.md` until that file was
archived; they are reproduced here **verbatim** because they are not
specific to that task.

Provenance: `agent_count_variants_build_tracker.md` lines 11-29, section
"Golden rules for this whole task (from the user — always valid)".

---

## Golden rules (from the user — always valid)

1. **Faithful-merge rule.** The merged/tailored prompt must contain
   EVERY instruction, detail, and nuance from the source(s). The ONLY
   permitted changes: (a) agent names / topology references re-pointed;
   (b) the specific agreed conflicts removed or tailored; (c) a concept
   that appears in BOTH sources collapsed to one copy. Otherwise keep the
   original wording, structure, and logic. When in doubt, preserve
   verbatim.
2. **Propose-then-apply, per change.** Show the exact change; the user has
   final say on EACH change; ask (via the multiple-choice tool) on any
   fork or slight uncertainty; apply nothing without showing it first.
3. **No Claude coauthor / attribution** in commits or PRs.
4. **PowerShell/bash blocks touching the repo start with `cd "<worktree>"`.**
5. **Step by step.** Do not run ahead on design / architecture decisions.
6. **Every fragment gets a per-system copy** tailored to that structure.
   The **Receptionist is an EXTRA agent** — always present, not one of the
   "5" or the "3".

---

## Scope notes (added when lifting, not part of the original text)

- Rules **2, 3, 4, 5** are general and apply to any work in this repo.
- Rules **1** and **6** were authored for the prompt-merge task
  specifically.  Rule 1's *spirit* — never silently drop content when
  merging — generalises to any merge, including documentation merges;
  rule 6 is prompt-layer-specific.
- Rule 1 is the reason documentation merges in this repo append verbatim
  and demote superseded text to a "Historical" section rather than
  deleting it.
