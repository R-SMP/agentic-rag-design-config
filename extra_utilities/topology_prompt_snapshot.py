"""Assemble every agent's system prompt for a topology, and diff snapshots.

The repo had no way to assemble the 5-agent prompts at all: the only
assembler, ``extra_utilities/prompt_pdf/dump.py``, is hard-wired to the
7-agent set.  That is the reason topology-5 regressions went unnoticed
(``docs/active/topology5_rebuild_plan.md`` D14).

Usage
-----
    py -3.13 extra_utilities/topology_prompt_snapshot.py save  <dir> [--topology N]
    py -3.13 extra_utilities/topology_prompt_snapshot.py diff  <dirA> <dirB>

``save`` writes ``<dir>/<N>agent/<agent>.txt`` for every agent that
assembles under topology ``N``, plus a ``manifest.json`` carrying the
SHA-256 and character count of each.  With no ``--topology`` it snapshots
EVERY topology in ``ENUM_OPTIONS["SYSTEM_TOPOLOGY"]``.

``diff`` compares two snapshot directories and reports, per topology and
per agent, whether the prompt is byte-identical, moved (with a unified
diff), appeared or disappeared.  That report IS the verification standard
this rebuild works to: never claim "unchanged" without it.

Why a subprocess per topology
-----------------------------
``prompts.py`` reads ``SYSTEM_TOPOLOGY`` fresh on every call, but it
captures ``PLANNER_FIRST`` and ``DC_INSPECTOR_ENABLED`` at IMPORT.  Once
those two are forced per topology (plan D6), assembling two topologies in
one process would give the second one the first one's flags.  One process
per topology sidesteps that permanently.

Why the agent list is not hard-coded
------------------------------------
It is derived from ``routing_tools.AGENT_DISPLAY`` plus the Database
Handler, and every key is attempted.  Agents that do not exist in a
topology fail to assemble and are recorded as ``unavailable`` with their
exception, so the script keeps working across the whole rebuild without
edits -- and a NEWLY failing agent shows up as a diff rather than as
silence.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_BOOTSTRAP_DIR = REPO / "extra_utilities" / "prompt_pdf"


# ---------------------------------------------------------------------------
# Assembly (runs in a child process, one per topology)
# ---------------------------------------------------------------------------

# Production (Railway/Docker) paths, matching prompt_pdf/dump.py so the
# two harnesses describe the same deployed prompt.
_USER_INPUTS_DIR = "/app/inputs"
_EXTRACTION_FILE = "/app/inputs/extracted_inputs.txt"
_USER_QUERY_FILE = "/app/inputs/user_query.txt"
_INPUT_IMAGES_SUBDIR = "input_images"

# Routing SHAPE per (topology, agent): the arguments the agent's
# ``set_routing_tools`` passes to ``routing.routing_instructions``.
# Transcribed, exactly as dump.py does -- ``_wire_routing`` lives on a hub
# class that cannot be constructed without langchain, so there is nothing to
# read it from.
#
# Topology 5's shape comes from ``Planner5._wire_routing``: the hub forwards
# to the DC Input Creator, the DCIC's next is the Tool Caller (there is no DC
# Input Inspector to pass through), and the Tool Caller's prev is the DCIC.
# Keyed off the EFFECTIVE DCII state rather than the raw setting, because
# ``prompts._dcii_effective()`` is hard-False wherever the hub is not the
# Orchestrator.
_ROUTING_SHAPE: dict[str, tuple] = {
    # agent: (agent_name, next_agent, prev_agent, fragment_name)
    "planner": ("Planner", "DC Input Creator", "User Input Inspector",
                "routing_planner_uii_first.md"),
    "user_input_inspector": ("User Input Inspector", "Planner", None,
                             "routing_user_input_inspector_uii_first.md"),
    "dc_input_creator": ("DC Input Creator", None, "Planner",
                         "routing_dc_input_creator_uii_first.md"),
    "dc_input_inspector": ("DC Input Inspector", "Tool Caller",
                           "DC Input Creator", "routing_dc_input_inspector.md"),
    "tool_caller": ("Tool Caller", "DC Output Inspector", None,
                    "routing_tool_caller.md"),
    "dc_output_inspector": ("DC Output Inspector", None, "Tool Caller",
                            "routing_dc_output_inspector.md"),
}


def _runtime_slots(agent: str, P, S) -> dict | None:
    """The ``.format()`` kwargs *agent* is constructed with, or None.

    None means "this agent's prompt is never ``.format()``ed" (the hub and the
    Database Handler); the caller then uses the template verbatim.
    """
    from agents.shared.routing import routing_instructions

    # The EFFECTIVE value, not the raw setting: topology 5 has no DC Input
    # Inspector whatever the flag says, so its DCIC forwards to the Tool
    # Caller and its Tool Caller's previous is the DCIC.
    from agents.shared import prompts as _P
    dcii = _P._dcii_effective()

    def routing(agent_key: str) -> str:
        name, nxt, prev, frag = _ROUTING_SHAPE[agent_key]
        if agent_key == "dc_input_creator":
            nxt = "DC Input Inspector" if dcii else "Tool Caller"
        if agent_key == "tool_caller":
            prev = "DC Input Inspector" if dcii else "DC Input Creator"
        return routing_instructions(agent_name=name, next_agent=nxt,
                                    prev_agent=prev, fragment_name=frag)

    if agent == "receptionist":
        return dict(user_inputs_dir=_USER_INPUTS_DIR,
                    extraction_output_file=_EXTRACTION_FILE)
    if agent == "orchestrator":
        import agents.orchestrator.orchestrator as ORCH
        return dict(chain_access_block=(ORCH._CHAIN_ACCESS_ON if S.CHAIN_ACCESS
                                        else ORCH._CHAIN_ACCESS_OFF))
    if agent == "planner":
        return dict(routing_instructions=routing("planner"),
                    user_inputs_dir=_USER_INPUTS_DIR,
                    input_images_subdir=_INPUT_IMAGES_SUBDIR,
                    extraction_output_file=_EXTRACTION_FILE)
    if agent == "tool_caller":
        return dict(
            routing_instructions=routing("tool_caller"),
            render_check_library_block=(
                (P.RENDER_CHECK_LIBRARY_PYVISTA
                 if S.RENDER_LIBRARY == "pyvista"
                 else P.RENDER_CHECK_LIBRARY_TRIMESH)
                if S.MESH_CHECKS else P.RENDER_CHECK_LIBRARY_OFF),
        )
    if agent == "dc_output_inspector":
        import agents.dc_output_inspector.dc_output_inspector as DCOI_M
        return dict(
            routing_instructions=routing("dc_output_inspector"),
            image_persistence_block=(DCOI_M._IMAGE_PERSISTENCE_ON
                                     if S.KEEP_IMAGES_IN_CONTEXT
                                     else DCOI_M._IMAGE_PERSISTENCE_OFF),
            comparison_mode_block=DCOI_M._build_comparison_mode_block(
                S.DCOI_COMPARISON_MODE, _EXTRACTION_FILE, _USER_QUERY_FILE),
        )
    if agent in _ROUTING_SHAPE:
        return dict(routing_instructions=routing(agent))
    return None


def _assemble(topology: int) -> dict:
    """Assemble every agent's prompt under *topology*.

    Imports happen INSIDE this function, after ``SYSTEM_TOPOLOGY`` is set,
    so any import-time flag capture sees the right value.
    """
    sys.modules["simplejson"] = None          # type: ignore[assignment]
    sys.modules["chardet"] = None             # type: ignore[assignment]
    sys.path.insert(0, str(_BOOTSTRAP_DIR))
    import bootstrap                          # noqa: E402
    bootstrap.install()

    import workflow_settings.settings as settings   # noqa: E402
    settings.SYSTEM_TOPOLOGY = topology

    from agents.shared import prompts as P          # noqa: E402
    from agents.shared import topology as T         # noqa: E402
    from agents.shared.routing_tools import AGENT_DISPLAY   # noqa: E402

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from hub_registry import built_here                     # noqa: E402

    # AGENT_DISPLAY is the topology-NEUTRAL identity registry -- nothing
    # iterates it to BUILD agents.  Iterating it unfiltered made the
    # 5-agent section assemble an Orchestrator and a DC Input Inspector,
    # and the 3-agent section a Planner and a Tool Caller: chimeras built
    # with the ACTIVE topology's slot resolution.  This tool IS the
    # evidence for "which agents did my edit move", so rows for prompts
    # that cannot exist at runtime make that evidence lie.
    _built = built_here()
    candidates = [k for k in sorted(AGENT_DISPLAY) if k in _built]
    if "database_handler" not in candidates:
        candidates.append("database_handler")

    out: dict = {
        "topology": T.topology(),
        "hub_key": T.hub_key(),
        "hub_display": T.hub_display(),
        "planner_first": bool(getattr(P, "PLANNER_FIRST", False)),
        "dcii_enabled": bool(P._dcii_effective()),
        "prompts": {},
        "unavailable": {},
    }
    out["templates"] = {}
    for agent in candidates:
        try:
            template = P._build_template(agent)
        except Exception as exc:                     # noqa: BLE001
            out["unavailable"][agent] = f"{type(exc).__name__}: {exc}"
            continue
        out["templates"][agent] = template
        # The FULL prompt is the template with its runtime {slots} filled in.
        # ``{routing_instructions}`` is the whole reason this matters: it is
        # not part of the template, and it is where every topology difference
        # lives (hub display name, section set, natural-flow string).
        try:
            slots = _runtime_slots(agent, P, settings)
            out["prompts"][agent] = (
                template.format(**slots) if slots else template
            )
        except Exception as exc:                     # noqa: BLE001
            out["prompts"][agent] = template
            out["unformatted"] = out.get("unformatted", {})
            out["unformatted"][agent] = f"{type(exc).__name__}: {exc}"
    return out


def _child_main(topology: int) -> int:
    """Entry point for the per-topology child process: JSON on stdout."""
    try:
        payload = _assemble(topology)
    except Exception as exc:                          # noqa: BLE001
        payload = {"topology": topology, "fatal": f"{type(exc).__name__}: {exc}"}
    sys.stdout.write(json.dumps(payload))
    return 0


def _run_child(topology: int) -> dict:
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()),
         "_child", str(topology)],
        capture_output=True, text=True, cwd=str(REPO),
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(
            f"topology {topology} assembly failed (rc={proc.returncode})\n"
            f"{proc.stderr[-4000:]}"
        )
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------

def _topologies() -> list[int]:
    sys.path.insert(0, str(REPO))
    from workflow_settings.editor import ENUM_OPTIONS
    return [int(v) for v in ENUM_OPTIONS["SYSTEM_TOPOLOGY"]]


def cmd_save(outdir: Path, topology: int | None) -> int:
    targets = [topology] if topology is not None else _topologies()
    outdir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {}

    for n in targets:
        data = _run_child(n)
        if "fatal" in data:
            print(f"[{n}-agent] FATAL {data['fatal']}")
            manifest[str(n)] = {"fatal": data["fatal"]}
            continue

        sub = outdir / f"{n}agent"
        sub.mkdir(parents=True, exist_ok=True)
        rows = {}
        for agent, text in sorted(data["prompts"].items()):
            # newline="" so the assembled text is written byte-for-byte;
            # the fragments are CRLF and must not be silently translated.
            (sub / f"{agent}.txt").write_text(text, encoding="utf-8",
                                              newline="")
            tmpl = data.get("templates", {}).get(agent, text)
            rows[agent] = {
                "chars": len(text),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "template_chars": len(tmpl),
                "template_sha256":
                    hashlib.sha256(tmpl.encode("utf-8")).hexdigest(),
            }
        manifest[str(n)] = {
            "hub_key": data["hub_key"],
            "hub_display": data["hub_display"],
            "planner_first": data["planner_first"],
            "dcii_enabled": data["dcii_enabled"],
            "prompts": rows,
            "unavailable": data["unavailable"],
            "unformatted": data.get("unformatted", {}),
        }
        print(f"[{n}-agent] hub={data['hub_key']} "
              f"PF={data['planner_first']} DCII={data['dcii_enabled']} "
              f"built={len(rows)} unavailable={len(data['unavailable'])}")
        print(f"    {'agent':<24} {'full':>7} {'sha':<13}"
              f"{'template':>9} {'sha':<13}")
        for agent, row in rows.items():
            print(f"    {agent:<24} {row['chars']:>7} "
                  f"{row['sha256'][:12]} {row['template_chars']:>9} "
                  f"{row['template_sha256'][:12]}")
        for agent, err in sorted(data.get("unformatted", {}).items()):
            print(f"    {agent:<24} !! not formatted: {err}")
        for agent, err in sorted(data["unavailable"].items()):
            print(f"    {agent:<24} -- {err}")

    (outdir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8",
    )
    print(f"\nwrote {outdir / 'manifest.json'}")
    return 0


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def cmd_diff(a: Path, b: Path, context: int) -> int:
    ma = json.loads((a / "manifest.json").read_text(encoding="utf-8"))
    mb = json.loads((b / "manifest.json").read_text(encoding="utf-8"))

    moved = 0
    for n in sorted(set(ma) | set(mb), key=lambda s: -int(s)):
        ra, rb = ma.get(n, {}), mb.get(n, {})
        pa = ra.get("prompts", {})
        pb = rb.get("prompts", {})
        print(f"\n=== topology {n} "
              f"(hub {ra.get('hub_key')} -> {rb.get('hub_key')}) ===")
        for key in ("hub_key", "hub_display", "planner_first", "dcii_enabled"):
            if ra.get(key) != rb.get(key):
                print(f"  ! {key}: {ra.get(key)!r} -> {rb.get(key)!r}")
                moved += 1

        for agent in sorted(set(pa) | set(pb)):
            if agent not in pa:
                print(f"  + {agent:<24} APPEARED  {pb[agent]['chars']} chars")
                moved += 1
                continue
            if agent not in pb:
                print(f"  - {agent:<24} DISAPPEARED  {pa[agent]['chars']} chars")
                moved += 1
                continue
            if pa[agent]["sha256"] == pb[agent]["sha256"]:
                print(f"  = {agent:<24} byte-identical  "
                      f"{pa[agent]['chars']} chars")
                continue
            moved += 1
            d = pa[agent]["chars"]
            e = pb[agent]["chars"]
            print(f"  ~ {agent:<24} MOVED  {d} -> {e} chars ({e - d:+d})")
            ta = (a / f"{n}agent" / f"{agent}.txt").read_text(
                encoding="utf-8", newline="").splitlines()
            tb = (b / f"{n}agent" / f"{agent}.txt").read_text(
                encoding="utf-8", newline="").splitlines()
            for line in difflib.unified_diff(
                ta, tb, fromfile=f"{a.name}/{n}/{agent}",
                tofile=f"{b.name}/{n}/{agent}", n=context, lineterm="",
            ):
                print("      " + line)

        ua, ub = ra.get("unavailable", {}), rb.get("unavailable", {})
        for agent in sorted(set(ua) | set(ub)):
            if ua.get(agent) != ub.get(agent):
                print(f"  ! {agent:<24} unavailable: "
                      f"{ua.get(agent, '-')!r} -> {ub.get(agent, '-')!r}")
                moved += 1

    print(f"\n{moved} difference(s).")
    return 0


def main(argv: list[str]) -> int:
    # Windows consoles default to cp1252.  Every diff until now was
    # all-byte-identical, so no unified-diff body was ever printed; the
    # first genuinely moved prompt put a character from the prompt text
    # itself through print() and killed the run with UnicodeEncodeError
    # PART WAY THROUGH the report -- which reads as the tool finding
    # fewer differences than it had, the worst possible failure for the
    # one check this rebuild's verification rests on.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):        # pragma: no cover
        pass

    if len(argv) >= 2 and argv[0] == "_child":
        return _child_main(int(argv[1]))

    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("save", help="assemble and snapshot prompts")
    s.add_argument("outdir", type=Path)
    s.add_argument("--topology", type=int, default=None)

    d = sub.add_parser("diff", help="compare two snapshot directories")
    d.add_argument("a", type=Path)
    d.add_argument("b", type=Path)
    d.add_argument("--context", type=int, default=2)

    args = ap.parse_args(argv)
    if args.cmd == "save":
        return cmd_save(args.outdir, args.topology)
    return cmd_diff(args.a, args.b, args.context)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
