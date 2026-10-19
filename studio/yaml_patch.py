"""Change values in a YAML file without rewriting it (MAS-blueprint P6c).

A tool's ``tool.yaml`` is commented, hand-laid-out YAML; PyYAML can read it
but would drop every comment if it wrote it back.  :func:`patch` changes only
the values that differ: it finds each one's exact place with PyYAML's own
node positions (``yaml.compose``), writes the new value there -- a one-line
value as YAML writes it, a multi-line text as a ``|`` block -- adds a key
that is missing at the end of its mapping, or takes one out.  Every other
character of the file stays as it was.

A value put back to what it was when the Studio opened is written back with
its OPENED text (the same place in the opened file), so a change and its
Undo leave the file byte for byte as it was.  The result is read back and
must equal what was asked; :class:`PatchError` otherwise (the Studio then
points to the text tab).
"""

from __future__ import annotations

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode


class PatchError(ValueError):
    """The change cannot be written into the file's own layout."""


# ---------------------------------------------------------------------------
# writing one value
# ---------------------------------------------------------------------------

def inline(value) -> str:
    """*value* on one line, as YAML writes it inside a ``[...]``."""
    s = yaml.safe_dump([value], default_flow_style=True, allow_unicode=True,
                       width=10 ** 9, sort_keys=False).strip()
    if not (s.startswith("[") and s.endswith("]")):
        raise PatchError(f"cannot write {value!r} on one line")
    return s[1:-1]


def _literal_ok(text: str) -> bool:
    lines = text.rstrip("\n").split("\n")
    first = next((ln for ln in lines if ln), "")
    return (not first.startswith((" ", "\t")) and "\t" not in text
            and all(ln == ln.rstrip(" ") for ln in lines)
            and not text.endswith("\n\n"))


def literal(text: str, indent: int) -> str:
    """A multi-line text as a ``|`` block whose lines start at *indent*."""
    body = text[:-1] if text.endswith("\n") else text
    head = "|" if text.endswith("\n") else "|-"
    pad = " " * indent
    return head + "".join("\n" + (pad + ln if ln else "") for ln in body.split("\n"))


def block(value, indent: int) -> str:
    """A list or mapping as block YAML on the lines after its key (each line
    starting at *indent*), lists of plain values and small mappings in
    flow style, as the manifests write them."""
    out = yaml.safe_dump(value, default_flow_style=None, allow_unicode=True,
                         width=100, sort_keys=False).rstrip("\n")
    return "".join("\n" + " " * indent + ln for ln in out.split("\n"))


def _core_end(text: str, start: int, end: int) -> int:
    """The end of a node's own characters: a block node's range also takes
    the line breaks and blank lines after it."""
    seg = text[start:end]
    return start + len(seg.rstrip(" \n"))


# ---------------------------------------------------------------------------
# finding nodes
# ---------------------------------------------------------------------------

def _pairs(node: MappingNode) -> dict:
    return {k.value: (k, v) for k, v in node.value if isinstance(k, ScalarNode)}


def node_at(root, path):
    """The node at *path* (keys and list indexes), or None."""
    node = root
    for step in path:
        if isinstance(node, MappingNode) and isinstance(step, str):
            hit = _pairs(node).get(step)
            node = hit[1] if hit else None
        elif isinstance(node, SequenceNode) and isinstance(step, int) and 0 <= step < len(node.value):
            node = node.value[step]
        else:
            return None
        if node is None:
            return None
    return node


def _value_at(data, path):
    for step in path:
        if isinstance(data, dict) and step in data:
            data = data[step]
        elif isinstance(data, list) and isinstance(step, int) and 0 <= step < len(data):
            data = data[step]
        else:
            raise KeyError(step)
    return data


# ---------------------------------------------------------------------------
# the patch
# ---------------------------------------------------------------------------

def patch(text: str, desired, opened_text: str | None = None) -> str:
    """*text* (LF) with its values changed to *desired* (the whole file as
    plain data).  Raises PatchError when the result does not read back as
    *desired*."""
    try:
        cur = yaml.safe_load(text)
        root = yaml.compose(text)
    except yaml.YAMLError as exc:
        raise PatchError(f"the file is not valid YAML: {exc}") from None
    if cur == desired:
        return text
    opened = opened_root = None
    if opened_text is not None:
        try:
            opened, opened_root = yaml.safe_load(opened_text), yaml.compose(opened_text)
        except yaml.YAMLError:
            opened = opened_root = None
    edits: list[tuple[int, int, str]] = []

    def from_opened(path, want, flow: bool):
        """The opened text of the value at *path*, if it was *want* then."""
        if opened_root is None:
            return None
        try:
            if _value_at(opened, path) != want:
                return None
        except KeyError:
            return None
        o = node_at(opened_root, path)
        if o is None:
            return None
        seg = opened_text[o.start_mark.index:_core_end(opened_text, o.start_mark.index, o.end_mark.index)]
        if flow and "\n" in seg:
            return None
        return seg

    def render(want, flow: bool, indent: int, path) -> str:
        """The text of a value written where a value of the given context starts."""
        seg = from_opened(path, want, flow)
        if seg is not None:
            if not flow and isinstance(want, (dict, list)) and want and not seg.startswith(("[", "{")):
                return "\n" + " " * indent + seg if not seg.startswith("\n") else seg
            return seg
        if isinstance(want, str) and "\n" in want and not flow and _literal_ok(want):
            return literal(want, indent)
        if isinstance(want, (dict, list)) and want and not flow and any(
                isinstance(x, (dict, list)) for x in (want.values() if isinstance(want, dict) else want)):
            return block(want, indent)
        return inline(want)

    def replace(node, want, flow: bool, key_col: int, path, key_node=None):
        s = node.start_mark.index
        e = _core_end(text, s, node.end_mark.index)
        new = render(want, flow, key_col + 2, path)
        if isinstance(node, (MappingNode, SequenceNode)) and not node.flow_style and node.value:
            if new.startswith("\n"):
                # block for block: it starts where the first entry starts (any
                # comment lines above it stay), so without its first indent
                new = new.lstrip("\n")
                new = new[len(new) - len(new.lstrip(" ")):]
            else:
                # one value for a block: back on the key's line, after its colon
                if key_node is None:
                    raise PatchError(f"cannot write {'.'.join(map(str, path))} on one line")
                s = text.index(":", key_node.end_mark.index) + 1
                new = " " + new
        elif new.startswith("\n"):
            # a block collection starts on the line after its key: drop the
            # space after the colon
            while s > 0 and text[s - 1] == " ":
                s -= 1
        edits.append((s, e, new))

    def insert(node: MappingNode, key: str, want, path):
        if node.flow_style:
            close = node.end_mark.index - 1
            if text[close] != "}":
                raise PatchError(f"cannot add {'.'.join(map(str, path))} here")
            sep = ", " if node.value else ""
            edits.append((close, close, f"{sep}{key}: {render(want, True, 0, path)}"))
            return
        if not node.value:
            raise PatchError(f"cannot add {'.'.join(map(str, path))} to an empty mapping")
        col = node.value[0][0].start_mark.column
        last = node.value[-1][1]
        at = _core_end(text, last.start_mark.index, last.end_mark.index)
        value = render(want, False, col + 2, path)
        sep = "" if value.startswith("\n") else " "
        edits.append((at, at, f"\n{' ' * col}{key}:{sep}{value}"))

    def remove(node: MappingNode, key_node, value_node, path):
        if node.flow_style:
            i = [k for k, _ in node.value].index(key_node)
            if i > 0:
                prev = node.value[i - 1][1]
                s, e = _core_end(text, prev.start_mark.index, prev.end_mark.index), value_node.end_mark.index
            else:
                s = key_node.start_mark.index
                nxt = node.value[1][0] if len(node.value) > 1 else None
                e = nxt.start_mark.index if nxt is not None else value_node.end_mark.index
            edits.append((s, e, ""))
            return
        s = key_node.start_mark.index - key_node.start_mark.column
        e = _core_end(text, value_node.start_mark.index, value_node.end_mark.index)
        if e < len(text) and text[e] == "\n":
            e += 1
        edits.append((s, e, ""))

    def walk(c, w, node, path, flow: bool, key_col: int, key_node=None):
        if c == w and type(c) is type(w):
            return
        if isinstance(c, dict) and isinstance(w, dict) and isinstance(node, MappingNode):
            pairs = _pairs(node)
            for key in w:
                if key in c and key in pairs:
                    k, v = pairs[key]
                    walk(c[key], w[key], v, path + [key], node.flow_style, k.start_mark.column, k)
                elif key not in c:
                    insert(node, key, w[key], path + [key])
                else:
                    raise PatchError(f"cannot find {'.'.join(map(str, path + [key]))}")
            for key in c:
                if key not in w:
                    k, v = pairs[key]
                    remove(node, k, v, path + [key])
            return
        if (isinstance(c, list) and isinstance(w, list) and isinstance(node, SequenceNode)
                and len(c) == len(w) and any(isinstance(x, dict) for x in w)):
            for i, (ci, wi) in enumerate(zip(c, w)):
                item = node.value[i]
                walk(ci, wi, item, path + [i], node.flow_style, item.start_mark.column - 2
                     if not node.flow_style else 0)
            return
        replace(node, w, flow, key_col, path, key_node)

    walk(cur, desired, root, [], False, -2)
    out = text
    for s, e, new in sorted(edits, key=lambda x: x[0], reverse=True):
        out = out[:s] + new + out[e:]
    try:
        back = yaml.safe_load(out)
    except yaml.YAMLError as exc:
        raise PatchError(f"the change does not fit the file's layout ({exc})") from None
    if back != desired:
        raise PatchError("the change does not fit the file's layout: edit it in the text tab")
    return out
