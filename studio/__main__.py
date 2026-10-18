"""python -m studio [--pack <folder>] [--host 127.0.0.1] [--port 8770] [--workers 2]

Starts the Studio on this computer and prints its address.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def default_pack() -> Path:
    """The engine's own choice (config.py): ``DC_PACK_DIR``, taken from the
    project root when relative, else ``dc_pack/``."""
    p = Path(os.getenv("DC_PACK_DIR") or "dc_pack")
    return p if p.is_absolute() else REPO / p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m studio",
        description="The MAS Studio, read-only (MAS-blueprint P5): a setup's "
                    "parameters, text fields, tools and settings, where each "
                    "text lands in the agents' prompts, and every agent's "
                    "prompt and tools under any choice of settings, as the "
                    "engine assembles them.")
    ap.add_argument("--pack", type=Path, default=None,
                    help="the setup folder (default: dc_pack/ of this repository, "
                         "or DC_PACK_DIR)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--workers", type=int, default=2,
                    help="engine processes kept waiting for the prompt viewer (default 2)")
    args = ap.parse_args(argv)

    pack = (args.pack.resolve() if args.pack else default_pack().resolve())
    if not (pack / "pack.yaml").is_file():
        print(f"{pack} is not a setup folder: it has no pack.yaml.", file=sys.stderr)
        return 2

    import uvicorn
    from studio.server import create_app

    print(f"MAS Studio: http://{args.host}:{args.port}/   (setup: {pack})", flush=True)
    uvicorn.run(create_app(pack, workers=max(0, args.workers)), host=args.host,
                port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
