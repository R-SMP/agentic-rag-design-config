"""Which agent keys does a topology's hub actually BUILD?

Read from the hub class's own ``_agents_by_key`` literal, because that
dict is what the runtime resolves against: ``database_handler.py`` looks a
schedule row's ``from_agent`` up in it, and dispatch routes through it.
An agent key absent from it does not merely warn -- the Database Handler's
unknown-agent branch persists an ``ERROR:`` row into the R2 mirror and the
Postgres ``chunks`` table, where it comes back at retrieval time.

**Do not answer this question from a hand-maintained roster.** There are
two tables named ``AGENTS_BY_TOPOLOGY`` and neither is this:

* ``agents/shared/sessions_queue.py`` -- ``dict[int, list[tuple[str, str]]]``,
  keys 7/5/3, and it lists ``context_pruner``;
* ``extra_utilities/smoke_test_topology_fragments.py`` --
  ``dict[int, list[str]]``, keys 7 and 5 only.

Different shapes, so code written against one raises on the other, and
BOTH are supersets of the thing that actually gates: they name
``context_pruner`` and ``database_handler``, which no hub registers.  A
schedule row naming ``database_handler`` would pass a check written
against either one and still write an ``ERROR:`` chunk.

Parsed from SOURCE rather than from a built hub: constructing one
materialises every sub-agent's LLM and needs real API keys, which neither
a smoke test nor a diagnostic tool should require.  Both hubs write
``self._agents_by_key`` as a static dict literal, so the keys are exact.

The core reader takes a PATH, not a class, because
``smoke_test_dh_batching.py`` runs with ``langchain_core`` stubbed out and
must never import an agent module -- ``agents/__init__.py`` eagerly
imports every agent class.  :func:`built_here` is the convenience wrapper
for callers that can import.
"""

from __future__ import annotations

import ast
from pathlib import Path


def registry_keys_from_source(path) -> set[str]:
    """The literal keys of ``self._agents_by_key`` in the module at *path*.

    An unparsed key becomes a ``<unparsed:...>`` member rather than being
    dropped, so a caller that asserts on this set fails loudly if either
    hub ever stops using a plain dict literal.
    """
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    agent_key: str | None = None
    keys = None
    for node in ast.walk(tree):
        # ``AGENT_KEY = "planner"`` -- Planner5 uses ``self.AGENT_KEY`` as a
        # registry key rather than repeating the literal.
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "AGENT_KEY"
                        for t in node.targets)
                and isinstance(node.value, ast.Constant)):
            agent_key = node.value.value
        # AnnAssign, not Assign: both hubs write
        # ``self._agents_by_key: dict = {...}``.
        if (isinstance(node, ast.AnnAssign)
                and getattr(node.target, "attr", None) == "_agents_by_key"
                and isinstance(node.value, ast.Dict)):
            keys = node.value.keys
    if keys is None:
        return set()
    out: set[str] = set()
    for k in keys:
        if isinstance(k, ast.Constant):
            out.add(k.value)
        elif isinstance(k, ast.Attribute) and k.attr == "AGENT_KEY":
            out.add(agent_key)
        else:
            out.add(f"<unparsed:{ast.dump(k)[:40]}>")
    return out


def built_here() -> set[str]:
    """Agent keys the ACTIVE topology's hub registers.

    Asks ``agents.hub.hub_class()`` which hub the topology uses, so this
    never duplicates that mapping, then reads that class's source.  Empty
    when the topology has no hub module yet -- topology 3's Architect is
    not built -- which is the honest answer rather than an error.
    """
    import inspect

    try:
        from agents.hub import hub_class
        cls = hub_class()
    except ImportError:
        return set()
    src = inspect.getsourcefile(cls)
    return registry_keys_from_source(src) if src else set()
