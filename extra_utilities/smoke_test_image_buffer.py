"""Smoke-test for the image-buffer-and-flush mechanism.

Exercises the contiguity-preservation behaviour added to fix TODO #1:
when an LLM emits multiple tool_calls in one AIMessage and at least
one of them loads images, the message history must still satisfy the
provider's tool_use -> tool_result contiguity rule.

Run from the project root:
    .venv/Scripts/python.exe extra_utilities/smoke_test_image_buffer.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.shared.file_utils import (
    append_pending_images,
    flush_pending_image_blocks,
)


class FakeAgent:
    def __init__(self):
        self.messages = []
        self.provider = "anthropic"


def shape(msgs):
    return [type(m).__name__ for m in msgs]


# ---------------------------------------------------------------------
# Test 1: dual parallel tool call (load_input_images + read_input_text)
# ---------------------------------------------------------------------
print("Test 1: dual parallel tool call (load_input_images + read_input_text)")
agent = FakeAgent()

ai_msg = AIMessage(
    content="",
    tool_calls=[
        {"id": "t_load", "name": "load_input_images", "args": {"paths": ["/x/r.png"]}},
        {"id": "t_read", "name": "read_input_text",   "args": {"path":  "/x/notes.txt"}},
    ],
)
agent.messages.append(ai_msg)

# Tool 1: load_input_images appends ToolMessage AND buffers image blocks
agent.messages.append(ToolMessage(
    content="Loaded 1 image.",
    tool_call_id="t_load",
    name="load_input_images",
))
fake_image_block = {
    "type": "image",
    "source": {"type": "base64", "media_type": "image/png", "data": "..."},
}
append_pending_images(agent, [fake_image_block], ["/x/r.png"])
print(f"  After load tool: pending buffer = {len(agent._pending_image_blocks)} block(s)")
print(f"                   messages so far = {shape(agent.messages)}")

# Tool 2: read_input_text appends ToolMessage only
agent.messages.append(ToolMessage(
    content="Note contents...",
    tool_call_id="t_read",
    name="read_input_text",
))
print(f"  After read tool: pending buffer = {len(agent._pending_image_blocks)} block(s)")
print(f"                   messages so far = {shape(agent.messages)}")

# Run-loop flushes after the for-loop
n_flushed = flush_pending_image_blocks(agent)
print(f"  flush returned: {n_flushed} block(s)")
print(f"  After flush:    pending buffer = {len(agent._pending_image_blocks)} block(s)")
print(f"                  messages so far = {shape(agent.messages)}")

expected = ["AIMessage", "ToolMessage", "ToolMessage", "HumanMessage"]
got = shape(agent.messages)
assert got == expected, f"BAD shape: got {got}, expected {expected}"
print("  PASS — AIMessage, ToolMessage, ToolMessage, HumanMessage")

final = agent.messages[-1]
assert isinstance(final, HumanMessage)
content = final.content
assert isinstance(content, list)
types = [b.get("type") for b in content]
print(f"  Final HumanMessage content block types: {types}")
assert content[0]["type"] == "text" and "Loaded image" in content[0]["text"]
assert content[1]["type"] == "image"
print("  PASS — paired path-text + image block intact")
print()

# ---------------------------------------------------------------------
# Test 2: empty-flush is a no-op
# ---------------------------------------------------------------------
print("Test 2: empty-flush is a no-op")
agent2 = FakeAgent()
agent2.messages.append(AIMessage(content="", tool_calls=[]))
agent2.messages.append(ToolMessage(content="x", tool_call_id="abc", name="read_input_text"))

before = shape(agent2.messages)
n = flush_pending_image_blocks(agent2)
after = shape(agent2.messages)
assert n == 0
assert before == after
print(f"  flush returned {n}, message shape unchanged: {after}")
print("  PASS")
print()

# ---------------------------------------------------------------------
# Test 3: three parallel tool calls, two of them image-loading
# ---------------------------------------------------------------------
print("Test 3: 3 parallel tool calls (2 image-loading + 1 utility)")
agent3 = FakeAgent()
ai_msg = AIMessage(
    content="",
    tool_calls=[
        {"id": "A", "name": "load_input_images",  "args": {"paths": ["/x/a.png"]}},
        {"id": "B", "name": "list_input_files",   "args": {}},
        {"id": "C", "name": "load_render_images", "args": {"paths": ["/x/b.png", "/x/c.png"]}},
    ],
)
agent3.messages.append(ai_msg)

agent3.messages.append(ToolMessage(content="A done", tool_call_id="A", name="load_input_images"))
append_pending_images(agent3, [{"type": "image", "source": {}}], ["/x/a.png"])

agent3.messages.append(ToolMessage(content="B done", tool_call_id="B", name="list_input_files"))

agent3.messages.append(ToolMessage(content="C done", tool_call_id="C", name="load_render_images"))
append_pending_images(
    agent3,
    [{"type": "image", "source": {}}, {"type": "image", "source": {}}],
    ["/x/b.png", "/x/c.png"],
)

flush_pending_image_blocks(agent3)

expected3 = ["AIMessage", "ToolMessage", "ToolMessage", "ToolMessage", "HumanMessage"]
got3 = shape(agent3.messages)
assert got3 == expected3, f"BAD shape: got {got3}, expected {expected3}"

final3_content = agent3.messages[-1].content
# 3 images -> 6 content blocks (text+image alternating)
assert len(final3_content) == 6
print(f"  Final shape: {got3}")
print(f"  Final HumanMessage has {len(final3_content)} content blocks (3 images * 2 = 6)")
print("  PASS")
print()

# ---------------------------------------------------------------------
# Test 4: two image-loading calls in one batch (the exact DCOI failure)
# ---------------------------------------------------------------------
print("Test 4: load_render_images + load_input_images in one AIMessage")
print("        (the exact shape that 400'd in the run we just analysed)")
agent4 = FakeAgent()
ai_msg = AIMessage(
    content="",
    tool_calls=[
        {"id": "R", "name": "load_render_images", "args": {"paths": ["/r/iso.png"]}},
        {"id": "I", "name": "load_input_images",  "args": {"paths": ["/i/ref.png"]}},
    ],
)
agent4.messages.append(ai_msg)

# render-load handler: ToolMessage + buffer
agent4.messages.append(ToolMessage(content="loaded 1 render", tool_call_id="R", name="load_render_images"))
append_pending_images(agent4, [{"type": "image", "source": {}}], ["/r/iso.png"])

# input-load handler: ToolMessage + buffer
agent4.messages.append(ToolMessage(content="loaded 1 input", tool_call_id="I", name="load_input_images"))
append_pending_images(agent4, [{"type": "image", "source": {}}], ["/i/ref.png"])

flush_pending_image_blocks(agent4)

expected4 = ["AIMessage", "ToolMessage", "ToolMessage", "HumanMessage"]
got4 = shape(agent4.messages)
assert got4 == expected4, f"BAD shape: got {got4}, expected {expected4}"
final4_content = agent4.messages[-1].content
# 2 images -> 4 content blocks
assert len(final4_content) == 4
# Both paths in the path-text labels
text_blocks = [b for b in final4_content if b.get("type") == "text"]
assert any("/r/iso.png" in b.get("text", "") for b in text_blocks)
assert any("/i/ref.png" in b.get("text", "") for b in text_blocks)
print(f"  Final shape: {got4}")
print(f"  Final HumanMessage has 2 image blocks + 2 path-text blocks (correct order)")
print("  PASS — this is the exact failure mode that 400'd before; now resolved")
print()

print("All buffer-and-flush smoke tests passed.")
