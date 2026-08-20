"""Dispatcher for the retrieve_* tool calls (Phase 5B).

Parallel to ``dispatch_user_inputs_tool`` in ``user_inputs_tool.py``:
each chain agent's run loop calls
``dispatch_retrieve_tool(agent, tc, agent_key)`` after exhausting
its other tool-call branches.  The dispatcher inspects
``tc['name']`` and, when it matches one of the retrieve_* tools,
invokes the tool's real ``_run_retrieve_*`` function, appends a
``ToolMessage`` carrying the XML body to ``agent.messages``, and
(when image bytes are present) buffers image content blocks for
the next ``HumanMessage`` via ``append_pending_images``.

The split — public ``@tool``-decorated stub returning ``""`` plus a
private ``_run_retrieve_*`` doing the real work plus this
dispatcher routing the ``ToolMessage`` — mirrors the existing
``view_images`` pattern, so each chain agent sees one tool
call producing two attached pieces of evidence (XML text + image
content blocks) in its next view.

Lazy imports
------------
The tool modules under ``tools/retrieve_user_inputs/`` and
``tools/retrieve_attempt/`` are imported lazily inside each
handler so this dispatcher can ship before the tool modules
exist (incremental Phase 5B/5C delivery).  An ImportError surfaces
as a ToolMessage explaining the situation; the agent's run loop is
not broken.
"""

from __future__ import annotations

import logging

from langchain_core.messages import ToolMessage

from agents.shared.file_utils import append_pending_images
from agents.shared.routing_tools import log_tool_call

logger = logging.getLogger("propeller_agent")


def _emit_error_tool_message(
    agent, tc: dict, agent_key: str, summary: str
) -> None:
    """Append an error ToolMessage and write the matching log line."""
    log_tool_call(agent_key, tc["name"], tc.get("args"), summary)
    agent.messages.append(ToolMessage(
        content=summary,
        tool_call_id=tc["id"],
        name=tc["name"],
    ))


def _handle_retrieve_user_inputs(agent, tc: dict, agent_key: str) -> None:
    """Dispatcher handler for ``retrieve_user_inputs`` calls.

    Looks up the real implementation in
    ``tools.retrieve_user_inputs.retrieve_user_inputs``; lazy import
    so this dispatcher loads independently of the tool module's
    landing time.
    """
    try:
        from tools.retrieve_user_inputs.retrieve_user_inputs import (
            _run_retrieve_user_inputs,
        )
    except ImportError as exc:
        _emit_error_tool_message(
            agent, tc, agent_key,
            f"Error: retrieve_user_inputs tool module is not yet "
            f"available ({type(exc).__name__}: {exc}).  This is a "
            f"deploy-state problem, not a tool-call problem — alert "
            f"the operator.",
        )
        return

    args = tc.get("args", {}) or {}
    raw_session_ids = args.get("sessions_ID_list")
    if isinstance(raw_session_ids, str):
        raw_session_ids = [raw_session_ids]
    if not isinstance(raw_session_ids, list) or not raw_session_ids:
        _emit_error_tool_message(
            agent, tc, agent_key,
            "Error: 'sessions_ID_list' must be a non-empty list of "
            "session_id strings.",
        )
        return
    images_flag = bool(args.get("images_flag", False))

    try:
        xml, image_blocks, image_paths = _run_retrieve_user_inputs(
            caller_agent=agent_key,
            session_ids=[str(sid) for sid in raw_session_ids],
            images_flag=images_flag,
            provider=getattr(agent, "provider", "openai"),
        )
    except Exception as exc:
        logger.warning(
            f"[retrieve_user_inputs]  unhandled error for {agent_key}: "
            f"{type(exc).__name__}: {exc}",
            exc_info=True,
        )
        _emit_error_tool_message(
            agent, tc, agent_key,
            f"Error: retrieve_user_inputs raised "
            f"{type(exc).__name__}: {exc}.",
        )
        return

    log_tool_call(
        agent_key, tc["name"], tc.get("args"),
        # log a short head of the XML so the trace is greppable
        # without paying for the full body in every log line
        (xml[:200] + "...") if len(xml) > 200 else xml,
    )
    agent.messages.append(ToolMessage(
        content=xml,
        tool_call_id=tc["id"],
        name=tc["name"],
    ))
    if image_blocks:
        # Buffer images for the next HumanMessage so the
        # tool_use → tool_result contiguity invariant is preserved
        # when this tool call was batched alongside others.  Same
        # pattern as view_images.
        append_pending_images(agent, image_blocks, image_paths)


def _handle_retrieve_attempt(agent, tc: dict, agent_key: str) -> None:
    """Dispatcher handler for ``retrieve_attempt`` calls.

    Same shape as ``_handle_retrieve_user_inputs`` but with the
    int-coerced global attempt id list as input.  Lazy import of
    the tool module so 5C can land independently.
    """
    try:
        from tools.retrieve_attempt.retrieve_attempt import (
            _run_retrieve_attempt,
        )
    except ImportError as exc:
        _emit_error_tool_message(
            agent, tc, agent_key,
            f"Error: retrieve_attempt tool module is not yet "
            f"available ({type(exc).__name__}: {exc}).  This is a "
            f"deploy-state problem, not a tool-call problem — alert "
            f"the operator.",
        )
        return

    args = tc.get("args", {}) or {}
    raw_attempt_ids = args.get("attempts_ID_list")
    if isinstance(raw_attempt_ids, (str, int)):
        raw_attempt_ids = [raw_attempt_ids]
    if not isinstance(raw_attempt_ids, list) or not raw_attempt_ids:
        _emit_error_tool_message(
            agent, tc, agent_key,
            "Error: 'attempts_ID_list' must be a non-empty list of "
            "integer global attempt ids (BIGSERIAL "
            "dc_attempts.attempt_id values from Postgres).",
        )
        return
    try:
        global_ids = [int(aid) for aid in raw_attempt_ids]
    except (TypeError, ValueError):
        _emit_error_tool_message(
            agent, tc, agent_key,
            f"Error: every entry in 'attempts_ID_list' must be an "
            f"integer global attempt id; got {raw_attempt_ids!r}.",
        )
        return
    images_flag = bool(args.get("images_flag", False))

    try:
        xml, image_blocks, image_paths = _run_retrieve_attempt(
            caller_agent=agent_key,
            global_attempt_ids=global_ids,
            images_flag=images_flag,
            provider=getattr(agent, "provider", "openai"),
        )
    except Exception as exc:
        logger.warning(
            f"[retrieve_attempt]  unhandled error for {agent_key}: "
            f"{type(exc).__name__}: {exc}",
            exc_info=True,
        )
        _emit_error_tool_message(
            agent, tc, agent_key,
            f"Error: retrieve_attempt raised "
            f"{type(exc).__name__}: {exc}.",
        )
        return

    log_tool_call(
        agent_key, tc["name"], tc.get("args"),
        (xml[:200] + "...") if len(xml) > 200 else xml,
    )
    agent.messages.append(ToolMessage(
        content=xml,
        tool_call_id=tc["id"],
        name=tc["name"],
    ))
    if image_blocks:
        append_pending_images(agent, image_blocks, image_paths)


_HANDLERS = {
    "retrieve_user_inputs": _handle_retrieve_user_inputs,
    "retrieve_attempt":     _handle_retrieve_attempt,
}

RETRIEVE_TOOL_NAMES = frozenset(_HANDLERS.keys())


def dispatch_retrieve_tool(agent, tc: dict, agent_key: str) -> bool:
    """If *tc* calls one of the retrieve_* tools, handle it and return True.

    Mirrors :func:`agents.shared.user_inputs_tool.dispatch_user_inputs_tool`
    so each chain agent's run loop can add one one-liner to route
    the call to its correct handler.  Returns False (no side
    effects) when the tool name is not one of the retrieve_* tools,
    so the agent's run loop can fall through to its other branches.
    """
    name = tc.get("name")
    handler = _HANDLERS.get(name)
    if handler is None:
        return False
    handler(agent, tc, agent_key)
    return True
