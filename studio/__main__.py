"""python -m studio [--pack <folder>] [--host 127.0.0.1] [--port 8770] [--workers 2]
python -m studio --online [--workspace <folder>] [--pack <example>] [--host 0.0.0.0]
python -m studio validate [--pack <folder>] [--json <report.json>]
python -m studio prepare [--report <report.json>]

Starts the Studio on this computer and prints its address -- or validates a
setup (``studio/validate.py``) and prints the report -- or, in a folder made
by Download full package, makes it ready to commit and prints the git
commands (``studio/prepare.py``; it never runs git).

``--online`` (MAS-blueprint P7b-lite, ``studio/HOSTING.md``): the Studio for
everyone with the access code in ``INVITE_CODE`` (required), on ONE shared
setup in ``<workspace>/dc_pack`` -- a copy of ``--pack`` (the example; else
:func:`example_pack`) when the workspace has none, and "Start from a
configurator" replaces it with another of ``setups/``.  ``CONFIGURATOR_URL``
links the landing page to the configurator.  The port is ``PORT`` when set
(Railway sets it).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def default_pack() -> Path:
    """The engine's own choice (config.py, ``engine/setups.py``):
    ``DC_PACK_DIR``, taken from the project root when relative, else the
    configurator the app loaded last, else ``setups/propeller``."""
    from engine.setups import resolve
    return resolve(REPO, os.getenv("DC_PACK_DIR"))


def example_pack() -> Path:
    """What a shared setup starts from (online, and the Studio inside the
    app): ``DC_PACK_DIR`` when set, else ``setups/propeller`` -- a package's
    one configurator -- never the one the app loaded last."""
    from engine.setups import default_setup, resolve
    value = os.getenv("DC_PACK_DIR")
    return resolve(REPO, value) if value else default_setup(REPO)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["validate"]:
        from studio.validate import main as validate
        return validate(argv[1:])
    if argv[:1] == ["prepare"]:
        from studio.prepare import main as prepare
        return prepare(argv[1:])
    ap = argparse.ArgumentParser(
        prog="python -m studio",
        description="The MAS Studio (MAS-blueprint P5-P6c): a setup's "
                    "parameters, text fields, tools and settings, where each "
                    "text lands in the agents' prompts, and every agent's "
                    "prompt and tools under any choice of settings, as the "
                    "engine assembles them; it edits the text fields, the "
                    "parameters, the agent access and the tools, in the "
                    "setup's own files.")
    ap.add_argument("--pack", type=Path, default=None,
                    help="the setup folder (default: DC_PACK_DIR, else the configurator the app "
                         "loaded last, else setups/propeller/ of this repository; online: "
                         "DC_PACK_DIR, else setups/propeller/)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT") or 8770))
    ap.add_argument("--online", action="store_true",
                    help="the online Studio: an access code (INVITE_CODE) and one shared setup")
    ap.add_argument("--workspace", type=Path, default=None,
                    help="online: the folder of the shared setup (default: workspace/ of this "
                         "repository); it gets a copy of --pack when it has none")
    ap.add_argument("--workers", type=int, default=2,
                    help="engine processes kept waiting for the prompt viewer (default 2)")
    args = ap.parse_args(argv)

    pack = (args.pack.resolve() if args.pack
            else (example_pack() if args.online else default_pack()).resolve())
    if not (pack / "pack.yaml").is_file():
        print(f"{pack} is not a setup folder: it has no pack.yaml.", file=sys.stderr)
        return 2

    code, example = None, None
    if args.online:
        code = (os.getenv("INVITE_CODE") or "").strip()
        if not code:
            print("The online Studio needs an access code: set INVITE_CODE.", file=sys.stderr)
            return 2
        example = pack
        workspace = (args.workspace or REPO / "workspace").resolve()
        from studio.embedded import shared_setup
        pack = shared_setup(workspace, example)

    import uvicorn
    from studio.server import create_app

    print(f"MAS Studio{' (online)' if args.online else ''}: http://{args.host}:{args.port}/   "
          f"(setup: {pack})", flush=True)
    uvicorn.run(create_app(pack, workers=max(0, args.workers), online=args.online,
                           access_code=code, example_dir=example,
                           configurator_url=(os.getenv("CONFIGURATOR_URL") or "").strip() or None),
                host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
