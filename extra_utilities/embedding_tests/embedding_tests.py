"""Core module for the embedding-tests harness.

Loads cached descriptions + vectors from ``embeddings.json`` once, then
serves search requests entirely from in-memory state.  Also owns the
rebuild pipeline (regenerate descriptions + vectors for every sketch).

The web layer (``web_app.py``) calls into this module only — it never
imports voyage_client / caption_generator directly.

CLI usage
---------
::

    python -m extra_utilities.embedding_tests.embedding_tests rebuild

Public surface
--------------
* :func:`get_manifest`        — reference-table data for the UI
* :func:`search_text`         — text query → top-3 per method
* :func:`search_image`        — image query → top-3 per method
* :func:`rebuild_index`       — re-do all descriptions + vectors
* :func:`append_search_log`   — log a single search to searches.jsonl
* :func:`read_search_log`     — tail searches.jsonl for the side panel
* :func:`get_sketch_path`     — resolve a sketch name → absolute path
"""
from __future__ import annotations

import collections
import json
import math
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

THIS_DIR        = Path(__file__).parent
SKETCHES_DIR    = THIS_DIR / "sketches"
EMBEDDINGS_JSON = THIS_DIR / "embeddings.json"
SEARCHES_LOG    = THIS_DIR / "searches.jsonl"

OPENAI_EMBED_MODEL = "text-embedding-3-large"
OPENAI_EMBED_DIMS  = 1024

TOP_K = 3

ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg"}


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

@dataclass
class SketchEntry:
    index: int
    name: str
    type: str = "sketch"
    visual_description: str = ""
    semantic_description: str = ""
    voyage_vector: list[float] = field(default_factory=list)
    visual_caption_vector: list[float] = field(default_factory=list)
    semantic_caption_vector: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index":                   self.index,
            "name":                    self.name,
            "type":                    self.type,
            "visual_description":      self.visual_description,
            "semantic_description":    self.semantic_description,
            "voyage_vector":           self.voyage_vector,
            "visual_caption_vector":   self.visual_caption_vector,
            "semantic_caption_vector": self.semantic_caption_vector,
        }


_state_lock = threading.Lock()
_state: dict[str, Any] = {
    "loaded":          False,
    "schema_version":  1,
    "generated_at":    None,
    "model_versions":  {},
    "images":          [],   # list[SketchEntry]
}


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def _list_sketch_filenames() -> list[str]:
    """Sorted list of image filenames in ``sketches/``."""
    if not SKETCHES_DIR.is_dir():
        return []
    keep = []
    for p in sorted(SKETCHES_DIR.iterdir()):
        if p.is_file() and p.suffix.lower() in ALLOWED_SUFFIXES:
            keep.append(p.name)
    return keep


def _write_stub_if_missing() -> None:
    if EMBEDDINGS_JSON.is_file():
        return
    names = _list_sketch_filenames()
    stub = {
        "schema_version": 1,
        "generated_at":   None,
        "model_versions": {},
        "images": [
            {
                "index":                   i + 1,
                "name":                    n,
                "type":                    "sketch",
                "visual_description":      "",
                "semantic_description":    "",
                "voyage_vector":           [],
                "visual_caption_vector":   [],
                "semantic_caption_vector": [],
            }
            for i, n in enumerate(names)
        ],
    }
    EMBEDDINGS_JSON.write_text(
        json.dumps(stub, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_into_state() -> None:
    _write_stub_if_missing()
    data = json.loads(EMBEDDINGS_JSON.read_text(encoding="utf-8"))
    _state["schema_version"] = data.get("schema_version", 1)
    _state["generated_at"]   = data.get("generated_at")
    _state["model_versions"] = data.get("model_versions", {})
    # Defensive load: skip rows missing a usable name (single hand-edit
    # to embeddings.json shouldn't brick every endpoint), and coerce all
    # nullable fields to their sentinel default ("" or []) so downstream
    # ``.strip()`` / iteration cannot trip on ``None``.
    images: list[SketchEntry] = []
    for row in data.get("images", []):
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        images.append(SketchEntry(
            index=row.get("index", len(images) + 1),
            name=name,
            type=row.get("type") or "sketch",
            visual_description=row.get("visual_description") or "",
            semantic_description=row.get("semantic_description") or "",
            voyage_vector=row.get("voyage_vector") or [],
            visual_caption_vector=row.get("visual_caption_vector") or [],
            semantic_caption_vector=row.get("semantic_caption_vector") or [],
        ))
    _state["images"] = images
    _state["loaded"] = True


def ensure_loaded() -> None:
    if _state["loaded"]:
        return
    with _state_lock:
        if _state["loaded"]:
            return
        _load_into_state()


def _force_reload() -> None:
    """After rebuild_index overwrites embeddings.json."""
    with _state_lock:
        _state["loaded"] = False
        _load_into_state()


# --------------------------------------------------------------------------
# Reads for the UI
# --------------------------------------------------------------------------

def get_manifest() -> dict[str, Any]:
    """Reference-table data + model-version stamps for the UI."""
    ensure_loaded()
    return {
        "schema_version": _state["schema_version"],
        "generated_at":   _state["generated_at"],
        "model_versions": _state["model_versions"],
        "images": [
            {
                "index":                e.index,
                "name":                 e.name,
                "type":                 e.type,
                "visual_description":   e.visual_description,
                "semantic_description": e.semantic_description,
                "has_voyage_vector":           bool(e.voyage_vector),
                "has_visual_caption_vector":   bool(e.visual_caption_vector),
                "has_semantic_caption_vector": bool(e.semantic_caption_vector),
            }
            for e in _state["images"]
        ],
    }


def get_sketch_path(name: str) -> Path | None:
    """Resolve a sketch name to an absolute path; ``None`` if the file
    is not in the sketches/ folder.  Defends against path traversal —
    the name must be exactly one of the files we list."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    candidate = SKETCHES_DIR / name
    try:
        # Reject anything that escapes SKETCHES_DIR.
        candidate.resolve().relative_to(SKETCHES_DIR.resolve())
    except (ValueError, OSError):
        return None
    if not candidate.is_file():
        return None
    return candidate


# --------------------------------------------------------------------------
# Cosine
# --------------------------------------------------------------------------

def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na  = 0.0
    nb  = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na  += x * x
        nb  += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / math.sqrt(na * nb)


def _top_k_by_vector(query_vec: list[float],
                     attr: str,
                     k: int = TOP_K) -> list[dict[str, Any]]:
    ensure_loaded()
    if not query_vec:
        return []
    scored: list[tuple[float, SketchEntry]] = []
    for e in _state["images"]:
        stored = getattr(e, attr)
        if not stored:
            continue
        scored.append((_cosine(query_vec, stored), e))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [
        {"name": e.name, "score": round(float(score), 4), "index": e.index}
        for score, e in scored[:k]
    ]


# --------------------------------------------------------------------------
# OpenAI text embed
# --------------------------------------------------------------------------

_openai_client_lock = threading.Lock()
_openai_client = None


def _get_openai_client():
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    with _openai_client_lock:
        if _openai_client is not None:
            return _openai_client
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "openai SDK not installed."
            ) from exc
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set in the environment."
            )
        _openai_client = OpenAI(api_key=api_key, timeout=180.0)
        return _openai_client


def _openai_embed(text: str) -> list[float]:
    if not text or not text.strip():
        return []
    client = _get_openai_client()
    resp = client.embeddings.create(
        model=OPENAI_EMBED_MODEL,
        input=text,
        dimensions=OPENAI_EMBED_DIMS,
    )
    return list(resp.data[0].embedding)


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------

def _empty_per_method() -> dict[str, list]:
    return {"voyage": [], "caption_visual": [], "caption_semantic": []}


def search_text(query_text: str) -> dict[str, Any]:
    """Run a text query against all three methods.

    Failure isolation: if a single method's embedding call fails, that
    method's column returns an empty list with an error string; the
    other two still run.
    """
    ensure_loaded()
    text = (query_text or "").strip()
    if not text:
        return {"methods": _empty_per_method(), "errors": {}}

    methods: dict[str, list] = {}
    errors: dict[str, str] = {}

    # Voyage cross-modal: text → vector → cosine vs stored image vectors
    try:
        from .voyage_client import embed_text as voyage_embed_text
        q = voyage_embed_text(text)
        methods["voyage"] = _top_k_by_vector(q, "voyage_vector")
    except Exception as exc:
        methods["voyage"] = []
        errors["voyage"] = f"{type(exc).__name__}: {exc}"

    # Caption-based: text → OpenAI vector → cosine vs stored caption vectors
    try:
        q = _openai_embed(text)
        methods["caption_visual"]   = _top_k_by_vector(q, "visual_caption_vector")
        methods["caption_semantic"] = _top_k_by_vector(q, "semantic_caption_vector")
    except Exception as exc:
        methods.setdefault("caption_visual", [])
        methods.setdefault("caption_semantic", [])
        errors["caption_visual"]   = f"{type(exc).__name__}: {exc}"
        errors["caption_semantic"] = f"{type(exc).__name__}: {exc}"

    return {"methods": methods, "errors": errors}


def search_image(image_path: Path) -> dict[str, Any]:
    """Run an image query against all three methods.

    Returns ``methods`` (3 lanes) + ``errors`` (per-lane string) +
    ``captions_used`` (the two VLM captions that were embedded for the
    caption-based lanes — useful for the live log).
    """
    ensure_loaded()
    methods: dict[str, list] = {}
    errors: dict[str, str] = {}
    captions_used: dict[str, str] = {"visual": "", "semantic": ""}

    # Voyage image → vector → cosine vs stored
    try:
        from .voyage_client import embed_image as voyage_embed_image
        q = voyage_embed_image(Path(image_path), as_query=True)
        methods["voyage"] = _top_k_by_vector(q, "voyage_vector")
    except Exception as exc:
        methods["voyage"] = []
        errors["voyage"] = f"{type(exc).__name__}: {exc}"

    # Caption-based: VLM captions → OpenAI embed → cosine
    try:
        from .caption_generator import caption_visual
        captions_used["visual"] = caption_visual(Path(image_path))
        q = _openai_embed(captions_used["visual"])
        methods["caption_visual"] = _top_k_by_vector(q, "visual_caption_vector")
    except Exception as exc:
        methods["caption_visual"] = []
        errors["caption_visual"] = f"{type(exc).__name__}: {exc}"

    try:
        from .caption_generator import caption_semantic
        captions_used["semantic"] = caption_semantic(Path(image_path))
        q = _openai_embed(captions_used["semantic"])
        methods["caption_semantic"] = _top_k_by_vector(q, "semantic_caption_vector")
    except Exception as exc:
        methods["caption_semantic"] = []
        errors["caption_semantic"] = f"{type(exc).__name__}: {exc}"

    return {"methods": methods, "errors": errors, "captions_used": captions_used}


# --------------------------------------------------------------------------
# Rebuild
# --------------------------------------------------------------------------

def rebuild_index(*, regenerate_captions: bool = True,
                  preserve_existing_captions: bool = False) -> dict[str, Any]:
    """Recompute embeddings + (optionally) captions for every file in
    ``sketches/``.  Overwrites ``embeddings.json``.

    Parameters
    ----------
    regenerate_captions:
        When ``True`` (default), VLM captions are regenerated.  When
        ``False``, the existing captions from ``embeddings.json`` are
        reused (only the embedding vectors are recomputed).
    preserve_existing_captions:
        When ``True`` AND a sketch already has BOTH descriptions, those
        descriptions are kept verbatim — even if ``regenerate_captions``
        is ``True``.  This is the path used by the first bootstrap when
        the description-generation Workflow has already populated
        descriptions, so we don't pay for VLM calls twice.

    Returns
    -------
    Summary dict: ``{ok, n_images, errors[], generated_at,
    duration_seconds, captions_kept, captions_regenerated}``.
    """
    t0 = time.time()
    from .voyage_client import VOYAGE_MODEL, embed_image as voyage_embed_image
    from .caption_generator import (
        CAPTION_MODEL, caption_visual, caption_semantic,
    )

    names = _list_sketch_filenames()
    if not names:
        return {"ok": False,
                "error": "No sketches in sketches/ folder.",
                "duration_seconds": round(time.time() - t0, 2)}

    ensure_loaded()
    existing_by_name = {e.name: e for e in _state["images"]}
    rebuilt: list[SketchEntry] = []
    errors: list[dict[str, str]] = []
    captions_kept = 0
    captions_regenerated = 0

    for i, name in enumerate(names, start=1):
        path = SKETCHES_DIR / name
        prev = existing_by_name.get(name)

        already_has_both = bool(prev
                                and prev.visual_description.strip()
                                and prev.semantic_description.strip())

        if preserve_existing_captions and already_has_both:
            visual_desc   = prev.visual_description
            semantic_desc = prev.semantic_description
            captions_kept += 1
        elif regenerate_captions:
            # Track per-modality success so the summary counter only
            # increments when at least ONE caption was freshly produced
            # (otherwise the metric overstates against the errors[] list).
            new_visual = False
            new_semantic = False
            try:
                visual_desc = caption_visual(path)
                new_visual = True
            except Exception as exc:
                errors.append({"name": name, "step": "visual_caption",
                               "error": f"{type(exc).__name__}: {exc}"})
                visual_desc = prev.visual_description if prev else ""
            try:
                semantic_desc = caption_semantic(path)
                new_semantic = True
            except Exception as exc:
                errors.append({"name": name, "step": "semantic_caption",
                               "error": f"{type(exc).__name__}: {exc}"})
                semantic_desc = prev.semantic_description if prev else ""
            if new_visual or new_semantic:
                captions_regenerated += 1
        else:
            visual_desc   = prev.visual_description   if prev else ""
            semantic_desc = prev.semantic_description if prev else ""

        # Vectors
        try:
            voyage_vec = voyage_embed_image(path, as_query=False)
        except Exception as exc:
            errors.append({"name": name, "step": "voyage_embed",
                           "error": f"{type(exc).__name__}: {exc}"})
            voyage_vec = prev.voyage_vector if prev else []

        try:
            visual_caption_vec = _openai_embed(visual_desc) if visual_desc else []
        except Exception as exc:
            errors.append({"name": name, "step": "visual_caption_embed",
                           "error": f"{type(exc).__name__}: {exc}"})
            visual_caption_vec = prev.visual_caption_vector if prev else []

        try:
            semantic_caption_vec = _openai_embed(semantic_desc) if semantic_desc else []
        except Exception as exc:
            errors.append({"name": name, "step": "semantic_caption_embed",
                           "error": f"{type(exc).__name__}: {exc}"})
            semantic_caption_vec = prev.semantic_caption_vector if prev else []

        rebuilt.append(SketchEntry(
            index=i, name=name, type="sketch",
            visual_description=visual_desc,
            semantic_description=semantic_desc,
            voyage_vector=voyage_vec,
            visual_caption_vector=visual_caption_vec,
            semantic_caption_vector=semantic_caption_vec,
        ))

    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    data = {
        "schema_version": 1,
        "generated_at":   generated_at,
        "model_versions": {
            "voyage":                VOYAGE_MODEL,
            "caption_vlm":           CAPTION_MODEL,
            "caption_text_embedder": f"{OPENAI_EMBED_MODEL}/{OPENAI_EMBED_DIMS}",
        },
        "images": [e.to_dict() for e in rebuilt],
    }
    EMBEDDINGS_JSON.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    _force_reload()

    return {
        "ok":                   True,
        "n_images":             len(rebuilt),
        "errors":               errors,
        "generated_at":         generated_at,
        "duration_seconds":     round(time.time() - t0, 2),
        "captions_kept":        captions_kept,
        "captions_regenerated": captions_regenerated,
    }


def stamp_descriptions(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Bake a batch of (name, visual_description, semantic_description)
    rows into ``embeddings.json`` WITHOUT touching any vector fields.

    Used by the one-shot bootstrap that imports the descriptions
    produced by the offline Workflow.
    """
    ensure_loaded()
    existing_by_name = {e.name: e for e in _state["images"]}
    updates: list[SketchEntry] = []
    stamped_names: list[str] = []
    skipped: list[str] = []

    for row in rows:
        name = row.get("name")
        if not name or name not in existing_by_name:
            skipped.append(name or "<unnamed>")
            continue
        prev = existing_by_name[name]
        prev.visual_description   = (row.get("visual_description") or "").strip()
        prev.semantic_description = (row.get("semantic_description") or "").strip()
        stamped_names.append(name)

    # Rewrite embeddings.json
    data = {
        "schema_version": _state["schema_version"],
        "generated_at":   _state["generated_at"],
        "model_versions": _state["model_versions"],
        "images": [e.to_dict() for e in _state["images"]],
    }
    EMBEDDINGS_JSON.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    _force_reload()
    return {"ok": True, "stamped": stamped_names, "skipped": skipped}


# --------------------------------------------------------------------------
# Search log
# --------------------------------------------------------------------------

# Caps on the search log file.  When it exceeds SEARCHES_LOG_MAX_BYTES
# the next append trims the file in place to its last
# SEARCHES_LOG_KEEP_TAIL lines.  Pair of bounds prevents unbounded disk
# growth + unbounded full-file read in read_search_log.
SEARCHES_LOG_MAX_BYTES = 5 * 1024 * 1024
SEARCHES_LOG_KEEP_TAIL = 1000


def _rotate_search_log(*, keep_last_n: int) -> None:
    """Trim ``searches.jsonl`` in-place to its last ``keep_last_n`` lines.

    Best-effort: missing file or transient OSError silently no-ops; the
    next append will recreate / overwrite as needed.
    """
    try:
        with SEARCHES_LOG.open("r", encoding="utf-8") as f:
            tail = collections.deque(f, maxlen=keep_last_n)
    except OSError:
        return
    try:
        with SEARCHES_LOG.open("w", encoding="utf-8") as f:
            f.writelines(tail)
    except OSError:
        pass


def append_search_log(entry: dict[str, Any]) -> None:
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **entry,
    }
    # Cheap rotation check: one stat() per call.  When the cap is hit
    # we rewrite the file to its last SEARCHES_LOG_KEEP_TAIL lines
    # before the new append.
    try:
        if (SEARCHES_LOG.is_file()
                and SEARCHES_LOG.stat().st_size > SEARCHES_LOG_MAX_BYTES):
            _rotate_search_log(keep_last_n=SEARCHES_LOG_KEEP_TAIL)
    except OSError:
        pass
    try:
        with SEARCHES_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_search_log(limit: int = 50) -> list[dict[str, Any]]:
    """Return the last ``limit`` log entries.

    Uses ``collections.deque(f, maxlen=limit)`` so memory is O(limit)
    regardless of file size.  Disk I/O is still O(file_size), but
    bounded by the rotation cap above.
    """
    if not SEARCHES_LOG.is_file():
        return []
    try:
        with SEARCHES_LOG.open("r", encoding="utf-8") as f:
            tail_lines = collections.deque(f, maxlen=max(1, int(limit)))
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in tail_lines:
        s = line.strip()
        if not s:
            continue
        try:
            out.append(json.loads(s))
        except json.JSONDecodeError:
            continue
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _cli_rebuild(preserve: bool = False) -> int:
    result = rebuild_index(regenerate_captions=True,
                           preserve_existing_captions=preserve)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def _cli_search(text: str) -> int:
    print(json.dumps(search_text(text), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "rebuild":
        sys.exit(_cli_rebuild(preserve=False))
    elif cmd == "rebuild-preserve":
        sys.exit(_cli_rebuild(preserve=True))
    elif cmd == "search":
        q = " ".join(sys.argv[2:])
        sys.exit(_cli_search(q))
    else:
        print(__doc__)
        sys.exit(0)
