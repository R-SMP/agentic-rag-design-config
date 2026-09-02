"""Prompts hot-reload smoke test.

Verifies that ``agents.shared.prompts._build_slots`` and
``agents.shared.prompts._build_template`` re-read fragment files from
disk on every call, so an edit to a fragment .md takes effect on the
NEXT session's agent construction without a Python restart.  (This
mattered for the System Prompts UI, removed 2026-08-21; it matters
just as much now that fragments are edited as files, and it is what
lets the Sessions Queue switch prompt variants between runs inside
one process.)

Safe-by-construction: a temp directory mirrors the 4 source roots
with minimal fixture .md files; the test monkeypatches the path
constants in ``prompts.py`` to point at the tempdir; the real
fragments under ``DC_prompt_fragments/`` and
``agents/shared/prompt_fragments/`` are NEVER touched.

Run with:

    python extra_utilities/smoke_test_prompts_hot_reload.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import types
from pathlib import Path

# Bootstrap so the package import works when this file is run directly.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Pre-stub the ``agents`` package so its real ``__init__.py`` (which
# imports the langchain-dependent ``Orchestrator``) doesn't run.  This
# lets the test execute in local Python interpreters that lack
# ``langchain_core`` — only ``agents.shared.prompts`` is exercised here,
# and that module only needs ``agents.shared.routing`` +
# ``workflow_settings``, neither of which pulls langchain.  In
# environments where the real package is already loaded (production
# / Railway / Docker), ``setdefault`` is a no-op and the real package
# is used.
_agents_stub = types.ModuleType("agents")
_agents_stub.__path__ = [str(REPO_ROOT / "agents")]
sys.modules.setdefault("agents", _agents_stub)

from agents.shared import prompts  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

# Minimal .md content for every fragment that ``_build_slots`` reads.
# Each string is unique so the assertions below can spot ANY missing
# substitution.
_DC_CONFIG_FIXTURES = {
    "name.txt":                      "FixturePropeller",
    "domain_description.txt":        "fixture-domain-description",
    "parameter_count.txt":           "17",
    "structure.md":                  "[STRUCTURE]",
    "parameters.md":                 "[PARAMETERS]",
    "modelling_notes.md":            "[MODELLING_NOTES]",
    "qualitative_examples.md":       "[QUALITATIVE_EXAMPLES]",
    "visual_inspection_guide.md":    "[VISUAL_INSPECTION_GUIDE]",
    "capabilities_can.md":           "[CAPABILITIES_CAN]",
    "capabilities_cannot.md":        "[CAPABILITIES_CANNOT]",
    "output_file_locations.md":      "[OUTPUT_FILE_LOCATIONS]",
    "geometry_modification_rule.md": "[GEOMETRY_MODIFICATION_RULE]",
    "invalid_parameter_examples.md": "[INVALID_PARAMETER_EXAMPLES]",
    "hard_constraints_dc.md":        "[HARD_CONSTRAINTS_DC]",
}

_USER_INPUT_TYPES_FIXTURES = {
    "sketch_handling.md": "[SKETCH_HANDLING]",
    "sketch_notes.md":    "[SKETCH_NOTES]",
    # The fixture tree must carry EVERY fragment _build_slots() opens, or
    # this test dies on FileNotFoundError before asserting anything.  It had
    # drifted behind on THREE dicts at once.  Cross-check with the two
    # _read_*_fragment call sites in agents/shared/prompts.py when adding a
    # fragment; a new one is invisible to this test until it is listed here.
    "sketch_precision_examples.md": "[SKETCH_PRECISION_EXAMPLES]",
    "sketch_crop_example.md":       "[SKETCH_CROP_EXAMPLE]",
}

_TOOLS_CONFIG_FIXTURES = {
    "tool_inventory.md":             "[TOOL_INVENTORY]",
    "tool_caller_instructions.md":   "[TOOL_CALLER_INSTRUCTIONS]",
    "tool_caller_capabilities.md":   "[TOOL_CALLER_CAPABILITIES]",
    "agent_tools_overview.md":       "[AGENT_TOOLS_OVERVIEW]",
    "agent_tools_overview_brief.md": "[AGENT_TOOLS_OVERVIEW_BRIEF]",
    "hard_constraints_tools.md":     "[HARD_CONSTRAINTS_TOOLS]",
    "visualize_3d_model.md":         "[VISUALIZE_3D_MODEL]",
    "propose_attempt.md":            "[PROPOSE_ATTEMPT]",
    "database_search.md":            "[DATABASE_SEARCH]",
    "retrieve_user_inputs.md":       "[RETRIEVE_USER_INPUTS]",
    "retrieve_attempt.md":           "[RETRIEVE_ATTEMPT]",
    "blade_sections_visualizer.md":    "[BSV]",
    "blade_sections_visualizer_off.md": "[BSV_OFF]",
    "render_check_library/trimesh.md": "[RCL_TRIMESH]",
    "render_check_library/pyvista.md": "[RCL_PYVISTA]",
    "render_check_library/off.md":     "[RCL_OFF]",
}

_GENERIC_FIXTURES = {
    "generic_constraints.md":         "[GENERIC_CONSTRAINTS]",
    "routing_receptionist.md":        "[ROUTING_RECEPTIONIST]",
    "routing_orchestrator.md":        "[ROUTING_ORCHESTRATOR]",
    "pipeline_flow_planner_first.md": "[PIPELINE_FLOW_PF]",
    "pipeline_flow_uii_first.md":     "[PIPELINE_FLOW_UII]",
    "available_agents.md":            "[AVAILABLE_AGENTS]",
    "value_states.md":                 "[VALUE_STATES]",
}

# The stub agent's prompt.md references three $-slots so we can verify
# both round 1 (initial) and round 2 (after mutation) propagate.
_AGENT_PROMPT_MD = (
    "Stub agent for $domain_description with DC name $dc_name "
    "and $parameter_count parameters."
)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _write_fixtures(tmp_root: Path) -> None:
    """Write the fixture tree under ``tmp_root``."""
    dc_root      = tmp_root / "DC_prompt_fragments"
    dc_config    = dc_root / "dc_config"
    user_types   = dc_config / "user_input_types"
    tools_config = dc_root / "tools_config"
    generic      = tmp_root / "shared_prompt_fragments"
    agents_root  = tmp_root / "agents"
    stub_agent   = agents_root / "stub_agent"

    for d in (user_types, tools_config, generic, stub_agent):
        d.mkdir(parents=True)

    for name, body in _DC_CONFIG_FIXTURES.items():
        (dc_config / name).write_text(body, encoding="utf-8")
    for name, body in _USER_INPUT_TYPES_FIXTURES.items():
        (user_types / name).write_text(body, encoding="utf-8")
    for name, body in _TOOLS_CONFIG_FIXTURES.items():
        # Some fixture names carry a subdirectory (render_check_library/*.md),
        # so the parent must be created rather than assumed.
        dest = tools_config / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
    for name, body in _GENERIC_FIXTURES.items():
        (generic / name).write_text(body, encoding="utf-8")

    (stub_agent / "prompt.md").write_text(_AGENT_PROMPT_MD, encoding="utf-8")


def main() -> int:
    # Snapshot the live constants so we can restore them no matter
    # how the test exits.
    orig = {
        "DC_FRAGMENTS_DIR":     prompts.DC_FRAGMENTS_DIR,
        "DC_CONFIG_DIR":        prompts.DC_CONFIG_DIR,
        "TOOLS_CONFIG_DIR":     prompts.TOOLS_CONFIG_DIR,
        "GENERIC_FRAGMENTS_DIR": prompts.GENERIC_FRAGMENTS_DIR,
        "AGENTS_DIR":           prompts.AGENTS_DIR,
    }

    tmp_dir = Path(tempfile.mkdtemp(prefix="prompts_hot_reload_"))
    failures: list[str] = []
    try:
        _write_fixtures(tmp_dir)

        # Monkeypatch the path constants in prompts.py.
        prompts.DC_FRAGMENTS_DIR      = tmp_dir / "DC_prompt_fragments"
        prompts.DC_CONFIG_DIR         = tmp_dir / "DC_prompt_fragments" / "dc_config"
        prompts.TOOLS_CONFIG_DIR      = tmp_dir / "DC_prompt_fragments" / "tools_config"
        prompts.GENERIC_FRAGMENTS_DIR = tmp_dir / "shared_prompt_fragments"
        prompts.AGENTS_DIR            = tmp_dir / "agents"

        # ------- Round 1 — fixture content propagates --------------
        slots = prompts._build_slots()
        if slots["dc_name"] != "FixturePropeller":
            failures.append(
                f"R1 _build_slots: expected dc_name 'FixturePropeller', "
                f"got {slots['dc_name']!r}"
            )
        if slots["domain_description"] != "fixture-domain-description":
            failures.append(
                f"R1 _build_slots: expected domain_description "
                f"'fixture-domain-description', got "
                f"{slots['domain_description']!r}"
            )
        if slots["parameter_count"] != "17":
            failures.append(
                f"R1 _build_slots: expected parameter_count '17', "
                f"got {slots['parameter_count']!r}"
            )

        tpl = prompts._build_template("stub_agent")
        for needle in ("FixturePropeller", "fixture-domain-description", "17"):
            if needle not in tpl:
                failures.append(
                    f"R1 _build_template: missing fixture {needle!r}; "
                    f"got {tpl!r}"
                )

        # ------- Round 2 — mutate a fixture; assert disk-fresh ----
        (prompts.DC_CONFIG_DIR / "name.txt").write_text(
            "MutatedPropeller", encoding="utf-8",
        )
        slots2 = prompts._build_slots()
        if slots2["dc_name"] != "MutatedPropeller":
            failures.append(
                f"R2 _build_slots: expected dc_name 'MutatedPropeller' "
                f"after mutation, got {slots2['dc_name']!r}  "
                f"— hot reload is not reading disk fresh"
            )
        tpl2 = prompts._build_template("stub_agent")
        if "MutatedPropeller" not in tpl2:
            failures.append(
                f"R2 _build_template: expected new content after "
                f"fragment mutation, got {tpl2!r}"
            )
        if "FixturePropeller" in tpl2:
            failures.append(
                f"R2 _build_template: stale content survived a "
                f"fragment mutation, got {tpl2!r}"
            )

    finally:
        # Restore module constants and clean up the tempdir even on
        # exception.
        for name, val in orig.items():
            setattr(prompts, name, val)
        shutil.rmtree(tmp_dir, ignore_errors=True)

    for line in failures:
        print(f"FAIL {line}")
    if failures:
        return 1
    print("OK prompts hot-reload smoke test "
          "(_build_slots + _build_template both re-read disk fresh)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
