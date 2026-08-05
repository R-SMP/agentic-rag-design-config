"""System Prompts admin-backer smoke test.

Exercises ``workflow_settings.prompts_admin`` end-to-end against a
tempdir mirror — the real fragments under ``DC_prompt_fragments/``
and ``agents/shared/prompt_fragments/`` are NEVER touched.

What's covered:

  * :func:`build_tree` shape — 4 groups, correct files per group,
    used_by populated for $-slot + WIRING-time + per-agent files.
  * :func:`read_file` returns content + ``has_conditional_regions``
    flag (true for files with ``<<…>>`` markers, false otherwise).
  * :func:`save_files` writes atomically and returns
    ``affected_agents`` per file + the warnings list.
  * Path safety — ``_resolve_safe('../etc/passwd')`` and
    ``_resolve_safe('agents/.../prompt.exe')`` both raise
    ``PromptsAdminError``.
  * Validation rules — unknown $slot, unbalanced <<…>>, unescaped
    ``{x}`` in a prompt.md, and empty file each surface their own
    warning kind.

Run with:

    python extra_utilities/smoke_test_prompts_admin.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Pre-stub the ``agents`` package so its real ``__init__.py`` (which
# imports the langchain-dependent ``Orchestrator``) doesn't run.
# Same trick as smoke_test_prompts_hot_reload.py; see that file's
# comment for the full rationale.
_agents_stub = types.ModuleType("agents")
_agents_stub.__path__ = [str(REPO_ROOT / "agents")]
sys.modules.setdefault("agents", _agents_stub)

from workflow_settings import prompts_admin as pa  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture writer — mirrors the real 4 source-root layout under tmp_root
# ---------------------------------------------------------------------------

# Receptionist + Planner are enough to exercise prompt-md and an
# agent with no .format() runtime slots.
_AGENT_PROMPT_MD = {
    "receptionist": (
        "You are the Receptionist for a $domain_description.\n"
        "$hard_constraints_generic\n"
    ),
    "planner": (
        "You are the Planner for a $domain_description.\n"
        "Input directory: {user_inputs_dir}\n"
        "$pipeline_flow\n"
        "{routing_instructions}\n"
        "<<PF_ON>>planner-first branch<</PF_ON>>\n"
    ),
}


def _write_fixtures(tmp_root: Path) -> None:
    """Write a minimal but representative mirror of the 4 source roots."""
    agents_dir       = tmp_root / "agents"
    shared_fragments = agents_dir / "shared" / "prompt_fragments"
    dc_config        = tmp_root / "DC_prompt_fragments" / "dc_config"
    user_input_types = dc_config / "user_input_types"
    tools_config     = tmp_root / "DC_prompt_fragments" / "tools_config"
    render_check     = tools_config / "render_check_library"

    for d in (
        shared_fragments, user_input_types, render_check,
        agents_dir / "receptionist", agents_dir / "planner",
    ):
        d.mkdir(parents=True)

    # Per-agent prompt.md files
    for agent_dir, body in _AGENT_PROMPT_MD.items():
        (agents_dir / agent_dir / "prompt.md").write_text(body, encoding="utf-8")

    # Shared fragments — $-slot owners
    (shared_fragments / "generic_constraints.md").write_text(
        "[GENERIC_CONSTRAINTS]", encoding="utf-8",
    )
    (shared_fragments / "pipeline_flow_planner_first.md").write_text(
        "[PF_PLANNER]", encoding="utf-8",
    )
    (shared_fragments / "pipeline_flow_uii_first.md").write_text(
        "[PF_UII]", encoding="utf-8",
    )
    # Shared fragments — WIRING-time
    (shared_fragments / "routing_planner_planner_first.md").write_text(
        "[ROUTING_PLANNER_PF]", encoding="utf-8",
    )
    # README — used_by should be empty
    (shared_fragments / "README.md").write_text("# readme", encoding="utf-8")

    # DC-config fragments
    (dc_config / "domain_description.txt").write_text(
        "fixture-domain", encoding="utf-8",
    )
    (dc_config / "structure.md").write_text("[STRUCTURE]", encoding="utf-8")
    # Subfolder
    (user_input_types / "sketch_handling.md").write_text(
        "[SKETCH]", encoding="utf-8",
    )

    # Tools-config fragments
    (tools_config / "database_search.md").write_text(
        "[DBSEARCH]", encoding="utf-8",
    )
    # Per-agent overlay (WIRING-time)
    (tools_config / "database_search_planner.md").write_text(
        "[DBSEARCH_PLANNER]", encoding="utf-8",
    )
    # Render-check (WIRING-time, in a subfolder)
    (render_check / "trimesh.md").write_text("[TRIMESH]", encoding="utf-8")
    (render_check / "pyvista.md").write_text("[PYVISTA]", encoding="utf-8")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _collect_files(node: dict, acc: list[dict]) -> None:
    if node.get("kind") == "file":
        acc.append(node)
    for child in node.get("children", []) or []:
        _collect_files(child, acc)


def main() -> int:
    # Snapshot every constant we are about to monkey-patch so the
    # finally block restores cleanly.
    orig = {
        "REPO_ROOT":     pa.REPO_ROOT,
        "_SOURCE_ROOTS": pa._SOURCE_ROOTS,
    }
    tmp_dir = Path(tempfile.mkdtemp(prefix="prompts_admin_"))
    failures: list[str] = []
    try:
        _write_fixtures(tmp_dir)

        pa.REPO_ROOT     = tmp_dir
        pa._SOURCE_ROOTS = (
            tmp_dir / "agents",
            tmp_dir / "agents" / "shared" / "prompt_fragments",
            tmp_dir / "DC_prompt_fragments" / "dc_config",
            tmp_dir / "DC_prompt_fragments" / "tools_config",
        )

        # -------- build_tree shape --------
        tree = pa.build_tree()
        groups = {g["id"]: g for g in tree["groups"]}
        if set(groups) != {"per_agent", "routing_shared", "dc_config", "tools_config"}:
            failures.append(f"build_tree: unexpected group ids {sorted(groups)}")

        per_agent_files: list[dict] = []
        _collect_files({"children": groups["per_agent"]["children"]}, per_agent_files)
        if {f["display"] for f in per_agent_files} != {"receptionist", "planner"}:
            failures.append(
                f"build_tree per_agent: expected "
                f"{{'receptionist','planner'}}, got "
                f"{[f['display'] for f in per_agent_files]}"
            )

        # routing_shared should contain README.md + generic_constraints +
        # pipeline_flow_planner_first + pipeline_flow_uii_first +
        # routing_planner_planner_first.
        routing_files: list[dict] = []
        _collect_files({"children": groups["routing_shared"]["children"]}, routing_files)
        wanted_routing = {
            "README.md",
            "generic_constraints.md",
            "pipeline_flow_planner_first.md",
            "pipeline_flow_uii_first.md",
            "routing_planner_planner_first.md",
        }
        if {f["display"] for f in routing_files} != wanted_routing:
            failures.append(
                f"build_tree routing_shared: expected {wanted_routing}, "
                f"got {sorted(f['display'] for f in routing_files)}"
            )

        # used_by spot-checks.
        usage_by_path = {f["path"]: f["used_by"] for f in routing_files}
        readme_used = usage_by_path.get(
            "agents/shared/prompt_fragments/README.md", "MISSING"
        )
        if readme_used != []:
            failures.append(f"README used_by expected [], got {readme_used!r}")

        gc_used = usage_by_path.get(
            "agents/shared/prompt_fragments/generic_constraints.md", "MISSING"
        )
        # generic_constraints feeds $hard_constraints_generic — used by
        # 'receptionist' (only agent in the fixture that references it).
        if gc_used != ["receptionist"]:
            failures.append(
                f"generic_constraints used_by expected ['receptionist'], "
                f"got {gc_used!r}"
            )

        rp_used = usage_by_path.get(
            "agents/shared/prompt_fragments/routing_planner_planner_first.md",
            "MISSING",
        )
        # WIRING-time hardcoded → ['planner']
        if rp_used != ["planner"]:
            failures.append(
                f"routing_planner used_by expected ['planner'], got {rp_used!r}"
            )

        # tools_config — render_check subfolder + database_search overlay.
        tc_files: list[dict] = []
        _collect_files({"children": groups["tools_config"]["children"]}, tc_files)
        tc_paths = {f["path"] for f in tc_files}
        expected_tc_paths = {
            "DC_prompt_fragments/tools_config/database_search.md",
            "DC_prompt_fragments/tools_config/database_search_planner.md",
            "DC_prompt_fragments/tools_config/render_check_library/trimesh.md",
            "DC_prompt_fragments/tools_config/render_check_library/pyvista.md",
        }
        if tc_paths != expected_tc_paths:
            failures.append(
                f"tools_config files: expected {expected_tc_paths}, "
                f"got {tc_paths}"
            )

        # -------- read_file --------
        rf = pa.read_file("agents/planner/prompt.md")
        if "<<PF_ON>>" not in rf["content"]:
            failures.append("read_file: expected content to include <<PF_ON>>")
        if rf["has_conditional_regions"] is not True:
            failures.append(
                "read_file: planner prompt has <<PF_ON>>, "
                "has_conditional_regions should be True"
            )

        rf2 = pa.read_file("agents/shared/prompt_fragments/generic_constraints.md")
        if rf2["has_conditional_regions"] is not False:
            failures.append(
                "read_file: generic_constraints has no markers, "
                "has_conditional_regions should be False"
            )

        # -------- Path safety --------
        for bad in ("../../etc/passwd", "agents/../../etc/passwd",
                    "agents/planner/prompt.exe", ""):
            try:
                pa._resolve_safe(bad)
            except pa.PromptsAdminError:
                pass
            else:
                failures.append(
                    f"_resolve_safe({bad!r}) should have raised PromptsAdminError"
                )

        # -------- save_files: happy path --------
        result = pa.save_files([{
            "path": "agents/shared/prompt_fragments/generic_constraints.md",
            "content": "[GENERIC_CONSTRAINTS_MUTATED]",
        }])
        if not result.get("ok"):
            failures.append(f"save_files happy path: result not ok: {result!r}")
        written = result.get("files_written", [])
        if len(written) != 1:
            failures.append(
                f"save_files: expected 1 file_written entry, got {len(written)}"
            )
        elif written[0].get("affected_agents") != ["receptionist"]:
            failures.append(
                f"save_files: expected affected_agents=['receptionist'], "
                f"got {written[0].get('affected_agents')!r}"
            )
        # Read-back confirms the disk content actually changed.
        rb = pa.read_file(
            "agents/shared/prompt_fragments/generic_constraints.md"
        )
        if "MUTATED" not in rb["content"]:
            failures.append(
                f"save_files: read-back missing MUTATED content: {rb!r}"
            )

        # -------- Validation rule (a) — unknown $slot --------
        warnings_a = pa.validate_one(
            "agents/shared/prompt_fragments/generic_constraints.md",
            "hello $not_a_real_slot world",
        )
        if not any(w["kind"] == "unknown_slot" and "not_a_real_slot" in w["detail"]
                   for w in warnings_a):
            failures.append(
                f"validate_one (rule a): expected unknown_slot warning, "
                f"got {warnings_a!r}"
            )

        # -------- Validation rule (b) — unbalanced <<…>> --------
        warnings_b = pa.validate_one(
            "agents/shared/prompt_fragments/generic_constraints.md",
            "line one\n<<PF_ON>>open with no close\nline three",
        )
        if not any(w["kind"] == "unbalanced_marker" for w in warnings_b):
            failures.append(
                f"validate_one (rule b): expected unbalanced_marker, "
                f"got {warnings_b!r}"
            )

        # -------- Validation rule (c) — unescaped { in prompt.md --------
        warnings_c = pa.validate_one(
            "agents/receptionist/prompt.md",
            "header\n{unexpected_slot}\nfooter",
        )
        if not any(w["kind"] == "brace_escape" and "unexpected_slot" in w["detail"]
                   for w in warnings_c):
            failures.append(
                f"validate_one (rule c, receptionist=no slots): expected "
                f"brace_escape warning, got {warnings_c!r}"
            )

        warnings_c_ok = pa.validate_one(
            "agents/planner/prompt.md",
            "header {routing_instructions} footer",
        )
        if any(w["kind"] == "brace_escape" for w in warnings_c_ok):
            failures.append(
                f"validate_one (rule c, planner allows routing_instructions): "
                f"expected no brace_escape warning, got {warnings_c_ok!r}"
            )

        # -------- Empty-file warning --------
        warnings_empty = pa.validate_one(
            "agents/shared/prompt_fragments/generic_constraints.md", "",
        )
        if not any(w["kind"] == "empty_file" for w in warnings_empty):
            failures.append(
                f"validate_one (empty): expected empty_file warning, "
                f"got {warnings_empty!r}"
            )

    finally:
        for name, val in orig.items():
            setattr(pa, name, val)
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # -- _used_by for per-agent SCOPED COPIES (real repo paths, not fixtures) --
    #
    # Two properties.  A scoped copy must report its ONE owning agent, not the
    # empty list (which reads as "orphan" in the tree and, worse, as
    # "affected agents: none" on the save receipt for a file that changes
    # exactly one system prompt).  And the BASE fragment must STOP counting an
    # agent once that agent has its own copy, or its badge over-counts by one
    # more with every copy added.
    #
    # Ordering matters and is the thing most likely to regress: the base
    # fragment is a FRAGMENT_TO_SLOT key, so a scoped copy falling through to
    # that branch would report every agent whose prompt.md mentions the slot.
    slot_usage = pa._prompt_md_slot_usage()
    base_rel = "DC_prompt_fragments/dc_config/hard_constraints_dc.md"
    scoped_rel = (
        "DC_prompt_fragments/dc_config/hard_constraints_dc_dc_input_inspector.md"
    )
    overlay_rel = "DC_prompt_fragments/tools_config/database_search_planner.md"

    got = pa._used_by(scoped_rel, slot_usage)
    if got != ["dc_input_inspector"]:
        failures.append(
            f"_used_by(scoped copy): expected ['dc_input_inspector'], got {got!r}"
        )

    # The pre-existing _per_agent OVERLAYS use the same basename shape but a
    # different mechanism; they must keep resolving via _WIRING_TIME_USAGE.
    got = pa._used_by(overlay_rel, slot_usage)
    if got != ["planner"]:
        failures.append(
            f"_used_by(database_search overlay): expected ['planner'], got {got!r}"
        )

    base_before = pa._used_by(base_rel, slot_usage)
    probe = pa.REPO_ROOT / scoped_rel
    if probe.exists():
        failures.append(
            f"scoped-copy probe {probe.name} already exists — refusing to "
            "overwrite a real file; rename the probe"
        )
    else:
        try:
            probe.write_text("probe\n", encoding="utf-8")
            base_with = pa._used_by(base_rel, slot_usage)
            if "dc_input_inspector" in base_with:
                failures.append(
                    "_used_by(base): dc_input_inspector has its own scoped copy "
                    f"but is still counted against the shared file: {base_with!r}"
                )
            if set(base_before) - set(base_with) != {"dc_input_inspector"}:
                failures.append(
                    f"_used_by(base): expected exactly dc_input_inspector to "
                    f"drop, got {base_before!r} -> {base_with!r}"
                )
        finally:
            probe.unlink(missing_ok=True)
        base_after = pa._used_by(base_rel, slot_usage)
        if base_after != base_before:
            failures.append(
                f"_used_by(base): not restored after removing the scoped copy: "
                f"{base_before!r} -> {base_after!r}"
            )

    for line in failures:
        print(f"FAIL {line}")
    if failures:
        return 1
    print(
        "OK prompts admin smoke test "
        "(build_tree + read_file + save_files + path-safety + 4 validators "
        "+ scoped-copy usage)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
