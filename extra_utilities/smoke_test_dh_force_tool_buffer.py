"""Smoke test — the DH's forced-tool turns leave NO dangling function_call.

Regression guard for the ID1484_20260908_163919 save, which wrote ZERO
interview answers.  Its DH log shows the same OpenAI 400 on every single
call after the batch plan::

    No tool output found for function call call_UB7T15gm4FVEr5MspdpfaU3V.

``_force_tool_args`` appended the AIMessage carrying the forced call and
returned the args straight to Python, never emitting a ToolMessage for
it.  ``self.messages`` grows monotonically across a save and is never
re-seeded (it is the DH's cached prefix), so that one unanswered call
sat in the prefix for the REST OF THE SAVE.  ``/v1/responses`` rejects a
dangling ``function_call`` outright, so every later DH call died: no
questions written, no batch decisions, every row SKIPPED.
chat/completions tolerated it, which is why this only surfaced after the
endpoint move.

``langchain_core`` is not importable in every dev environment, so this
lifts the SHIPPED method text out of ``database_handler.py`` verbatim and
executes it against stubs.  It exercises the real code path rather than a
paraphrase of it, and it is stdlib-only.

Run:
    python extra_utilities/smoke_test_dh_force_tool_buffer.py
"""

from __future__ import annotations

import re
import sys
import textwrap
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DH_SOURCE = REPO_ROOT / "agents" / "database_handler" / "database_handler.py"

# The id from the real failing save — kept verbatim so a future reader can
# grep it straight back to the log that motivated this test.
ID1484_CALL_ID = "call_UB7T15gm4FVEr5MspdpfaU3V"


# ----------------------------------------------------------------------
# Minimal message stubs.  Only the attributes _force_tool_args touches.
# ----------------------------------------------------------------------
class ToolMessage:
    def __init__(self, content, tool_call_id, name):
        self.content = content
        self.tool_call_id = tool_call_id
        self.name = name


class HumanMessage:
    def __init__(self, content):
        self.content = content


class AIMessage:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


def _lift_method(source_path: Path) -> str:
    """Return the text of _force_tool_args, dedented to module level."""
    src = source_path.read_text(encoding="utf-8")
    match = re.search(
        r"\n    def _force_tool_args\(.*?\n        return None\n", src, re.S,
    )
    if match is None:
        raise AssertionError(
            f"could not locate _force_tool_args in {source_path}. "
            f"If the method was renamed or its final 'return None' changed, "
            f"update this test — do not delete it."
        )
    return textwrap.dedent(match.group(0))


def _run_case(method_src: str, call_ids: list[str], label: str) -> bool:
    """Drive one forced-tool turn; assert every call it emitted is answered."""
    def _fake_response(*_args, **_kwargs):
        return AIMessage([
            {"name": "submit_batch_plan", "args": {"groups": []},
             "id": cid, "type": "tool_call"}
            for cid in call_ids
        ])

    namespace: dict = {
        "HumanMessage": HumanMessage,
        "ToolMessage": ToolMessage,
        "logger": types.SimpleNamespace(warning=lambda *a, **k: None),
        "invoke_with_retry": _fake_response,
        "make_system_message": lambda *a, **k: "sysmsg",
        "history_cache_control": lambda *a, **k: None,
    }
    exec("from __future__ import annotations\n" + method_src, namespace)

    handler = types.SimpleNamespace(
        base_llm=types.SimpleNamespace(
            bind_tools=lambda tools, tool_choice: "bound",
        ),
        messages=[],
        system_prompt="sys",
        provider="openai",
    )
    args = namespace["_force_tool_args"](
        handler, object(), "submit_batch_plan", "instruction", "DH-plan",
    )

    emitted: set[str] = set()
    answered: set[str] = set()
    for msg in handler.messages:
        for call in (getattr(msg, "tool_calls", None) or []):
            emitted.add(call["id"])
        if isinstance(msg, ToolMessage):
            answered.add(msg.tool_call_id)

    orphans = emitted - answered
    ok = args is not None and not orphans
    print(f"{'PASS' if ok else 'FAIL'}  {label}")
    print(f"        emitted  = {sorted(emitted)}")
    print(f"        answered = {sorted(answered)}")
    print(f"        orphans  = {sorted(orphans) or 'none'}"
          f"   args_returned = {args is not None}")
    return ok


def main() -> int:
    print(f"Lifting _force_tool_args from {DH_SOURCE.name}\n")
    method_src = _lift_method(DH_SOURCE)

    all_ok = True
    all_ok &= _run_case(
        method_src, [ID1484_CALL_ID],
        "a single forced call is answered (the exact ID1484 shape)",
    )
    print()
    all_ok &= _run_case(
        method_src, ["call_a", "call_b"],
        "MULTIPLE forced calls in one response are ALL answered",
    )

    print("\nALL PASS" if all_ok else "\nFAILURES")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
