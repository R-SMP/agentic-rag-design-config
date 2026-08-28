"""Smoke test — the Sessions Queue's per-run topology + per-agent tiering.

Covers the pieces that decide what an overnight run actually executes on:

1. ``sessions_queue.ALL_AGENT_KEYS`` still equals
   ``llm_routing.AGENT_KEYS``.  This is the load-bearing one: every key in
   a ``tier_payload`` is fed to ``llm_routing.write_updates``, which
   REJECTS an unknown key outright — so a hub gaining an agent without
   ``AGENTS_BY_TOPOLOGY`` learning about it would fail every tiered run at
   3am, and a stale key here would fail them at the first write.
2. The condition registry is exactly ``current`` / ``single`` / ``tiers``.
3. ``tier_payload`` resolves the active topology's agents and CLEARS
   everyone else's override (the cross-topology leak).
4. Its validation rejects a half-filled panel rather than quietly running
   the wrong model.
5. ``normalize_topology`` defaults a legacy run to 7 but refuses garbage.
6. ``build_manifest`` carries the new fields and validates at BUILD time.

Run: ``py extra_utilities/smoke_test_queue_tiers.py``
(Set ``PYTHONIOENCODING=utf-8`` under Python 3.8 or the arrows kill it.)

Uses the namespace-package shim the other smoke tests use, so the eager
``agents/__init__.py`` -> orchestrator -> trimesh chain never runs: this
file only needs the framework-free helpers.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# Register `agents` / `agents.shared` as NAMESPACE packages so importing
# `agents.shared.sessions_queue` never executes `agents/__init__.py`
# (which imports the whole agent tree, and with it trimesh / langchain).
for _name, _path in (
    ("agents", _ROOT / "agents"),
    ("agents.shared", _ROOT / "agents" / "shared"),
):
    if _name not in sys.modules:
        _mod = types.ModuleType(_name)
        _mod.__path__ = [str(_path)]  # type: ignore[attr-defined]
        sys.modules[_name] = _mod

from agents.shared import sessions_queue as sq          # noqa: E402
from workflow_settings import llm_routing               # noqa: E402

_failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}" + (f"  --  {detail}" if detail else ""))
        _failures.append(label)


def raises(label: str, fn, needle: str = "") -> None:
    """Assert ``fn()`` raises ValueError, optionally mentioning ``needle``."""
    try:
        fn()
    except ValueError as exc:
        if needle and needle.lower() not in str(exc).lower():
            check(label, False, f"raised, but without {needle!r}: {exc}")
        else:
            print(f"  PASS  {label}")
        return
    except Exception as exc:  # noqa: BLE001
        check(label, False, f"raised {type(exc).__name__}, expected ValueError: {exc}")
        return
    check(label, False, "did not raise")


# ---------------------------------------------------------------------------
print("\n1. Agent-key table agrees with llm_routing.AGENT_SPEC")
# ---------------------------------------------------------------------------
routing_keys = set(llm_routing.AGENT_KEYS)
queue_keys = set(sq.ALL_AGENT_KEYS)
check("ALL_AGENT_KEYS == AGENT_KEYS", routing_keys == queue_keys,
      f"queue-only={sorted(queue_keys - routing_keys)} "
      f"routing-only={sorted(routing_keys - queue_keys)}")
check("no duplicate keys in ALL_AGENT_KEYS",
      len(sq.ALL_AGENT_KEYS) == len(set(sq.ALL_AGENT_KEYS)))
for topo in sq.TOPOLOGIES:
    rows = sq.AGENTS_BY_TOPOLOGY[topo]
    keys = [k for k, _ in rows]
    check(f"topology {topo}: no duplicate rows", len(keys) == len(set(keys)))
    check(f"topology {topo}: has a context_pruner row", "context_pruner" in keys)
    check(f"topology {topo}: has a database_handler row", "database_handler" in keys)

# ---------------------------------------------------------------------------
print("\n2. Condition registry")
# ---------------------------------------------------------------------------
ids = [c["id"] for c in sq.list_conditions()]
check("conditions are current/single/tiers", ids == ["current", "single", "tiers"],
      f"got {ids}")
check("no payload leaks from list_conditions",
      all(set(c) == {"id", "label"} for c in sq.list_conditions()))
check("'tiers' has no static payload", sq.routing_payload_for("tiers") is None)
check("known_condition_ids includes tiers", "tiers" in sq.known_condition_ids())

# ---------------------------------------------------------------------------
print("\n3. tier_payload resolves the topology and clears everyone else")
# ---------------------------------------------------------------------------
MODELS = {"low": "L-model", "mid": "M-model", "high": "H-model"}


def full_tiers(topo: int, tier: str = "mid") -> dict:
    return {k: tier for k, _ in sq.AGENTS_BY_TOPOLOGY[topo]}


for topo in sq.TOPOLOGIES:
    tiers = full_tiers(topo)
    # Make one agent HIGH and one LOW so the mapping is actually exercised.
    keys = [k for k, _ in sq.AGENTS_BY_TOPOLOGY[topo]]
    tiers[keys[0]] = "high"
    tiers[keys[-1]] = "low"
    payload = sq.tier_payload(provider="anthropic", low=MODELS["low"],
                              mid=MODELS["mid"], high=MODELS["high"],
                              agent_tiers=tiers, topology=topo)
    by_key = {a["key"]: a for a in payload["agents"]}
    check(f"topology {topo}: mode is individual", payload["mode"] == "individual")
    check(f"topology {topo}: every agent key present",
          set(by_key) == set(sq.ALL_AGENT_KEYS),
          f"missing={sorted(set(sq.ALL_AGENT_KEYS) - set(by_key))}")
    check(f"topology {topo}: no duplicate agent entries",
          len(payload["agents"]) == len(by_key))
    active = set(keys)
    check(f"topology {topo}: active agents carry the provider",
          all(by_key[k]["override_provider"] == "anthropic" for k in active))
    check(f"topology {topo}: tier -> model mapping",
          by_key[keys[0]]["override_model"] == MODELS["high"]
          and by_key[keys[-1]]["override_model"] == MODELS["low"]
          and all(by_key[k]["override_model"] == MODELS["mid"]
                  for k in active - {keys[0], keys[-1]}))
    inactive = set(sq.ALL_AGENT_KEYS) - active
    check(f"topology {topo}: inactive agents CLEARED ({len(inactive)})",
          all(by_key[k]["override_provider"] == "" and by_key[k]["override_model"] == ""
              for k in inactive))
    check(f"topology {topo}: shared is non-empty",
          bool(payload["shared"]["provider"]) and bool(payload["shared"]["model"]))
    # write_updates rejects a PARTIAL override (one field set, one blank).
    check(f"topology {topo}: no partial overrides",
          all(bool(a["override_provider"]) == bool(a["override_model"])
              for a in payload["agents"]))

# The shared fallback must survive a run where no agent uses the mid tier.
only_high = sq.tier_payload(provider="openai", low="", mid="", high="H",
                            agent_tiers=full_tiers(3, "high"), topology=3)
check("shared falls back when the mid box is empty",
      only_high["shared"]["model"] == "H", only_high["shared"]["model"])

# ---------------------------------------------------------------------------
print("\n4. tier_payload validation")
# ---------------------------------------------------------------------------
raises("unknown provider rejected",
       lambda: sq.tier_payload(provider="hal9000", low="a", mid="b", high="c",
                               agent_tiers=full_tiers(7), topology=7),
       "provider")
partial = full_tiers(7)
partial.pop("planner")
raises("agent with no tier rejected",
       lambda: sq.tier_payload(provider="openai", low="a", mid="b", high="c",
                               agent_tiers=partial, topology=7),
       "Planner")
raises("empty tier box rejected",
       lambda: sq.tier_payload(provider="openai", low="a", mid="", high="c",
                               agent_tiers=full_tiers(7, "mid"), topology=7),
       "empty")
raises("bogus tier name rejected",
       lambda: sq.tier_payload(provider="openai", low="a", mid="b", high="c",
                               agent_tiers=full_tiers(7, "medium"), topology=7),
       "no tier selected")
# A 5-agent assignment used under topology 7 leaves 7-agent-only rows unset.
raises("wrong-topology assignment rejected",
       lambda: sq.tier_payload(provider="openai", low="a", mid="b", high="c",
                               agent_tiers=full_tiers(5), topology=7),
       "no tier selected")

# ---------------------------------------------------------------------------
print("\n5. normalize_topology")
# ---------------------------------------------------------------------------
check("None -> 7", sq.normalize_topology(None) == 7)
check("'' -> 7", sq.normalize_topology("") == 7)
check("'5' -> 5", sq.normalize_topology("5") == 5)
check("3 -> 3", sq.normalize_topology(3) == 3)
raises("4 rejected", lambda: sq.normalize_topology(4), "must be one of")
raises("'seven' rejected", lambda: sq.normalize_topology("seven"), "must be one of")
check("agent_rows_for(None) is the 7-agent set",
      [k for k, _ in sq.agent_rows_for(None)]
      == [k for k, _ in sq.AGENTS_BY_TOPOLOGY[7]])

# ---------------------------------------------------------------------------
print("\n6. build_manifest")
# ---------------------------------------------------------------------------
def tier_run(**over) -> dict:
    run = {
        "run_id": "r1", "query": "design a propeller", "condition": "tiers",
        "topology": 5, "tier_provider": "openai",
        "tier_low": "gpt-5.4-mini", "tier_mid": "gpt-5.4", "tier_high": "gpt-5.5",
        "agent_tiers": full_tiers(5),
    }
    run.update(over)
    return run


m = sq.build_manifest(runs=[tier_run()], defaults={})
r = m["runs"][0]
check("topology carried into the manifest", r["topology"] == 5, str(r.get("topology")))
check("tier fields carried", (r["tier_provider"], r["tier_mid"]) == ("openai", "gpt-5.4"))
check("agent_tiers carried", r["agent_tiers"] == full_tiers(5))

# Legacy runs (no topology field at all) must still build, as 7.
legacy = sq.build_manifest(
    runs=[{"run_id": "old", "query": "q", "condition": "current"}], defaults={})
check("legacy run defaults to topology 7", legacy["runs"][0]["topology"] == 7)

# Topology applies to EVERY condition, not just 'tiers'.
mixed = sq.build_manifest(
    runs=[{"run_id": "s", "query": "q", "condition": "single", "topology": 3,
           "single_provider": "openai", "single_model": "gpt-5.4"}], defaults={})
check("topology honoured on a 'single' run", mixed["runs"][0]["topology"] == 3)

raises("half-filled tier panel rejected at BUILD",
       lambda: sq.build_manifest(runs=[tier_run(agent_tiers={})], defaults={}),
       "no tier selected")
raises("bad topology rejected at BUILD",
       lambda: sq.build_manifest(runs=[tier_run(topology=6)], defaults={}),
       "topology")
raises("non-dict agent_tiers rejected",
       lambda: sq.build_manifest(runs=[tier_run(agent_tiers="mid")], defaults={}),
       "agent_tiers")
raises("retired subj5 condition rejected",
       lambda: sq.build_manifest(
           runs=[{"run_id": "x", "query": "q", "condition": "subj5-openai"}],
           defaults={}),
       "unknown condition")

# Iteration expansion must copy the tier assignment onto every iteration.
it = sq.build_manifest(runs=[tier_run(iterations=3)], defaults={})
check("iterations each carry topology + tiers",
      len(it["runs"]) == 3
      and all(x["topology"] == 5 and x["agent_tiers"] == full_tiers(5)
              for x in it["runs"]))

# ---------------------------------------------------------------------------
print()
if _failures:
    print(f"FAILED — {len(_failures)} check(s): {_failures}")
    sys.exit(1)
print("ALL CHECKS PASSED")
