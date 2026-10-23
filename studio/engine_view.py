"""What the Studio shows of a setup, computed by the engine itself.

    python -m studio.engine_view static
    python -m studio.engine_view assemble <base|all_on> <7|5|3>
    python -m studio.engine_view view <choice.json>
    python -m studio.engine_view worker          (then one choice on stdin)
    python -m studio.engine_view checker         (then parameter files on stdin)

MAS-blueprint P5a.  The Studio's screens read one dict, :func:`build`:

* **static** -- the parameters (``setups/<setup>/parameters.json``), every text
  field of the pack with its three topology texts and its per-agent copies
  (read through the slot registry, ``engine/pack.py``), the role map, the
  tools and their settings, the parameter-access grid, the secrets' names;
* **assembled** -- every agent's real system prompt, topologies 3 / 5 / 7,
  under two setting combinations of ``prompt_matrix.py``: ``base`` (the
  setup's defaults) and ``all_on`` (every feature on), with the exact place
  of every field's text inside them ("where it lands").

Each part is computed in a child process (the commands above, run by
:func:`run_children` with ``DC_PACK_DIR`` set to the setup): the assembler
stubs the runtime packages (``extra_utilities/prompt_pdf/bootstrap.py``)
and some settings are captured at import, so one process per (combination,
topology) -- the prompt matrix's rule.  The seven children run in
parallel.

"Where it lands" without guessing
---------------------------------
Each topology is assembled TWICE in its child: once as is, once with every
pack field's text wrapped in invisible private-use markers (and the runtime
blocks too).  The markers are stripped again and the result must equal the
real prompt -- byte for byte, or, where a marker lengthened a line enough to
change a re-wrap, after whitespace normalisation.  The marker positions are
then exact spans in the REAL prompt.  An agent whose prompts do not line up
gets no spans and is reported (``align``), never approximated.

The prompt viewer (MAS-blueprint P5b)
------------------------------------
A VIEW is one topology assembled under a CHOICE of the settings that change
what an agent sees (:func:`viewer_controls`, measured setting by setting):
the prompts with their marked spans as above, and the tools each agent is
given when the team is built (:func:`team_tools`).  A choice is laid over
the setup's defaults (:func:`setup_defaults`) before any of the engine's
code loads, so each view runs in a process of its own -- usually a WORKER
that loaded the third-party libraries while it waited (:data:`PRELOAD`)
and takes exactly one job.

The Studio draft (``extra_utilities/docs/studio_draft/build_draft_data.py``)
builds its data from the same functions.
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMBOS = ("base", "all_on")
TOPOLOGIES = (7, 5, 3)

START, END, ID0 = "", "", 0xF0000

# The runtime blocks the assembler fills per agent ({routing_instructions},
# ...): marked too, so their text is not taken for generic engine text.
RUNTIME_SLOTS = ("routing_instructions", "render_check_library_block",
                 "image_persistence_block", "comparison_mode_block",
                 "chain_access_block", "user_inputs_dir",
                 "input_images_subdir", "extraction_output_file")


_loaded = False


def load_engine():
    """Make the engine's prompt layer importable in this (child) process:
    the repo and the assembler's folders on sys.path, the runtime packages
    stubbed (``extra_utilities/prompt_pdf/bootstrap.py``).  Once per
    process."""
    global _loaded
    if _loaded:
        return
    for p in ("extra_utilities/scripts", "extra_utilities/prompt_pdf", "."):
        sys.path.insert(0, str(REPO / p))
    sys.modules["simplejson"] = None          # type: ignore[assignment]
    sys.modules["chardet"] = None             # type: ignore[assignment]
    import bootstrap
    bootstrap.install()
    _loaded = True


def setup_defaults(combo: str = "base"):
    """Lay ``prompt_matrix.py``'s combination *combo* over the SETUP's
    defaults in this (child) process -- settings.py as written, each
    tool.yaml's defaults, pack.yaml's access table -- and nothing saved on
    this computer in Workflow Settings (``tool_settings.json``,
    ``parameter_access.json``, ``engine/setups.py``).  Before any agent code loads: some
    settings are read at import.  Returns the settings module."""
    import prompt_matrix as PM
    S = PM.apply_config(combo)
    from engine import pack_tools as PT
    PT.read_overrides = lambda: {}
    return S


def pack_slots(P) -> dict[str, str]:
    """slot -> 'dc' | 'tool', for every $slot whose text lives in the pack
    (from the slot registry; runtime fragments are not $slots)."""
    out = {name: ("dc" if spec["folder"] == "dc" else "tool")
           for name, spec in P._pack.slots(source="pack", use="prompt").items()}
    # The tool runner's numbered list ($tool_inventory) is built by the engine
    # from each tool's own entry (MAS-blueprint P3d): still tool text.
    out.update({name: "tool" for name, spec in P._pack.slots(source="generated").items()
                if spec["from"] in P._GENERATED_PER_AGENT})
    return out


# ---------------------------------------------------------------------------
# assembly (child): one (combination, topology), twice, with spans
# ---------------------------------------------------------------------------

def strip_markers(marked: str, names: list[str]):
    """The text without its markers, and ``[start, end, name, depth]`` per
    marked span (positions in the stripped text)."""
    text, spans, stack = [], [], []
    n = 0
    i = 0
    while i < len(marked):
        c = marked[i]
        if c == START and i + 1 < len(marked):
            stack.append((ord(marked[i + 1]) - ID0, n))
            i += 2
            continue
        if c == END:
            if stack:
                idx, s = stack.pop()
                if n > s:
                    spans.append([s, n, names[idx], len(stack)])
            i += 1
            continue
        text.append(c)
        n += 1
        i += 1
    while stack:
        idx, s = stack.pop()
        if n > s:
            spans.append([s, n, names[idx], len(stack)])
    return "".join(text), spans


def normalise(t: str):
    """Collapse whitespace runs; return (normalised, n_of[i] for i in t, idx)."""
    out, idx, n_of = [], [], []
    prev_ws = False
    for i, c in enumerate(t):
        ws = c.isspace()
        if ws and prev_ws:
            n_of.append(len(out) - 1)
            continue
        n_of.append(len(out))
        out.append(" " if ws else c)
        idx.append(i)
        prev_ws = ws
    n_of.append(len(out))
    return "".join(out), n_of, idx


def assemble(combo: str, topology: int) -> dict:
    """Every agent's prompt under *combo* (a ``prompt_matrix.py``
    combination) and *topology*, with the place of every field's text in
    it: ``{"prompts", "spans", "align"}``.  Patches the prompt layer, so it
    belongs in a process of its own."""
    load_engine()
    # The same combination set-up as the prompt matrix, including the
    # parameter-access cells its old setting names stand for.
    setup_defaults(combo)
    return assemble_marked(topology)


def assemble_marked(topology: int) -> dict:
    """The prompts of *topology* under the settings already in place,
    assembled twice -- as is and marked -- with the marks turned into spans
    of the real prompts (see the module's docstring)."""
    import topology_prompt_snapshot as T
    from agents.shared import prompts as P

    real = T._assemble(topology)["prompts"]
    pack = pack_slots(P)
    names = sorted(pack) + list(RUNTIME_SLOTS)
    ids = {nm: i for i, nm in enumerate(names)}

    orig_mark = P.mark_inline_slots

    def marked_slots(slots):
        return orig_mark({k: (START + chr(ID0 + ids[k]) + v + END
                              if k in pack and v else v)
                          for k, v in slots.items()})
    P.mark_inline_slots = marked_slots

    orig_rt = T._runtime_slots

    def marked_runtime(agent, P_, S_):
        d = orig_rt(agent, P_, S_)
        if d is None:
            return None
        return {k: (START + chr(ID0 + ids[k]) + v + END if k in ids and v else v)
                for k, v in d.items()}
    T._runtime_slots = marked_runtime

    try:
        marked = T._assemble(topology)["prompts"]
    finally:
        P.mark_inline_slots, T._runtime_slots = orig_mark, orig_rt
    result = {"prompts": real, "spans": {}, "align": {}}
    for agent, text in real.items():
        stripped, spans = strip_markers(marked.get(agent, ""), names)
        if stripped == text:
            result["align"][agent] = "exact"
            result["spans"][agent] = spans
            continue
        ns, n_of_s, _ = normalise(stripped)
        nr, _, idx_r = normalise(text)
        if ns != nr:
            result["align"][agent] = "FAILED"
            result["spans"][agent] = []
            continue
        mapped = []
        for s, e, nm, depth in spans:
            a, b = n_of_s[s], n_of_s[e]
            if b <= a:
                continue
            mapped.append([idx_r[a], idx_r[b - 1] + 1, nm, depth])
        result["align"][agent] = "normalized"
        result["spans"][agent] = mapped
    return result


# ---------------------------------------------------------------------------
# the prompt viewer (MAS-blueprint P5b)
# ---------------------------------------------------------------------------

# The engine settings that change what an agent sees, found by flipping
# every setting of settings.py in turn (P5b): RAG (its own control), these,
# each tool's switch and the tool settings the prompts read.
VIEWER_SETTINGS = ("DC_INSPECTOR_ENABLED", "DCOI_COMPARISON_MODE",
                   "KEEP_IMAGES_IN_CONTEXT", "CHAIN_ACCESS", "OCR_ENABLED")
RAG_CHOICES = ("off", "on", "all")      # all = every agent holds every database tool

_FLAG_IN_TEXT_RE = re.compile(r"<<(?:IF|IFNOT):((?:tool|setting):[a-z0-9_.]+)>>")


def _prompt_texts() -> list[Path]:
    """Every file prompt text is assembled from: the engine's (agents/)
    and the pack's (fragments and the tools' prompts/)."""
    from engine import pack
    files = {f for f in (REPO / "agents").rglob("*.md") if f.name != "README.md"}
    files |= set(pack.fragment_files()) | set(pack.tool_list_entry_files())
    return sorted(files)


def viewer_controls() -> dict:
    """The prompt viewer's settings bar, with the setup's defaults: RAG; the
    engine settings of :data:`VIEWER_SETTINGS` (with the topologies each
    one acts in, from Workflow Settings' own list, and its help text from
    settings.py); per tool its on/off switch and the settings its prompt
    text reads -- named in an ``<<IF:setting:...>>`` marker or in one of its
    runtime blocks."""
    from engine import pack_tools
    from workflow_settings import editor
    helps = {item["name"]: item.get("help", "") for item in editor.read_schema()}
    values = settings_values(set(VIEWER_SETTINGS) | {"RAG_ENABLED"})
    engine = []
    for name in VIEWER_SETTINGS:
        inert = editor._INERT_UNDER_TOPOLOGY.get(name, (frozenset(), ""))[0]
        engine.append({
            "name": name,
            "type": "enum" if name in editor.ENUM_OPTIONS else "bool",
            "values": editor.ENUM_OPTIONS.get(name),
            "default": values[name],
            "topologies": [n for n in TOPOLOGIES if n not in inert],
            "help": helps.get(name, ""),
        })
    used = set()
    for f in _prompt_texts():
        used.update(_FLAG_IN_TEXT_RE.findall(f.read_text(encoding="utf-8")))
    tools = []
    for name, m in pack_tools.manifests().items():
        specs = pack_tools.setting_specs(name)
        # A runtime block reads the settings its slot names, and only while
        # its off_unless setting is on.
        in_blocks: dict[str, str | None] = {}
        for b in (m.get("runtime_blocks") or {}).values():
            for ref in pack_tools._SETTING_REF_RE.findall(b["slot"]):
                in_blocks[ref] = b.get("off_unless")
            if b.get("off_unless"):
                in_blocks.setdefault(b["off_unless"], None)
        switch = next((s for s in specs if s["name"] == "enabled"), None)
        read = [{"name": s["name"], "type": s["type"], "values": s.get("values"),
                 "default": s["default"], "label": s.get("label", s["name"]),
                 "only_with": in_blocks.get(s["name"])}
                for s in specs if s["name"] != "enabled"
                and (f"setting:{name}.{s['name']}" in used or s["name"] in in_blocks)]
        if switch or read:
            tools.append({"tool": name, "display": m["display_name"],
                          "switch": ({"default": switch["default"],
                                      "label": switch.get("label", name)} if switch else None),
                          "settings": read})
    return {"rag_default": "on" if values["RAG_ENABLED"] else "off",
            "rag_help": helps.get("RAG_ENABLED", ""), "settings": engine, "tools": tools}


class ChoiceError(ValueError):
    """A viewer choice the setup does not offer."""


def canonical_choice(raw: dict, data: dict) -> dict:
    """A viewer choice, checked against the Studio's data (*data*:
    :func:`static_data`) and filled with the setup's defaults:
    ``{"topology", "rag", "settings": {name: value}, "tools": {tool:
    {setting: value}}, "access": {agent: state}}``.  A setting that does
    nothing in the topology is put back to its default, and an access cell
    equal to the setup's is dropped, so equal views have equal choices.
    Pure: the Studio's server calls it."""
    raw = dict(raw or {})
    known = {"topology", "rag", "settings", "tools", "access"}
    if set(raw) - known:
        raise ChoiceError(f"unknown parts: {', '.join(sorted(set(raw) - known))}")
    v = data["viewer"]
    topo = raw.get("topology", 7)
    if topo not in TOPOLOGIES:
        raise ChoiceError(f"team size is one of {', '.join(map(str, sorted(TOPOLOGIES)))}")
    rag = raw.get("rag", v["rag_default"])
    if rag not in RAG_CHOICES:
        raise ChoiceError(f"rag is one of {', '.join(RAG_CHOICES)}")
    specs = {s["name"]: s for s in v["settings"]}
    given = dict(raw.get("settings") or {})
    if set(given) - set(specs):
        raise ChoiceError(f"unknown settings: {', '.join(sorted(set(given) - set(specs)))}")
    settings = {}
    for name, s in specs.items():
        val = given.get(name, s["default"])
        if s["type"] == "bool" and not isinstance(val, bool) or \
                s["type"] == "enum" and val not in s["values"]:
            raise ChoiceError(f"{name}: {val!r} is not allowed")
        settings[name] = val if topo in s["topologies"] else s["default"]
    tool_specs = {t["tool"]: t for t in v["tools"]}
    given_tools = dict(raw.get("tools") or {})
    if set(given_tools) - set(tool_specs):
        raise ChoiceError(f"unknown tools: {', '.join(sorted(set(given_tools) - set(tool_specs)))}")
    tools = {}
    for name, t in tool_specs.items():
        g = dict(given_tools.get(name) or {})
        allowed = {s["name"]: s for s in t["settings"]}
        if t["switch"]:
            allowed["enabled"] = {"type": "bool", "default": t["switch"]["default"]}
        if set(g) - set(allowed):
            raise ChoiceError(f"{name}: unknown settings {', '.join(sorted(set(g) - set(allowed)))}")
        vals = {}
        for key, s in allowed.items():
            val = g.get(key, s["default"])
            if s["type"] == "bool" and not isinstance(val, bool) or \
                    s["type"] == "enum" and val not in s["values"]:
                raise ChoiceError(f"{name}.{key}: {val!r} is not allowed")
            vals[key] = val
        tools[name] = vals
    pa = data["parameter_access"]
    states = [s["id"] for s in pa["states"]]
    cells = {r["agent"]: r["cells"] for r in pa["rows"]}
    access = {}
    for agent, state in dict(raw.get("access") or {}).items():
        cell = cells.get(agent, {}).get(str(topo))
        if cell is None:
            raise ChoiceError(f"access: {agent} has no cell in the {topo}-agent team")
        if state not in states or (state == "tool" and agent in pa["no_tool"]):
            raise ChoiceError(f"access: {agent} cannot take {state!r}")
        if state != cell:
            access[agent] = state
    return {"topology": topo, "rag": rag, "settings": settings, "tools": tools,
            "access": access}


def apply_choice(choice: dict):
    """Lay a canonical *choice* over the setup's defaults in this (child)
    process, before any agent code loads."""
    S = setup_defaults("base")
    for name, value in choice["settings"].items():
        setattr(S, name, value)
    S.RAG_ENABLED = choice["rag"] != "off"
    S.TEAM_SIZE = choice["topology"]
    from engine import pack_tools as PT
    PT.settings_override_for_tests(choice["tools"])
    from engine import parameter_access as PA
    cells = {agent: {choice["topology"]: state} for agent, state in choice["access"].items()}
    PA.read_overrides = lambda: {a: dict(r) for a, r in cells.items()}
    if choice["rag"] == "all":
        from workflow_settings import database_access as DA
        DA.is_enabled_for = lambda agent, tool=None: True
    return S


def team_tools(topology: int) -> dict:
    """agent -> the tools it is given when the team of *topology* is built:
    ``[{name, description, args}]``.  The real hub, built with a stand-in
    model that records what each agent is bound to (the way of
    ``extra_utilities/scripts/tool_matrix.py``).  Tools an agent is given
    for one turn later (the Database Handler's) are not here."""
    import datetime
    from unittest.mock import MagicMock

    import tool_matrix as TM
    import workflow_settings.settings as S
    from agents.hub import build_hub
    from agents.shared import base_chain_agent, llm_provider
    from agents.shared.session import Session

    S.TEAM_SIZE = topology
    bound: dict[str, list] = {}

    class Recorder:
        def get_for_agent(self, agent_key):
            provider, model, _ = llm_provider._resolve_config(agent_key)
            llm = MagicMock(name=f"llm:{agent_key}")

            def bind_tools(tools, **kwargs):
                # An agent is bound once while it is built; were it bound
                # again, the later tools are the ones it keeps.
                bound[agent_key] = [TM._describe(t) for t in tools]
                return MagicMock(name=f"bound:{agent_key}")
            llm.bind_tools.side_effect = bind_tools
            return llm, provider, model

    rec = Recorder()
    base_chain_agent._default_llm_cache = rec
    build_hub(Session(session_id=f"studio_view_{topology}",
                      session_ts=datetime.datetime.now(datetime.timezone.utc)), llm_cache=rec)
    return bound


def view(choice: dict) -> dict:
    """One view: *choice*'s topology assembled under it (prompts, spans,
    align), its team's tools, and the primer each agent is sent."""
    load_engine()
    apply_choice(choice)
    out = assemble_marked(choice["topology"])
    out["tools"] = team_tools(choice["topology"])
    out["primer"] = primer_view(choice["topology"])
    return out


def primer_view(topology: int) -> dict:
    """agent -> the primer it is sent in *topology*, before the
    conversation (``engine/primer.py``): its text, whether that is the
    agent's own copy, the picture (file, size, tokens) and ``enabled`` --
    Workflow Settings' switch as set up.  Agents the setup gives none are
    left out; so is everyone when its section cannot be read (Validate
    says why)."""
    import yaml

    import workflow_settings.settings as S
    from engine import pack
    from engine import primer as pr
    try:
        agents = pr.agents_for(topology)
        path = pr.image_path()
    except (pr.PrimerError, yaml.YAMLError):
        return {}
    picture = None
    if path is not None:
        w, h = pr.png_size(path)
        picture = {"file": path.name, "width": w, "height": h, "tokens": pr.image_tokens(w, h)}
    out = {}
    for agent in agents:
        f = pack.fragment_path(pr.TEXT_SLOT, topology, agent)
        text = f.read_text(encoding="utf-8").rstrip() if f is not None else ""
        if text or picture:
            out[agent] = {"text": text, "picture": picture,
                          "own_copy": pack.agent_copy_path(pr.TEXT_SLOT, topology, agent) is not None,
                          "enabled": bool(getattr(S, "DC_PARAMS_PRIMER_ENABLED", True))}
    return out


# Third-party libraries a view loads.  A waiting worker loads them before
# it is given its job: none reads a setting of ours, and our own code loads
# only once the job's settings are in place.  LangChain loads its modules
# lazily, so these name the modules themselves (measured for P5b: they load
# 279 of the 280 third-party modules a view needs).  A name missing here
# only costs time; a name that is not installed is skipped.
PRELOAD = ("langchain_core.tools.base", "langchain_core.tools.structured",
           "langchain_core.tools.convert", "langchain_core.tools.simple",
           "langchain_core.callbacks.manager", "langchain_core.messages",
           "langchain_core.messages.utils", "langchain_core.runnables.base",
           "langchain_core.outputs", "langchain_core.utils.function_calling",
           "langchain_core.rate_limiters", "langsmith.client", "langsmith.run_trees",
           "langsmith.run_helpers", "pydantic.type_adapter", "pydantic.dataclasses",
           "numpy", "PIL.ImageDraw", "PIL.ImageFont", "PIL.ImageOps", "httpx", "anyio",
           "yaml")


def hold_files() -> None:
    """This process answers for one state of the setup and lives a few
    seconds: take its files as unchanging (``engine/pack.py``
    ``hold_stamps``), so they are not checked again on every lookup."""
    load_engine()
    from engine import pack
    pack.hold_stamps()


def worker() -> int:
    """Load :data:`PRELOAD`, then wait for ONE choice (a JSON line on stdin;
    ``pack_dir`` in it names another copy of the setup), answer its view on
    stdout and end.  An empty line ends it unused."""
    load_engine()
    for name in PRELOAD:
        try:
            importlib.import_module(name)
        except Exception:                                   # noqa: BLE001
            pass
    hold_files()
    line = sys.stdin.readline()
    if not line.strip():
        return 0
    job = json.loads(line)
    # A job may name another copy of the setup (the Studio's OPENED copy,
    # for the prompt diff); engine/pack.py reads config.DC_PACK_DIR per call.
    other = job.pop("pack_dir", None)
    if other:
        import config
        config.DC_PACK_DIR = Path(other)
    payload = view(job)
    sys.stdout.buffer.write(json.dumps(payload, default=str).encode("utf-8"))
    return 0


# ---------------------------------------------------------------------------
# running the children
# ---------------------------------------------------------------------------

ASSEMBLY_JOBS = {(combo, n): ["assemble", combo, str(n)]
                 for combo in COMBOS for n in TOPOLOGIES}


def run_children(jobs: dict, pack_dir: Path | None = None,
                 timeout: float = 600) -> dict:
    """Run ``python -m studio.engine_view <args>`` for every job, in
    parallel, with ``DC_PACK_DIR`` set to *pack_dir* (default: the
    environment's).  Returns ``{key: parsed JSON}`` in the jobs' order.
    Raises RuntimeError with the child's error when one fails."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if pack_dir is not None:
        env["DC_PACK_DIR"] = str(pack_dir)

    def one(args):
        proc = subprocess.run([sys.executable, "-m", "studio.engine_view", *args],
                              capture_output=True, cwd=str(REPO), env=env,
                              timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"{' '.join(args)}: "
                               + proc.stderr.decode("utf-8", "replace")[-3000:])
        return json.loads(proc.stdout.decode("utf-8"))

    with ThreadPoolExecutor(max_workers=max(1, len(jobs))) as pool:
        futures = {key: pool.submit(one, args) for key, args in jobs.items()}
        return {key: f.result() for key, f in futures.items()}


# ---------------------------------------------------------------------------
# static pack data (child)
# ---------------------------------------------------------------------------

def _topology_texts(pack, folder: Path, base: str, spec: dict) -> dict:
    """{"7"|"5"|"3": text or None} as stored on disk: the linked file for all
    three, else each topology's own ``.t<N>.md`` (None where there is none)."""
    linked = folder / f"{base}.md"
    if linked.is_file():
        t = pack._clean(spec, linked.read_text(encoding="utf-8"))
        return {"7": t, "5": t, "3": t}
    out = {}
    for n in ("7", "5", "3"):
        p = folder / f"{base}.t{n}.md"
        out[n] = pack._clean(spec, p.read_text(encoding="utf-8")) if p.is_file() else None
    return out


def _entry_agrees(pack, p: dict) -> bool:
    """A choice's or an on/off parameter's entry in the shared parameter
    list holds its values and "only when" (engine/parameters.py)."""
    from engine import parameters as ep
    text = pack.shared_path("parameter_list", pack.REFERENCE_TOPOLOGY).read_text(encoding="utf-8")
    entry = []
    for line in text.splitlines():
        if re.match(r"\s*\d+\.\s+" + re.escape(p["name"]) + r"\b", line):
            entry = [line]
        elif entry and line.strip() and not re.match(r"\s*\d+\.\s", line) and not line.lstrip().startswith("#"):
            entry.append(line)
        elif entry:
            break
    return bool(entry) and ep.entry_problem(p, " ".join(entry)) is None


def parameters(pack) -> dict:
    """The parameter set from its single source, ``setups/<setup>/parameters.json``
    (``engine/parameters.py``), plus each parameter's unit and description
    as the agents' hand-written ``$parameter_list`` text words them.
    ``copies_agree``: that text gives the same range as the file (a choice
    or on/off parameter: its values and "only when", MAS-blueprint P6d)."""
    from engine import parameters as ep
    spec = ep.load()
    md = {}
    for line in pack.shared_path("parameter_list", pack.REFERENCE_TOPOLOGY).read_text(
            encoding="utf-8").splitlines():
        m = re.match(r"\s*\d+\.\s+(\w+)\s+\((.*?)\)\s+—\s+(.*?)\s*\[([\d.]+);\s*([\d.]+)\]\s*$", line)
        if m:
            md[m.group(1)] = {"unit_prompt": m.group(2), "description": m.group(3),
                              "min": float(m.group(4)), "max": float(m.group(5))}
    params = []
    for p in spec["parameters"]:
        a = md.get(p["name"], {})
        params.append({
            "name": p["name"], "type": p["type"], "group": p["group"],
            "label": p["label"], "unit": p["unit"],
            "unit_prompt": a.get("unit_prompt", ""), "description": a.get("description", ""),
            "min": p.get("min"), "max": p.get("max"), "step": p.get("step"), "default": p["default"],
            "copies_agree": (a.get("min"), a.get("max")) == (float(p["min"]), float(p["max"]))
            if "min" in p else _entry_agrees(pack, p),
        })
    groups = [{"id": g["id"], "label": g["label"]} for g in spec["groups"]]
    return {"groups": groups, "parameters": params}


def registry_order(pack) -> dict[str, int]:
    """slot -> its place among its section's slots, in the slot registry's
    order (``engine/slot_registry.yaml``)."""
    seen: dict = defaultdict(int)
    out = {}
    for name, spec in pack.registry().items():
        sec = spec.get("section", "other")
        out[name] = seen[sec]
        seen[sec] += 1
    return out


def text_fields(pack) -> dict:
    """The setup's text fields: the $slots spliced into prompts, and the ones
    the app's code reads (``use: runtime``: tool texts and answers, the tool
    runner's list, the parameter primer, the web page's words --
    ``setups/<setup>/README.md``)."""
    return {**pack.slots(source="pack", use="prompt"), **pack.slots(source="pack", use="runtime")}


def slots(P, pack_origin: dict, roles: dict, order: dict | None = None) -> list:
    """Every pack text field with its three topology texts and per-agent
    copies, read from setups/<setup>/ through the registry (engine/pack.py naming).
    A field a tool owns is read from that tool's prompts/ folder and names
    its owner; ``runtime``: read by the app's code, not spliced into a prompt
    by a $name.  *order*: slot -> its place in its section (default: the
    registry's)."""
    pack = P._pack
    claims = pack.tool_claims()
    order = registry_order(pack) if order is None else order
    agents = sorted({a for t in roles["roster"].values() for a in t} | {"database_handler"})
    out = []
    for slot, spec in sorted(text_fields(pack).items()):
        folder = (pack.tool_prompts_dir(claims[slot]) if slot in claims
                  else pack.fragments_dir() / spec["folder"])
        overlay = spec.get("missing") == "empty"
        vals = ({"7": "", "5": "", "3": ""} if overlay
                else _topology_texts(pack, folder, slot, spec))
        variants = []
        for ag in agents:
            v = _topology_texts(pack, folder, f"{slot}@{ag}", spec)
            if any(x is not None for x in v.values()):
                variants.append({"agent": ag, "values": v,
                                 "linked": (folder / f"{slot}@{ag}.md").is_file()})
        out.append({
            "slot": slot, "title": spec.get("title", ""), "origin": pack_origin.get(slot, "dc"),
            "owner": claims.get(slot),
            "kind": spec["kind"], "runtime": spec.get("use") == "runtime",
            "section": spec.get("section", "other"), "order": order.get(slot, 999),
            "description": spec.get("description", "") or (
                "Per-agent overlay: each agent's own text for this tool; "
                "agents without a file get nothing." if overlay else ""),
            "values": vals,
            # Linked = ONE file for every topology (what an edit changes);
            # an overlay has no shared text at all.
            "linked": overlay or (folder / f"{slot}.md").is_file(),
            "variants": variants,
        })
    return out


def roles() -> dict:
    from agents.shared import agent_roles as AR
    from agents.shared.routing_tools import AGENT_DISPLAY
    disp = {k: (v if isinstance(v, str) else str(v)) for k, v in AGENT_DISPLAY.items()}
    disp.setdefault("database_handler", "Database Handler")
    return {"roster": {str(k): list(v) for k, v in AR.ROSTER.items()},
            "roles_of": {k: list(v) for k, v in AR.ROLES_OF.items()},
            "holder": {str(k): v for k, v in AR._HOLDER_BY_TOPOLOGY.items()},
            "display": disp}


def parameter_access() -> dict:
    """The pack's parameter-access grid (engine/parameter_access.py), for the
    Agent access screen: one row per agent, its cell per topology."""
    from agents.shared import agent_roles
    from engine import parameter_access as pa
    names = dict(agent_roles.DISPLAY, database_handler="Database Handler")
    return {
        "states": [{"id": s, "short": s, "label": pa.LABELS[s]} for s in pa.STATES],
        "no_tool": sorted(pa.NO_TOOL_AGENTS),
        "rows": [{"agent": a, "name": names.get(a, a),
                  "cells": {str(t): s for t, s in row.items()}}
                 for a, row in pa.default_table().items()],
    }


def primer_data() -> dict:
    """The setup's primer (``engine/primer.py``) for the Primer page: the
    picture it names (``{file, width, height, bytes, tokens}``, or ``{file,
    error}``), one row per agent that may get it -- its cell in each
    topology it is in, and the topologies where it has its own text -- and
    why ``pack.yaml``'s section cannot be read when it cannot."""
    import yaml

    from agents.shared import agent_roles
    from engine import pack
    from engine import primer as pr
    try:
        cur, problems = pr.read(), []
    except (pr.PrimerError, yaml.YAMLError) as exc:
        cur, problems = None, [ln for ln in str(exc).split("\n") if ln.strip()]
    picture = None
    if cur and cur["image"]:
        path = pack.asset_path(cur["image"])
        if not path.is_file():
            picture = {"file": cur["image"], "error": "missing"}
        else:
            try:
                w, h = pr.png_size(path)
                picture = {"file": cur["image"], "width": w, "height": h,
                           "bytes": path.stat().st_size, "tokens": pr.image_tokens(w, h)}
            except ValueError:
                picture = {"file": cur["image"], "error": "not a PNG"}
    order = []                      # the 7-agent team first
    for t in TOPOLOGIES:
        order += [a for a in agent_roles.ROSTER[t] if a not in order]
    rows = []
    for agent in order:
        if agent in pr.NO_PRIMER_AGENTS:
            continue
        rows.append({
            "agent": agent, "name": agent_roles.DISPLAY.get(agent, agent),
            "cells": {str(t): bool(cur) and agent in cur["agents"][t]
                      for t in TOPOLOGIES if agent in agent_roles.ROSTER[t]},
            "copies": [t for t in TOPOLOGIES if agent in agent_roles.ROSTER[t]
                       and pack.agent_copy_path(pr.TEXT_SLOT, t, agent)]})
    return {"declared": bool(cur and cur["declared"]), "image": cur["image"] if cur else None,
            "picture": picture, "rows": rows, "problems": problems, "text_slot": pr.TEXT_SLOT,
            "no_primer": sorted(pr.NO_PRIMER_AGENTS)}


def settings_values(names) -> dict:
    """The on-disk defaults of the named settings (workflow_settings/
    settings.py), read as source: no override applies."""
    tree = ast.parse((REPO / "workflow_settings/settings.py").read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in names and node.value is not None:
                try:
                    out[node.target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
    return out


def tools() -> list:
    """The pack's tools, from their manifests (engine/pack_tools.py)."""
    from engine import pack_tools
    out = []
    for name, m in pack_tools.manifests().items():
        # its code -- or, for a tool the engine runs (backend: P6e), its model file
        ref = m.get("build") or m.get("entrypoint") or m.get("model")
        out.append({"name": name, "display": m["display_name"], "kind": m["kind"],
                    "file": f"tools/{name}/{ref.split(':')[0]}",
                    "description": m["description"],
                    "owns": list(m.get("prompt_slots") or []),
                    "list_order": m.get("list_order"),
                    "secrets": list(m.get("secrets") or [])})
    return out


def tool_settings() -> list:
    """Each tool's settings with their defaults (the Settings screen)."""
    from engine import pack_tools
    return [{"tool": name, "settings": [
                {"name": s["name"], "type": s["type"], "default": s["default"],
                 "values": s.get("values"), "label": s.get("label", "")}
                for s in pack_tools.setting_specs(name)]}
            for name in pack_tools.manifests()]


def where(prompts: dict) -> dict:
    """slot -> list of landing sentences, grouped across agents/topologies.
    *prompts*: ``{(combination, topology): assemble(...)}``."""
    groups = defaultdict(lambda: defaultdict(list))
    for (combo, topo), data in prompts.items():
        for agent, text in data["prompts"].items():
            for s, e, nm, _depth in data["spans"].get(agent, []):
                head = ""
                for line in reversed(text[:s].split("\n")):
                    if line.startswith("#"):
                        head = line.lstrip("#").strip()
                        break
                a = max(text.rfind(". ", 0, s) + 2, text.rfind("\n\n", 0, s) + 2, s - 220, 0)
                b_candidates = [x for x in (text.find(". ", e), text.find("\n\n", e)) if x != -1]
                b = min(b_candidates + [e + 220, len(text)])
                before = " ".join(text[a:s].split())
                value = " ".join(text[s:e].split())
                after = " ".join(text[e:b + 1].split())
                if len(value) > 260:
                    value = value[:240] + " …"
                key = (head, before, value, after)
                groups[nm][key].append((combo, topo, agent))
    out = {}
    for nm, g in groups.items():
        rows = []
        for (head, before, value, after), found in g.items():
            agents = defaultdict(set)
            combos = set()
            for combo, topo, agent in found:
                agents[agent].add(topo)
                combos.add(combo)
            rows.append({"heading": head, "before": before, "value": value,
                         "after": after,
                         "agents": {a: sorted(t, reverse=True) for a, t in agents.items()},
                         "only_with_features": combos == {"all_on"}})
        rows.sort(key=lambda r: (r["only_with_features"], -sum(len(t) for t in r["agents"].values())))
        out[nm] = rows
    return out


def base_prompts(prompts: dict) -> dict:
    """The ``base`` combination's prompts and spans, per topology."""
    return {f"{n}": {"prompts": prompts[("base", n)]["prompts"],
                     "spans": prompts[("base", n)]["spans"]}
            for n in TOPOLOGIES}


def alignment(prompts: dict) -> dict:
    """``"<combination>/<topology>"`` -> agent -> exact | normalized | FAILED."""
    return {f"{c}/{n}": prompts[(c, n)]["align"] for c, n in prompts}


def env_names() -> list:
    return sorted({ln.split("=", 1)[0].strip() for ln in
                   (REPO / ".env.example").read_text(encoding="utf-8").splitlines()
                   if re.match(r"^[A-Z][A-Z0-9_]*=", ln)})


# ---------------------------------------------------------------------------
# the Studio's own static data (not in the draft's)
# ---------------------------------------------------------------------------

def env_sections() -> dict:
    """variable -> the heading of its section in ``.env.example`` (the
    comment line between two ``# ----`` rules)."""
    lines = (REPO / ".env.example").read_text(encoding="utf-8").splitlines()
    out, head = {}, ""
    for i, ln in enumerate(lines):
        if (ln.startswith("# ---") and i + 2 < len(lines)
                and lines[i + 2].startswith("# ---")):
            head = lines[i + 1].lstrip("#").strip()
        m = re.match(r"^([A-Z][A-Z0-9_]*)=", ln)
        if m:
            out[m.group(1)] = head
    return out


def slot_files(pack) -> dict:
    """slot -> {"" (the shared text) | agent: [its files]}, each path
    starting with the setup folder's name."""
    root = pack.pack_dir()
    out: dict = {}
    for p in pack.fragment_files():
        agent = p.name[:-3].split("@", 1)[1].split(".")[0] if "@" in p.name else ""
        out.setdefault(pack.slot_of_file(p.name), {}).setdefault(agent, []).append(
            f"{root.name}/{p.relative_to(root).as_posix()}")
    return out


def tool_info() -> dict:
    """tool -> what its manifest declares beyond :func:`tools`: the roles
    that may call it, its model format and pictures, its on/off switch and
    its settings' names."""
    from engine import pack_tools
    out = {}
    for name, m in pack_tools.manifests().items():
        outputs = m.get("outputs") or {}
        out[name] = {
            "roles": list(m.get("roles") or []),
            "model_format": outputs.get("model_format"),
            "images": [{"view": i["view"], "label": i.get("label", i["view"]),
                        "default_enabled": i.get("default_enabled", True)}
                       for i in outputs.get("images") or []],
            "switch": bool(m.get("switch")),
            "settings": [s["name"] for s in pack_tools.setting_specs(name)],
        }
    return out


def editing_data(P, slot_list: list) -> dict:
    """What the Studio's editor needs (P6a), read through the engine: each
    text field's folder (``dir``, relative to the setup; None for text
    about a tool the setup lacks), kind and trimming; the ``$names`` and
    ``<<IF:...>>`` flags a text may use; the setup's tool names; and, per
    field and topology, the file the engine actually reads (``resolve``:
    a topology without its own file reads another one)."""
    from engine import pack_flags, pack_tools
    pack = P._pack
    root = pack.pack_dir()
    claims = pack.tool_claims()
    specs = {}
    for name, spec in text_fields(pack).items():
        if name in claims:
            folder = pack.tool_prompts_dir(claims[name]).relative_to(root).as_posix()
        elif spec.get("filled_by") == "tool":
            folder = None
        else:
            folder = (pack.fragments_dir() / spec["folder"]).relative_to(root).as_posix()
        specs[name] = {"dir": folder, "kind": spec["kind"],
                       "strip": spec.get("strip", "right"),
                       "missing": spec.get("missing", "crash")}

    def rel(path):
        return None if path is None else f"{root.name}/{path.relative_to(root).as_posix()}"
    resolve = {}
    for s in slot_list:
        rows = {"": {str(n): rel(pack.fragment_path(s["slot"], n)) for n in TOPOLOGIES}}
        for v in s["variants"]:
            rows[v["agent"]] = {str(n): rel(pack.fragment_path(s["slot"], n, v["agent"]))
                                for n in TOPOLOGIES}
        resolve[s["slot"]] = rows
    return {
        "slot_specs": specs,
        "text_names": sorted(set(P._build_slots()) | set(pack.registry())),
        "text_flags": sorted(set(pack_flags.values()) | {"param_list", "param_ranges"}),
        "pack_tools": sorted(pack_tools.manifests()),
        "resolve": resolve,
    }


def _title(pack) -> str:
    """The web app's title (``$app_title``), "" when the setup has none."""
    try:
        return pack.read("app_title", 7)
    except (KeyError, OSError):
        return ""


def static_data() -> dict:
    """Everything the Studio shows that is read, not assembled."""
    load_engine()
    from agents.shared import prompts as P
    from engine import parameters as ep
    pack = P._pack
    role_map = roles()
    slot_list = slots(P, pack_slots(P), role_map)
    return {
        "pack": {"name": pack.read("dc_name", 7),
                 "title": _title(pack),
                 "domain": pack.read("domain_description", 7),
                 "parameter_count": P._GENERATED_SLOTS["parameter_count"]()},
        "pack_dir": str(pack.pack_dir()),
        "parameters": parameters(pack),
        "group_images": {g["id"]: g.get("image") for g in ep.load()["groups"]},
        "slots": slot_list,
        "files": slot_files(pack),
        **editing_data(P, slot_list),
        "roles": role_map,
        "tools": tools(),
        "tool_info": tool_info(),
        "tool_settings": tool_settings(),
        "settings": settings_values({"DC_PARAMS_PRIMER_ENABLED"}),
        "parameter_access": parameter_access(),
        "primer": primer_data(),
        "env_vars": env_names(),
        "env_sections": env_sections(),
        "viewer": viewer_controls(),
    }


def build(pack_dir: Path | None = None) -> dict:
    """The Studio's data for the setup in *pack_dir*: :func:`static_data`
    plus ``where`` / ``prompts`` (the base combination) / ``align``, from
    seven child processes run in parallel."""
    out = run_children({"static": ["static"], **ASSEMBLY_JOBS}, pack_dir)
    data = out.pop("static")
    data["where"] = where(out)
    data["prompts"] = base_prompts(out)
    data["align"] = alignment(out)
    return data


def check_tools(pack_dir: Path) -> list[str]:
    """Every problem the engine finds in the tools of the setup copy in
    *pack_dir* (``engine/pack_tools.py``: each manifest, who owns which
    text, the geometry tools) -- [] when it would load them.  For the
    Studio's tool editor (P6c): a changed manifest is checked in a copy
    before it is written.  The engine's kept file data is cleared before
    and after: a copy keeps the files' times."""
    import yaml

    import config
    from engine import pack, pack_tools

    def clear():
        for cache in (pack._folders_cache, pack._claims_cache, pack._names_cache,
                      pack_tools._manifests_cache):
            cache.clear()
    real = config.DC_PACK_DIR
    config.DC_PACK_DIR = pack_dir
    clear()
    try:
        pack_tools._read_manifests()
        return []
    except pack_tools.PackToolError as exc:
        return [ln for ln in str(exc).split("\n") if ln.strip()]
    except yaml.YAMLError as exc:
        return [f"a tool.yaml is not valid YAML: {exc}"]
    finally:
        config.DC_PACK_DIR = real
        clear()


def check_setup(pack_dir: Path) -> list[str]:
    """Why the engine could not show the setup in *pack_dir* (a setup file
    being opened, P7-2): its format, its ``parameters.json``, its tools --
    [] when it can.  The rest is Validate's."""
    import yaml

    from engine import pack
    from engine import parameters as ep
    try:
        problem = pack.format_problem(pack_dir)
    except yaml.YAMLError as exc:
        return [f"pack.yaml is not valid YAML: {exc}"]
    if problem:
        return [problem]
    try:
        spec = json.loads((pack_dir / "parameters.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ["parameters.json is missing"]
    except ValueError as exc:
        return [f"parameters.json is not valid JSON: {exc}"]
    return [f"parameters.json: {p}" for p in ep.validate(spec)] + check_tools(pack_dir)


def checker() -> int:
    """The engine's own parameter check (``engine/parameters.py``
    ``validate``) for the Studio's parameter editor (P6b): one JSON line in
    -- ``{"parameters": <a parameters.json>}`` --, one line out --
    ``{"problems": [...]}`` --, until stdin closes.  The check reads nothing
    but the file it is given, so one process answers every change.  Also
    ``{"tools_check": <folder>}`` (:func:`check_tools`) and
    ``{"setup_check": <folder>}`` (:func:`check_setup`)."""
    load_engine()
    from engine import parameters as ep
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            job = json.loads(line)
            if "tools_check" in job:
                out = {"problems": check_tools(Path(job["tools_check"]))}
            elif "setup_check" in job:
                out = {"problems": check_setup(Path(job["setup_check"]))}
            else:
                out = {"problems": ep.validate(job["parameters"])}
        except Exception as exc:                            # noqa: BLE001
            out = {"problems": [f"the check failed: {type(exc).__name__}: {exc}"]}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()
    return 0


def _main(argv: list[str]) -> int:
    if argv[:1] in (["static"], ["assemble"], ["view"]):
        hold_files()
    if argv[:1] == ["static"]:
        payload = static_data()
    elif argv[:1] == ["assemble"] and len(argv) == 3:
        payload = assemble(argv[1], int(argv[2]))
    elif argv[:1] == ["view"] and len(argv) == 2:
        payload = view(json.loads(Path(argv[1]).read_text(encoding="utf-8")))
    elif argv[:1] == ["worker"]:
        return worker()
    elif argv[:1] == ["checker"]:
        return checker()
    else:
        sys.stderr.write(__doc__.split("\n\n")[1] + "\n")
        return 2
    sys.stdout.buffer.write(json.dumps(payload, default=str).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
