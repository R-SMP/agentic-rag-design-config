"""Render one PNG per step of the Studio process, plus an overview image.

    py -3.13 extra_utilities/docs/studio_draft/shoot.py [step-id ...]

Headless Microsoft Edge opens index.html at each step's address (hash route)
with a throw-away profile, so it never touches the user's own browser.  Run
build_draft_data.py first.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMAGES = HERE / "images"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
SIZE = (1480, 940)

# (id, route, caption) -- in the order a user meets them
STEPS = [
    ("01_landing", "/landing", "Open the Studio: three ways in"),
    ("02_create", "/start", "Create your own: example or blank"),
    ("03_import", "/import?file=1", "Or import a setup file"),
    ("04_parameters", "/studio/parameters?param=middlePos", "Parameters: one list for everything"),
    ("05_examples_grid", "/studio/examples?field=past_run_lookup_examples", "Text fields: 3 / 5 / 7 grid + where it lands"),
    ("06_description_unlinked", "/studio/description?field=hard_constraints_dc", "Per-topology and per-agent texts"),
    ("07_outputs_vocabulary", "/studio/outputs?field=output_images", "Outputs and vocabulary"),
    ("08_blank_start", "/studio/examples?blank=1&field=past_run_lookup_examples", "Starting blank: the propeller as reference"),
    ("09_tools_new_tool", "/studio/tools?modal=newtool", "Tools: add one (never run on the site)"),
    ("10_agent_access", "/studio/access", "Who sees the parameter list"),
    ("11_settings_secrets", "/studio/settings", "Settings, and the secrets to set later"),
    ("12_prompt_viewer", "/studio/prompts?topo=7&agent=dc_output_inspector", "Prompt viewer: every prompt, by origin"),
    ("13_validate", "/studio/validate", "Validate: static checks + every prompt"),
    ("14_download", "/studio/validate?modal=download", "Download: setup file or full package"),
    ("15_local_test_tool", "/studio/tools?mode=local&test=render_blade_sections&scroll=330", "On your own computer: Test tool works"),
]


def shoot(step_id: str, route: str, profile: str) -> Path:
    out = IMAGES / f"{step_id}.png"
    url = (HERE / "index.html").as_uri() + "#" + route
    cmd = [str(EDGE), "--headless=new", "--disable-gpu", "--hide-scrollbars",
           "--no-first-run", "--no-default-browser-check", f"--user-data-dir={profile}",
           f"--window-size={SIZE[0]},{SIZE[1]}", "--virtual-time-budget=8000",
           f"--screenshot={out}", url]
    subprocess.run(cmd, capture_output=True, timeout=120)
    if not out.is_file():
        raise SystemExit(f"no screenshot for {step_id}")
    return out


def overview(paths: list[tuple[str, str, Path]]) -> Path:
    from PIL import Image, ImageDraw, ImageFont
    cols, tw = 5, 420
    th = round(tw * SIZE[1] / SIZE[0])
    pad, cap, top = 26, 40, 74
    rows = (len(paths) + cols - 1) // cols
    W = pad + cols * (tw + pad)
    H = top + rows * (th + cap + pad) + 10
    img = Image.new("RGB", (W, H), (30, 31, 36))
    d = ImageDraw.Draw(img)
    try:
        f_title = ImageFont.truetype("segoeuib.ttf", 26)
        f_cap = ImageFont.truetype("segoeui.ttf", 16)
        f_num = ImageFont.truetype("segoeuib.ttf", 16)
    except OSError:
        f_title = f_cap = f_num = ImageFont.load_default()
    d.text((pad, 22), "MAS Studio \u2014 the process (draft, real propeller data)", font=f_title, fill=(230, 232, 236))
    for i, (sid, caption, p) in enumerate(paths):
        r, c = divmod(i, cols)
        x = pad + c * (tw + pad)
        y = top + r * (th + cap + pad)
        thumb = Image.open(p).convert("RGB").resize((tw, th), Image.LANCZOS)
        img.paste(thumb, (x, y))
        d.rectangle([x - 1, y - 1, x + tw, y + th], outline=(58, 61, 70))
        d.ellipse([x, y + th + 9, x + 24, y + th + 33], fill=(74, 140, 255))
        n = str(i + 1)
        d.text((x + 12, y + th + 21), n, font=f_num, fill=(255, 255, 255), anchor="mm")
        d.text((x + 32, y + th + 11), caption, font=f_cap, fill=(200, 204, 211))
        if c < cols - 1 and i < len(paths) - 1:
            ax = x + tw + 5
            ay = y + th // 2
            d.line([ax, ay, ax + pad - 10, ay], fill=(74, 140, 255), width=3)
            d.polygon([(ax + pad - 9, ay - 6), (ax + pad - 3, ay), (ax + pad - 9, ay + 6)], fill=(74, 140, 255))
    out = IMAGES / "00_overview.png"
    img.save(out, optimize=True)
    return out


def main(argv: list[str]) -> int:
    if not EDGE.is_file():
        raise SystemExit(f"Microsoft Edge not found at {EDGE}")
    IMAGES.mkdir(exist_ok=True)
    wanted = set(argv)
    done = []
    with tempfile.TemporaryDirectory(prefix="studio_shoot_") as profile:
        for sid, route, caption in STEPS:
            p = IMAGES / f"{sid}.png"
            if not wanted or sid in wanted:
                p = shoot(sid, route, profile)
                print(f"  {p.name}")
            done.append((sid, caption, p))
    if all(p.is_file() for _, _, p in done):
        print(f"  {overview(done).name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
