"""One-shot helper: bake the workflow-generated descriptions into
``embeddings.json``.

Reads the Claude Code workflow output file (the parallel sketch-
description run) and writes a clean ``embeddings.json`` with the
visual + semantic descriptions populated and all vector fields empty.
Run :func:`rebuild_index` afterwards to fill in the vectors.

Usage::

    python -m extra_utilities.embedding_tests.bake_descriptions <workflow_output_path>

If ``<workflow_output_path>`` is omitted, the script looks for the
hard-coded default path from this session's workflow run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

THIS_DIR        = Path(__file__).parent
SKETCHES_DIR    = THIS_DIR / "sketches"
EMBEDDINGS_JSON = THIS_DIR / "embeddings.json"

DEFAULT_WORKFLOW_OUTPUT = Path(
    r"C:\Users\vince\AppData\Local\Temp\claude"
    r"\C--Users-vince-MT-Coding-tests-test11-v9-git--claude-worktrees-silly-black-743a7c"
    r"\e4967989-40b0-4034-bc6b-7043f775227f\tasks\w6rtqdaqf.output"
)


def bake(workflow_output_path: Path) -> dict:
    data = json.loads(workflow_output_path.read_text(encoding="utf-8"))
    result = data.get("result") or []
    desc_by_name: dict[str, dict] = {}
    for row in result:
        if not isinstance(row, dict):
            continue
        nm = row.get("name")
        if isinstance(nm, str) and nm.strip():
            desc_by_name[nm] = row

    sketches = sorted(
        p.name for p in SKETCHES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"}
    )

    images = []
    missing = []
    for i, name in enumerate(sketches, start=1):
        row = desc_by_name.get(name)
        if row is None:
            missing.append(name)
            vd = sd = ""
        else:
            vd = (row.get("visual_description")   or "").strip()
            sd = (row.get("semantic_description") or "").strip()
        images.append({
            "index":                   i,
            "name":                    name,
            "type":                    "sketch",
            "visual_description":      vd,
            "semantic_description":    sd,
            "voyage_vector":           [],
            "visual_caption_vector":   [],
            "semantic_caption_vector": [],
        })

    emb = {
        "schema_version": 1,
        "generated_at":   None,
        "model_versions": {},
        "images":         images,
    }
    EMBEDDINGS_JSON.write_text(
        json.dumps(emb, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "n_baked":  len(images) - len(missing),
        "missing":  missing,
        "n_images": len(images),
        "json":     str(EMBEDDINGS_JSON),
    }


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_WORKFLOW_OUTPUT
    if not path.is_file():
        print(f"Workflow output not found: {path}", file=sys.stderr)
        sys.exit(1)
    out = bake(path)
    print(json.dumps(out, indent=2, ensure_ascii=False))
