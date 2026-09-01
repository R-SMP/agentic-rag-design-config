"""Pure formatting helpers shared by every topology's hub.

Lifted out of ``agents/orchestrator/orchestrator.py`` (2026-08-31) when the
topology-5 hub was added: both hubs need them, and copying ~90 lines into a
second hub would be a fork of live code -- the failure mode the reduced-agent
build order warns about.  ``orchestrator.py`` re-imports them, so
``from agents.orchestrator.orchestrator import _first_line, ...`` keeps
working for the Architect and any other existing caller.

Nothing here touches an agent, a session or a setting: they are string
formatters, which is why they are safe to share across topologies.
"""

from datetime import datetime


# ---------------------------------------------------------------------------
# Limit-surfacing helpers
# ---------------------------------------------------------------------------

def _first_line(text: str, limit: int = 180) -> str:
    """Return the first non-empty line of *text*, truncated to *limit*."""
    if not isinstance(text, str):
        text = str(text)
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:limit] + ("..." if len(line) > limit else "")
    return ""


def _truncate(text: str, limit: int) -> str:
    if not isinstance(text, str):
        text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[truncated]"


def _last_text_message(agent) -> str:
    """Return the most recent textual content produced by *agent*."""
    messages = getattr(agent, "messages", None) or []
    for msg in reversed(messages):
        content = getattr(msg, "content", "")
        rendered = _format_message_content(content).strip()
        if rendered:
            return rendered
    return ""


# ---------------------------------------------------------------------------
# History-dump helpers
# ---------------------------------------------------------------------------

def _format_message_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        rendered = []
        for block in content:
            if isinstance(block, dict):
                btype = block.get("type", "?")
                if btype == "text":
                    rendered.append(block.get("text", ""))
                elif btype in {"image", "image_url"}:
                    rendered.append(f"<{btype} block omitted>")
                else:
                    rendered.append(f"<{btype} block: {list(block.keys())}>")
            else:
                rendered.append(str(block))
        return "\n".join(rendered)
    return str(content)


def _format_agent_history(agent_name: str, messages: list, sys_prompt) -> str:
    lines: list = []
    lines.append(f"=== History for agent: {agent_name} ===")
    lines.append(f"Dumped at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Message count: {len(messages)}")
    lines.append("")

    if sys_prompt:
        lines.append("--- System Prompt ---")
        lines.append(str(sys_prompt))
        lines.append("")

    for i, msg in enumerate(messages, start=1):
        msg_type = type(msg).__name__
        lines.append(f"=== Message {i} : {msg_type} ===")
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                tc_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "?")
                tc_args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                lines.append(f"[tool_call] {tc_name}  args={tc_args}")
        tm_name = getattr(msg, "name", None)
        tm_id = getattr(msg, "tool_call_id", None)
        # Disambiguate the label based on the message type:
        #   * ToolMessage (has tool_call_id) → "[tool_result] name=... id=..."
        #   * Any other message with name= set (e.g. a HumanMessage
        #     appended by the Orchestrator at end-of-session feedback
        #     round) → "[from <name>]" — NOT "[tool_result]", which
        #     was misleading.
        if tm_id:
            lines.append(f"[tool_result] name={tm_name}  id={tm_id}")
        elif tm_name:
            lines.append(f"[from {tm_name}]")

        content = _format_message_content(getattr(msg, "content", ""))
        if content:
            lines.append(content)
        lines.append("")

    return "\n".join(lines)
