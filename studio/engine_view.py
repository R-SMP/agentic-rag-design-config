"""What the Studio shows of a setup, computed by the engine itself.

    python -m studio.engine_view static
    python -m studio.engine_view assemble <base|all_on> <7|5|3>

MAS-blueprint P5a.  The Studio's screens read one dict, :func:`build`:

* **static** -- the parameters (``dc_pack/parameters.json``), every text
  field of the pack with its three topology texts and its per-agent copies
  (read through the slot registry, ``engine/pack.py``), the role map, the
  tools and their settings, the parameter-access grid, the secrets' names;
* **assembled** -- every agent's real system prompt, topologies 7 / 5 / 3,
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

The Studio draft (``extra_utilities/docs/studio_draft/build_draft_data.py``)
builds its data from the same functions.
"""

from __future__ import annotations

import ast
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


def load_engine():
    """Make the engine's prompt layer importable in this (child) process:
    the repo and the assembler's folders on sys.path, the runtime packages
    stubbed (``extra_utilities/prompt_pdf/bootstrap.py``)."""
    for p in ("extra_utilities/scripts", "extra_utilities/prompt_pdf", "."):
        sys.path.insert(0, str(REPO / p))
    sys.modules["simplejson"] = None          # type: ignore[assignment]
    sys.modules["chardet"] = None             # type: ignore[assignment]
    import bootstrap
    bootstrap.install()


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
    import prompt_matrix as PM
    # The same combination set-up as the prompt matrix, including the
    # parameter-access cells its old setting names stand for.
    PM.apply_config(combo)
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

    marked = T._assemble(topology)["prompts"]
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


def parameters(pack) -> dict:
    """The parameter set from its single source, ``dc_pack/parameters.json``
    (``engine/parameters.py``), plus each parameter's unit and description
    as the agents' hand-written ``$parameter_list`` text words them.
    ``copies_agree``: that text gives the same range as the file."""
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
            "min": p["min"], "max": p["max"], "step": p["step"], "default": p["default"],
            "copies_agree": (a.get("min"), a.get("max")) == (float(p["min"]), float(p["max"])),
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


def slots(P, pack_origin: dict, roles: dict, order: dict | None = None) -> list:
    """Every pack $slot with its three topology texts and per-agent copies,
    read from dc_pack/ through the registry (engine/pack.py naming).  A slot a
    tool owns is read from that tool's prompts/ folder and names its owner.
    *order*: slot -> its place in its section (default: the registry's)."""
    pack = P._pack
    claims = pack.tool_claims()
    order = registry_order(pack) if order is None else order
    agents = sorted({a for t in roles["roster"].values() for a in t} | {"database_handler"})
    out = []
    for slot, spec in sorted(pack.slots(source="pack", use="prompt").items()):
        folder = (pack.tool_prompts_dir(claims[slot]) if slot in claims
                  else pack.fragments_dir() / spec["folder"])
        overlay = spec.get("missing") == "empty"
        vals = ({"7": "", "5": "", "3": ""} if overlay
                else _topology_texts(pack, folder, slot, spec))
        variants = []
        for ag in agents:
            v = _topology_texts(pack, folder, f"{slot}@{ag}", spec)
            if any(x is not None for x in v.values()):
                variants.append({"agent": ag, "values": v})
        present = [x for x in vals.values() if x is not None]
        out.append({
            "slot": slot, "origin": pack_origin.get(slot, "dc"),
            "owner": claims.get(slot),
            "kind": spec["kind"],
            "section": spec.get("section", "other"), "order": order.get(slot, 999),
            "description": spec.get("description", "") or (
                "Per-agent overlay: each agent's own text for this tool; "
                "agents without a file get nothing." if overlay else ""),
            "values": vals,
            "linked": overlay or (len(present) == 3 and len(set(present)) == 1),
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
        ref = m.get("build") or m.get("entrypoint")
        out.append({"name": name, "display": m["display_name"], "kind": m["kind"],
                    "file": f"dc_pack/tools/{name}/{ref.split(':')[0]}",
                    "description": m["description"],
                    "owns": list(m.get("prompt_slots") or []),
                    "list_order": m.get("list_order")})
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


def static_data() -> dict:
    """Everything the Studio shows that is read, not assembled."""
    load_engine()
    from agents.shared import prompts as P
    from engine import parameters as ep
    pack = P._pack
    role_map = roles()
    return {
        "pack": {"name": pack.read("dc_name", 7),
                 "domain": pack.read("domain_description", 7),
                 "parameter_count": P._GENERATED_SLOTS["parameter_count"]()},
        "pack_dir": str(pack.pack_dir()),
        "parameters": parameters(pack),
        "group_images": {g["id"]: g.get("image") for g in ep.load()["groups"]},
        "slots": slots(P, pack_slots(P), role_map),
        "files": slot_files(pack),
        "roles": role_map,
        "tools": tools(),
        "tool_info": tool_info(),
        "tool_settings": tool_settings(),
        "settings": settings_values({"DC_PARAMS_PRIMER_ENABLED"}),
        "parameter_access": parameter_access(),
        "env_vars": env_names(),
        "env_sections": env_sections(),
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


def _main(argv: list[str]) -> int:
    if argv[:1] == ["static"]:
        payload = static_data()
    elif argv[:1] == ["assemble"] and len(argv) == 3:
        payload = assemble(argv[1], int(argv[2]))
    else:
        sys.stderr.write(__doc__.split("\n\n")[1] + "\n")
        return 2
    sys.stdout.buffer.write(json.dumps(payload).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
