"""The 7-agent REDUCED variant's forked code.

``SYSTEM_TOPOLOGY`` is the agent COUNT; ``PROMPT_VARIANT`` is which set of
prompts — and now which code — that same agent set runs on.  Everything under
this package is selected ONLY when ``PROMPT_VARIANT == "reduced"`` and
``SYSTEM_TOPOLOGY == 7``; the standard 7-agent system and the 5- and 3-agent
topologies never import it.

WHY A REPO-ROOT MIRROR.  ``agents/7agent_reduced/`` holds this variant's ``.md``
overrides, but a directory whose name starts with a digit is not a valid Python
package, and ``tools/`` is a sibling of ``agents/`` rather than a child — so
only a repo-root tree can mirror the real layout.  Paths here mirror the
original EXACTLY, with no filename suffix: the path is the identifier, and
``reduced7/agents/shared/routing.py`` diffs against ``agents/shared/routing.py``
by a plain prefix swap.

DELEGATE, DON'T DUPLICATE.  A forked module re-implements only what actually
differs and IMPORTS the rest from its original.  Copying machinery that has not
changed is how the two trees silently drift apart, and drift here is invisible:
a stale copy produces a plausible prompt, not an error.

EVERY FORKED FILE CARRIES a header naming its origin path and the commit it was
forked at, so a reader can diff it against the original without guessing.
"""
