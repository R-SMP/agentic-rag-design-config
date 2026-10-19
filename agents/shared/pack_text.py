"""Pack words in the text the engine writes for the agents.

The prompts name this design configurator's outputs through the pack's
vocabulary (``$output_model`` "mesh", ``$output_images_label`` "Render
images" ...).  The text Python writes for the agents -- tool descriptions,
tool answers, runtime blocks -- does the same since MAS-blueprint P4a: its
sentences are the engine's, generic, and every word about the configurator
is a ``$name`` filled from the pack here.  :func:`fill` accepts:

* any slot of ``engine/slot_registry.yaml`` the pack fills (its shared text
  for the active topology): the vocabulary, ``$domain_description``,
  ``$dc_name``, ``$geometry_model_filename``, the small example slots;
* ``$parameter_count`` (from ``dc_pack/parameters.json``);
* the forms the engine derives from the vocabulary -- :data:`DERIVED`;
* the words it derives from the tool manifests -- :data:`FROM_MANIFESTS`
  (the model's file name and extension).

The web page takes its words the same way: ``web_app.py`` fills
``web/index.html`` with them (HTML-escaped) as it serves it, and hands the
page's script the ones it needs in ``/pack/page.js``.

An unknown ``$name`` is an error, so a misspelt word fails loudly; write
``$$`` for a literal dollar sign.

When the words are read:

* text built per call or per session (tool answers, a factory's tools, the
  routing tools, the Receptionist's block) -- every time;
* tool descriptions LangChain takes from a docstring -- :func:`described`
  (applied above ``@tool``) fills the description at import and remembers
  its template, and :func:`refresh_tools` (``agents/hub.build_hub``) fills
  them again for every session, so a topology switch inside one process
  reaches them; a tool a factory builds per session takes :func:`filled`
  instead;
* module constants (the Context Pruner's prompts, the inspectors' runtime
  blocks, the Database Handler's reminder, ``database_search``'s argument
  texts) -- once, at import.  The pack does not change within a process, and
  the words they use are the same in every topology today; a word given a
  per-topology copy would not reach them.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

from engine import pack as _pack
from engine import parameters as _parameters


def _cap(word: str) -> str:
    return word[:1].upper() + word[1:]


# Forms the engine derives from the pack's words: name -> (word, how).
DERIVED = {
    "Output_model": ("output_model", _cap),                    # "Mesh"
    "Output_image": ("output_image", _cap),                    # "Render"
    "Output_images": ("output_images", _cap),                  # "Renders"
    "output_images_label_lower": ("output_images_label", str.lower),  # "render images"
}


def _model_file() -> str:
    from engine import pack_tools
    return pack_tools.model_file() or ""


def _extra_images_note() -> str:
    """' (including\\n``<file>``)' for the pictures the helper tools make,
    "" when none does -- read_attempts' description."""
    from engine import pack_tools
    files = [r["file"] for r in pack_tools.image_outputs()
             if pack_tools.manifest(r["tool"])["kind"] == "helper"]
    return " (including\n" + ", ".join(f"``{f}``" for f in files) + ")" if files else ""


# Words the engine derives from the tool manifests (engine/pack_tools.py).
FROM_MANIFESTS = {
    "model_file": _model_file,                                    # "propeller_mesh.obj"
    "model_ext": lambda: Path(_model_file()).suffix,              # ".obj"
    "extra_images_note": _extra_images_note,
}


class _Words(dict):
    """The words of one fill, read from the pack on first use."""

    def __init__(self, topology: int):
        super().__init__()
        self.topology = topology

    def __missing__(self, name: str) -> str:
        if name in DERIVED:
            base, how = DERIVED[name]
            value = how(self[base])
        elif name in FROM_MANIFESTS:
            value = FROM_MANIFESTS[name]()
        elif name == "parameter_count":
            value = str(_parameters.count())
        elif name == "parameter_value":
            # "a number" while every parameter is one (MAS-blueprint P6d)
            value = _parameters.value_phrase()
        else:
            spec = _pack.registry().get(name)
            if spec is None or spec.get("source") != "pack":
                raise KeyError(f"${name} is not a pack word (engine/slot_registry.yaml)")
            value = _pack.read(name, self.topology)
        self[name] = value
        return value


class _Escaped(dict):
    """The words of one fill, each passed through *escape*."""

    def __init__(self, words: _Words, escape):
        super().__init__()
        self.words, self.escape = words, escape

    def __missing__(self, name: str) -> str:
        value = self.escape(self.words[name])
        self[name] = value
        return value


def fill(template: str, topology: int | None = None, escape=None,
         extra: dict | None = None) -> str:
    """*template* with every ``$name`` replaced by the pack's word for the
    active topology (or *topology*), passed through *escape* when given
    (the web page: ``html.escape``).  *extra* adds words of the caller's
    own (the web page: the tool chosen for downloads)."""
    if topology is None:
        from agents.shared.topology import topology as _active
        topology = _active()
    words = _Words(topology)
    words.update(extra or {})
    return Template(template).substitute(_Escaped(words, escape) if escape else words)


_DESCRIBED: list[tuple[object, str]] = []


def described(tool):
    """Decorator, above ``@tool``: the tool's description (its docstring)
    names pack words as ``$name``; fill them now and on every
    :func:`refresh_tools`."""
    template = tool.description
    _DESCRIBED.append((tool, template))
    tool.description = fill(template)
    return tool


def refresh_tools() -> None:
    """Fill every :func:`described` tool's description again (session build)."""
    for tool, template in _DESCRIBED:
        tool.description = fill(template)


def filled(tool):
    """Decorator, above ``@tool``, for a tool a factory builds per session:
    fill its description's pack words once, as it is built."""
    tool.description = fill(tool.description)
    return tool
