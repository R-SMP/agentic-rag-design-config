"""Local browser interface -- a thin client over the CLI engine.

Deliberately NOT part of the deployed web app: it binds to localhost, has no
authentication, no database and no session state, and it imports the same
``pipeline.run`` the CLI calls.  Nothing about the propeller lives here; if this
file were deleted the tool would still work from the command line.

Renders run on a worker thread and the page polls for progress, so a turntable
of twenty frames reports as it goes instead of hanging a request for a minute.
"""

from __future__ import annotations

import json
import threading
import traceback
import uuid
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from propeller_studio import params as P
from propeller_studio import pipeline
from propeller_studio import settings as S

STATIC = Path(__file__).resolve().parent / "static"

_jobs = {}
_jobs_lock = threading.Lock()


def _job_update(job_id, **fields):
    with _jobs_lock:
        _jobs.setdefault(job_id, {}).update(fields)


def _job_log(job_id, line):
    with _jobs_lock:
        _jobs.setdefault(job_id, {}).setdefault("log", []).append(line)


def create_app(out_root=None):
    app = Flask(__name__, static_folder=None)
    out_root = Path(out_root) if out_root else pipeline.DEFAULT_OUT_ROOT

    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/static/<path:name>")
    def static_files(name):
        return send_from_directory(STATIC, name)

    @app.get("/api/schema")
    def schema():
        """Everything the form needs to build itself: no duplicated schema."""
        return jsonify({
            "params": [
                {"name": s.name, "label": s.label, "unit": s.unit, "lo": s.lo,
                 "hi": s.hi, "integer": s.integer, "group": s.group}
                for s in P.PARAM_SPECS
            ],
            "defaults_params": P.DEFAULT_PARAMS,
            "defaults": S.defaults(),
            "presets": sorted(f.stem for f in S.PRESET_DIR.glob("*.json")),
            "named_views": S.NAMED_VIEWS,
            "lighting_presets": list(S.LIGHTING_PRESETS),
            "background_modes": list(S.BACKGROUND_MODES),
            "projections": list(S.PROJECTIONS),
            "layouts": list(S.DRAWING_LAYOUTS),
            "sheet_sizes": sorted(S.SHEET_SIZES),
        })

    @app.get("/api/preset/<name>")
    def get_preset(name):
        try:
            return jsonify(S.load_preset(name))
        except S.SettingsError as exc:
            return jsonify({"error": str(exc)}), 404

    @app.post("/api/preset/<name>")
    def save_preset(name):
        safe = pipeline.slugify(name, "preset")
        path = S.PRESET_DIR / (safe + ".json")
        path.write_text(json.dumps(request.get_json(force=True), indent=2),
                        encoding="utf-8")
        return jsonify({"saved": safe})

    @app.post("/api/render")
    def start_render():
        payload = request.get_json(force=True) or {}
        job_id = uuid.uuid4().hex[:12]
        _job_update(job_id, status="running", log=[], manifest=None, error=None)

        def work():
            try:
                manifest = pipeline.run(
                    payload.get("params") or {},
                    payload.get("settings") or {},
                    out_root=out_root,
                    slug=payload.get("slug"),
                    title=payload.get("title"),
                    strict_range=not payload.get("allow_out_of_range"),
                    progress=lambda m: _job_log(job_id, m),
                    rhino=payload.get("rhino") or {},
                )
                manifest["run_url_base"] = "/api/file/%s" % manifest["run"]
                _job_update(job_id, status="done", manifest=manifest)
            except Exception as exc:                    # surfaced to the page
                _job_log(job_id, "FAILED: %s" % exc)
                _job_update(job_id, status="error", error=str(exc),
                            traceback=traceback.format_exc())

        threading.Thread(target=work, daemon=True).start()
        return jsonify({"job": job_id})

    @app.get("/api/job/<job_id>")
    def job_status(job_id):
        with _jobs_lock:
            job = dict(_jobs.get(job_id) or {})
        if not job:
            return jsonify({"error": "unknown job"}), 404
        return jsonify(job)

    @app.get("/api/runs")
    def runs():
        out = []
        if out_root.is_dir():
            for d in sorted(out_root.iterdir(), reverse=True):
                mf = d / "manifest.json"
                if mf.is_file():
                    try:
                        m = json.loads(mf.read_text(encoding="utf-8"))
                    except ValueError:
                        continue
                    out.append({
                        "run": d.name, "backend": m.get("backend"),
                        "created": m.get("created"),
                        "renders": [r["file"] for r in m.get("renders", [])],
                        "drawing": bool(m.get("drawing")),
                    })
                if len(out) >= 40:
                    break
        return jsonify(out)

    @app.get("/api/file/<run>/<path:name>")
    def run_file(run, name):
        # Resolve and confine: a run name is user-supplied, and ".." in it must
        # not reach outside the output root.
        base = (out_root / run).resolve()
        if out_root.resolve() not in base.parents and base != out_root.resolve():
            return jsonify({"error": "outside the output root"}), 400
        return send_from_directory(base, name)

    return app


def serve(host="127.0.0.1", port=8765, open_browser=True, out_root=None):
    app = create_app(out_root)
    url = "http://%s:%d/" % (host, port)
    print("propeller_studio GUI on %s   (Ctrl+C to stop)" % url)
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=port, debug=False, threaded=True)
    return 0
