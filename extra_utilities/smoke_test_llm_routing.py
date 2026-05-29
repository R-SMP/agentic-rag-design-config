"""Smoke test for the LLM-routing read/write path.

Verifies:
  1. read_state() with empty/missing .env files returns sane defaults
     (mode='individual', shared=openai/gpt-5-mini, every agent shows
     source='shared' with empty overrides).
  2. write_updates() with mode='individual' and a per-agent override
     persists the override to agents/<agent>/.env without disturbing
     other lines (e.g. API key lines are preserved).
  3. read_state() after the write reflects override_provider /
     override_model and source='per-agent' for that agent only.
  4. write_updates() with mode='anthropic' rewrites LLM_ROUTING_MODE in
     settings.py and leaves per-agent override files on disk
     UNCHANGED (per-agent state is preserved, just ignored at
     resolution time).
  5. llm_provider._resolve_config honours mode='anthropic' — every
     agent is forced onto Anthropic with the shared MODEL_NAME, even
     the one with an OpenAI per-agent override.
  6. Flipping back to mode='individual' restores per-agent resolution.
  7. write_updates() with an empty per-agent override deletes the
     LLM_PROVIDER + MODEL_NAME lines from that agent's .env file
     while preserving other lines.
  8. write_updates() rejects malformed payloads (bad mode, partial
     override, unknown agent key).
  9. editor.write_updates rejects a direct write to LLM_ROUTING_MODE
     (only editor.write_internal may touch it).

The test isolates ALL on-disk side-effects under a tempdir so it can
be run from a dev checkout without trashing the real settings or
.env files.  Run from the project root:

    .venv/Scripts/python.exe extra_utilities/smoke_test_llm_routing.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _writeln(p: Path, content: str) -> None:
    p.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")


def _run() -> None:
    tmp_root = Path(tempfile.mkdtemp(prefix="llm_routing_smoke_"))
    try:
        # ---- Build an isolated mini-checkout under tmp_root ----------
        agents_dir = tmp_root / "agents"
        agents_dir.mkdir()
        (agents_dir / ".env").write_text("", encoding="utf-8")
        for agent_key in (
            "receptionist", "orchestrator", "user_input_inspector",
            "planner", "dc_input_creator", "dc_input_inspector",
            "dc_output_inspector", "tool_caller", "database_handler",
            "context_pruner",
        ):
            (agents_dir / agent_key).mkdir()

        # Seed shared/.env with an API key line so we can later prove
        # set_key did not destroy it.
        (agents_dir / ".env").write_text(
            "OPENAI_API_KEY=sk-keep-me\n", encoding="utf-8",
        )

        settings_path = tmp_root / "workflow_settings_settings.py"
        _writeln(settings_path, """
            # ===========================================================
            # 1.  Test settings
            # ===========================================================
            #
            # Valid values: True, False
            MESH_CHECKS: bool = False


            # ===========================================================
            # 12. LLM routing mode
            # ===========================================================
            #
            # Valid values: "individual" | "openai" | "anthropic" | "google"
            LLM_ROUTING_MODE: str = "individual"
        """)

        # ---- Import under-test modules and redirect their paths ------
        from agents.shared import llm_provider as _llm_provider
        from workflow_settings import editor as _editor
        from workflow_settings import llm_routing as _routing
        from workflow_settings import settings as _settings

        # Redirect file targets.
        _editor.SETTINGS_PATH = settings_path
        _routing.AGENTS_DIR = agents_dir
        _routing.SHARED_ENV_PATH = agents_dir / ".env"
        _llm_provider.AGENTS_DIR = agents_dir
        _llm_provider._SHARED_ENV_PATH = agents_dir / ".env"

        # Make the live ``workflow_settings.settings`` module mirror the
        # tempdir file so read_state pulls our LLM_ROUTING_MODE.
        _settings.LLM_ROUTING_MODE = "individual"

        # Stub os.environ so key-presence checks are predictable.
        env_stub = {
            "OPENAI_API_KEY": "sk-keep-me",
            "ANTHROPIC_API_KEY": "",
            "GOOGLE_API_KEY": "",
        }

        def _ge(name, default=""):
            return env_stub.get(name, os.environ.get(name, default))

        # ---- 1. Defaults --------------------------------------------------
        with patch.object(os, "getenv", _ge):
            state = _routing.read_state()
        assert state["mode"] == "individual", state["mode"]
        assert state["shared"]["provider"] == "openai", state["shared"]
        assert state["shared"]["model"] == "gpt-5-mini", state["shared"]
        prov_by_key = {p["key"]: p for p in state["providers"]}
        assert prov_by_key["openai"]["key_present"] is True
        assert prov_by_key["anthropic"]["key_present"] is False
        for a in state["agents"]:
            assert a["source"] == "shared", a
            assert a["override_provider"] == "", a
            assert a["override_model"] == "", a
        print("  [1] defaults OK")

        # ---- 2. Save an individual override for the receptionist ----------
        payload = {
            "mode": "individual",
            "shared": {"provider": "openai", "model": "gpt-5-mini"},
            "agents": [{"key": a["key"],
                        "override_provider":
                            "anthropic" if a["key"] == "receptionist" else "",
                        "override_model":
                            "claude-sonnet-4-5"
                            if a["key"] == "receptionist" else ""}
                       for a in state["agents"]],
        }
        with patch.object(os, "getenv", _ge):
            _routing.write_updates(payload)

        # Mirror the editor's write into the live module attribute (the
        # real flow does this via importlib.reload in _build_session;
        # we simulate it here).
        _settings.LLM_ROUTING_MODE = "individual"

        rec_env = (agents_dir / "receptionist" / ".env").read_text("utf-8")
        assert "LLM_PROVIDER=anthropic" in rec_env, rec_env
        assert "MODEL_NAME=claude-sonnet-4-5" in rec_env, rec_env

        # Shared file still has the seeded API key (per requirement #2).
        shared_env = (agents_dir / ".env").read_text("utf-8")
        assert "OPENAI_API_KEY=sk-keep-me" in shared_env, shared_env
        assert "LLM_PROVIDER=openai" in shared_env, shared_env
        assert "MODEL_NAME=gpt-5-mini" in shared_env, shared_env
        print("  [2] per-agent override write OK; shared keys preserved")

        # ---- 3. read_state reflects the override -------------------------
        env_stub["ANTHROPIC_API_KEY"] = "sk-ant-keep"
        with patch.object(os, "getenv", _ge):
            state2 = _routing.read_state()
        rec = next(a for a in state2["agents"] if a["key"] == "receptionist")
        assert rec["override_provider"] == "anthropic", rec
        assert rec["override_model"] == "claude-sonnet-4-5", rec
        assert rec["source"] == "per-agent", rec
        # No other agent should have flipped.
        other_sources = {a["source"] for a in state2["agents"]
                         if a["key"] != "receptionist"}
        assert other_sources == {"shared"}, other_sources
        print("  [3] read_state reflects override OK")

        # ---- 4. Switch to global mode='anthropic' ------------------------
        payload2 = {
            "mode": "anthropic",
            "shared": {"provider": "openai", "model": "gpt-5-mini"},
            "agents": [{"key": a["key"],
                        "override_provider": a["override_provider"],
                        "override_model": a["override_model"]}
                       for a in state2["agents"]],
        }
        with patch.object(os, "getenv", _ge):
            _routing.write_updates(payload2)
        # The editor.write_internal call rewrote LLM_ROUTING_MODE on disk.
        # Reflect it into the live module (the real flow uses reload).
        _settings.LLM_ROUTING_MODE = "anthropic"

        settings_text = settings_path.read_text("utf-8")
        assert 'LLM_ROUTING_MODE: str = "anthropic"' in settings_text, settings_text
        # Per-agent override file is unchanged on disk.
        rec_env2 = (agents_dir / "receptionist" / ".env").read_text("utf-8")
        assert "LLM_PROVIDER=anthropic" in rec_env2, rec_env2
        assert "MODEL_NAME=claude-sonnet-4-5" in rec_env2, rec_env2
        print("  [4] global mode switch + per-agent preservation OK")

        # ---- 5. _resolve_config honours global mode ----------------------
        # Put an OpenAI override on planner; with global=anthropic, planner
        # must STILL resolve to anthropic.
        (agents_dir / "planner" / ".env").write_text(
            "LLM_PROVIDER=openai\nMODEL_NAME=gpt-5-mini\nOPENAI_API_KEY=sk-plan\n",
            encoding="utf-8",
        )
        # Shared agents/.env needs an Anthropic key for the global override
        # resolution to succeed.
        shared_env_now = (agents_dir / ".env").read_text("utf-8")
        if "ANTHROPIC_API_KEY" not in shared_env_now:
            with open(agents_dir / ".env", "a", encoding="utf-8") as fh:
                fh.write("ANTHROPIC_API_KEY=sk-ant-keep\n")
        env_stub["ANTHROPIC_API_KEY"] = "sk-ant-keep"

        with patch.object(os, "getenv", _ge):
            provider, model, api_key = _llm_provider._resolve_config("planner")
        assert provider == "anthropic", provider
        assert api_key == "sk-ant-keep", api_key
        print("  [5] global override forces anthropic for planner OK")

        # ---- 6. Flip back to individual; planner returns to openai -------
        payload3 = dict(payload2)
        payload3["mode"] = "individual"
        with patch.object(os, "getenv", _ge):
            _routing.write_updates(payload3)
        _settings.LLM_ROUTING_MODE = "individual"
        with patch.object(os, "getenv", _ge):
            provider, _, _ = _llm_provider._resolve_config("planner")
        assert provider == "openai", provider
        print("  [6] flip back to individual restores per-agent OK")

        # ---- 7. Clear receptionist override --------------------------
        # Seed the rec .env with an unrelated line to prove preservation.
        rec_path = agents_dir / "receptionist" / ".env"
        existing = rec_path.read_text("utf-8")
        rec_path.write_text(existing + "ANTHROPIC_API_KEY=sk-rec\n",
                            encoding="utf-8")

        payload4 = {
            "mode": "individual",
            "shared": {"provider": "openai", "model": "gpt-5-mini"},
            "agents": [{"key": a["key"],
                        "override_provider":
                            "" if a["key"] == "receptionist"
                            else a["override_provider"],
                        "override_model":
                            "" if a["key"] == "receptionist"
                            else a["override_model"]}
                       for a in state2["agents"]],
        }
        with patch.object(os, "getenv", _ge):
            _routing.write_updates(payload4)
        rec_env3 = rec_path.read_text("utf-8")
        assert "LLM_PROVIDER" not in rec_env3, rec_env3
        assert "MODEL_NAME" not in rec_env3, rec_env3
        assert "ANTHROPIC_API_KEY=sk-rec" in rec_env3, rec_env3
        print("  [7] clearing override preserves other .env lines OK")

        # ---- 8. Reject malformed payloads ----------------------------
        for bad in (
            {"mode": "purple", "shared": {"provider": "openai", "model": "x"},
             "agents": []},  # bad mode
            {"mode": "individual",
             "shared": {"provider": "openai", "model": ""},
             "agents": []},  # empty shared model
            {"mode": "individual",
             "shared": {"provider": "openai", "model": "x"},
             "agents": [{"key": "receptionist",
                         "override_provider": "openai",
                         "override_model": ""}]},  # partial override
            {"mode": "individual",
             "shared": {"provider": "openai", "model": "x"},
             "agents": [{"key": "made_up_agent",
                         "override_provider": "openai",
                         "override_model": "gpt-x"}]},  # unknown agent
        ):
            try:
                with patch.object(os, "getenv", _ge):
                    _routing.write_updates(bad)
            except _routing.RoutingError:
                pass
            else:
                raise AssertionError(f"should have rejected: {bad!r}")
        print("  [8] malformed payloads rejected OK")

        # ---- 9. editor.write_updates rejects LLM_ROUTING_MODE --------
        try:
            _editor.write_updates({"LLM_ROUTING_MODE": "openai"})
        except _editor.SettingsError:
            pass
        else:
            raise AssertionError(
                "editor.write_updates should reject LLM_ROUTING_MODE"
            )
        # And confirm write_internal allows it.
        _editor.write_internal({"LLM_ROUTING_MODE": "google"})
        s = settings_path.read_text("utf-8")
        assert 'LLM_ROUTING_MODE: str = "google"' in s, s
        print("  [9] hide-list enforced; write_internal bypass works OK")

    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    _run()
    print("\nllm_routing smoke test: ALL CASES PASSED")
