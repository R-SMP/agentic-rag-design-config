"""``read_user_queries`` — selected entries from ``user_query.txt``.

Historically defined in ``agents/planner/planner.py``.  The 7-agent
Planner no longer binds it (2026-08-22 prompt reduction §B3 — it binds
``read_user_inputs`` instead), but the 5-agent Conductor and the 3-agent
Architect still inherit this tool from their Planner merge, so it moved
here rather than being deleted.
"""

from langchain_core.tools import tool

from agents.shared.agent_activity import generic_tool
from config import USER_INPUTS_DIR

_QUERY_HEADER_PREFIX = "--- ["


def _parse_user_query_entries(text: str) -> list[str]:
    """Split ``user_query.txt`` content into individual entries."""
    entries: list[str] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if line.startswith(_QUERY_HEADER_PREFIX):
            if current is not None:
                entries.append("\n".join(current).strip())
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        entries.append("\n".join(current).strip())
    return [e for e in entries if e]


@tool
@generic_tool("Read user queries")
def read_user_queries(n: int = 1, from_start: bool = False) -> str:
    """Return selected entries from user_query.txt.

    ``n`` (int, ≥ 1): number of entries to return.
    ``from_start`` (bool, default False): when False return the latest
    ``n`` entries; when True return the first ``n`` (oldest) entries.

    Entries are returned in chronological order, each preceded by its
    original ``--- [timestamp] ---`` header.  Returns a short message
    if the file does not exist, is empty, or has no parsable entries.
    """
    try:
        n_int = int(n)
    except (TypeError, ValueError):
        return "Error: 'n' must be an integer >= 1."
    if n_int < 1:
        return "Error: 'n' must be >= 1."

    path = USER_INPUTS_DIR / "user_query.txt"
    if not path.exists():
        return f"user_query.txt not found at {path.resolve()}."
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Error reading user_query.txt: {exc}"

    entries = _parse_user_query_entries(content)
    if not entries:
        return "user_query.txt contains no parsable entries."

    selected = entries[:n_int] if from_start else entries[-n_int:]
    label = "first" if from_start else "latest"
    header = (
        f"Showing {len(selected)} of {len(entries)} entries "
        f"({label} {n_int} requested):"
    )
    return header + "\n\n" + "\n\n".join(selected)
