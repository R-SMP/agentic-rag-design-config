# -*- coding: utf-8 -*-
"""A manual upload keeps the compression degree its uploader chose.

The bug this pins, in three layers:

1. ``manual_entry`` wrote its sidecar with a ``degree`` key while
   ``image_compression.read_degree`` reads ``degree_pct`` -- so every
   percentage chosen in the manual-entry form parsed back as None and
   was silently replaced by the size-based default.
2. The attempt COPY of the image got no sidecar at all, so the same
   upload compressed differently under ``user_inputs/`` and ``attempts/``.
3. ``is_render`` is decided by LOCATION (anything under ``attempts/``)
   while a GENERATED render is decided by its canonical FILENAME.  A
   manual upload matches neither name, so the render branch handed it
   ``degree=None`` and its sidecar was never consulted.

Sections A/B load ``image_compression`` standalone (no agent stack).
C/D/E need ``manual_entry`` / ``llm_provider``, so they bootstrap the
stubbed third-party deps first.  Everything is offline: no Postgres, no
R2, no network.  Nothing is written outside a temp folder.
"""
from __future__ import annotations

import base64
import importlib.util
import io
import sys
import tempfile
from pathlib import Path

from PIL import Image

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MOD = _REPO_ROOT / "agents" / "shared" / "image_compression.py"

_spec = importlib.util.spec_from_file_location("image_compression", _MOD)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print("   %-5s %s%s" % ("OK" if ok else "FAIL", name,
                            "" if ok else "  -- " + detail))
    if not ok:
        _failures.append(name)


# Deterministic settings: the assertions must not depend on whatever the
# local settings.py happens to hold.
_FAKE = {
    "IMAGE_COMPRESSION_ENABLED": True,
    "IMAGE_COMPRESSION_MIN_LONG_EDGE": 512,
    "IMAGE_COMPRESSION_RENDER_MIN_LONG_EDGE": 320,
    "IMAGE_COMPRESSION_DEFAULT_CAP": 1024,
    "IMAGE_COMPRESSION_HARD_MAX_LONG_EDGE": 1900,
    "IMAGE_COMPRESSION_3D_RENDER_DEGREE": 55,
    "IMAGE_COMPRESSION_CROSS_SECTIONS_DEGREE": 69,
}
m._get_setting = lambda name, default: _FAKE.get(name, default)


def png_bytes(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (120, 30, 200)).save(buf, format="PNG")
    return buf.getvalue()


def long_edge(raw: bytes) -> int:
    return max(Image.open(io.BytesIO(raw)).size)


print("=" * 74)
print("A.  degree_and_floor_for_path -- what counts as a GENERATED render")
print("=" * 74)

tmp = Path(tempfile.mkdtemp(prefix="manual_compress_"))
att = tmp / "attempts" / "20260916_120000_001_x"
att.mkdir(parents=True)
ui = tmp / "inputs" / "input_images"
ui.mkdir(parents=True)

iso = att / "render_isometric.png"
cross = att / "render_blade_sections.png"
manual = att / "ring_reference.png"
user_img = ui / "sketch.png"
for p in (iso, cross, manual, user_img):
    p.write_bytes(png_bytes(1600, 1200))

# A sidecar beside every one of them: the point is which ones HONOUR it.
for p in (iso, cross, manual, user_img):
    m.write_degree(p, 12)

deg, floor = m.degree_and_floor_for_path(iso, is_render=True)
check("canonical 3D render takes the per-type 3D degree, not its sidecar",
      deg == 55, f"got {deg}")
check("...and the lower RENDER floor", floor == 320, f"got {floor}")

deg, floor = m.degree_and_floor_for_path(cross, is_render=True)
check("canonical cross-section render takes the per-type cross degree",
      deg == 69, f"got {deg}")

deg, floor = m.degree_and_floor_for_path(manual, is_render=True)
check("manual upload under attempts/ takes ITS OWN sidecar degree",
      deg == 12, f"got {deg}")
check("...and the user-image floor (None => _floor())", floor is None,
      f"got {floor}")

deg, _ = m.degree_and_floor_for_path(user_img, is_render=False)
check("a user image still takes its sidecar degree", deg == 12, f"got {deg}")

bare = att / "no_sidecar.png"
bare.write_bytes(png_bytes(1600, 1200))
deg, _ = m.degree_and_floor_for_path(bare, is_render=True)
check("no sidecar => None (caller falls back to the size-based default)",
      deg is None, f"got {deg}")

print()
print("=" * 74)
print("B.  The degree actually reaches the pixels")
print("=" * 74)

raw = png_bytes(1600, 1200)
m.write_degree(manual, 10)
d10, f10 = m.degree_and_floor_for_path(manual, is_render=True)
out10 = m.compress_for_model(raw, d10, is_render=True, floor=f10)
m.write_degree(manual, 90)
d90, f90 = m.degree_and_floor_for_path(manual, is_render=True)
out90 = m.compress_for_model(raw, d90, is_render=True, floor=f90)

print(f"   degree 10 -> long edge {long_edge(out10)};  "
      f"degree 90 -> long edge {long_edge(out90)}")
check("two different chosen degrees produce two different sizes",
      long_edge(out10) != long_edge(out90),
      "identical -- the sidecar is being ignored, which is the bug")
check("a higher degree compresses harder",
      long_edge(out90) < long_edge(out10))

# The regression this replaces: before the fix BOTH landed on the
# size-based default, i.e. exactly what a None degree gives.
none_out = m.compress_for_model(raw, None, is_render=True, floor=None)
check("neither equals the size-based default any more",
      long_edge(out10) != long_edge(none_out)
      and long_edge(out90) != long_edge(none_out),
      f"default={long_edge(none_out)}")

# A canonical render must be untouched by any of this.
m.write_degree(iso, 5)
dr, fr = m.degree_and_floor_for_path(iso, is_render=True)
check("a canonical render still ignores a sidecar planted beside it",
      dr == 55 and fr == 320, f"got {dr}/{fr}")

print()
print("=" * 74)
print("C/D/E.  manual_entry staging, the upload whitelist, and encode_image")
print("=" * 74)

sys.path.insert(0, str(_REPO_ROOT / "extra_utilities" / "prompt_pdf"))
import bootstrap                                        # noqa: E402
bootstrap.STUB_ROOTS -= {"PIL"}
bootstrap.install()
sys.path.insert(0, str(_REPO_ROOT))

from agents.database_handler import manual_entry as me   # noqa: E402
from agents.shared import image_compression as ic        # noqa: E402

img = me.ManualImage(filename="ring_reference.png",
                     data=png_bytes(1600, 1200),
                     note="a reference photo",
                     compression_degree=37)
staging = Path(tempfile.mkdtemp(prefix="manual_stage_"))
ui_dir, attempt_dir = me._stage(
    staging, "some prose", [img],
    to_user_inputs=True, parameters={"bladeCount": 5}, attempt_nnn="001")

ui_img = ui_dir / "images" / img.filename
check("C: user_inputs copy exists", ui_img.is_file())
check("C: user_inputs sidecar round-trips the chosen degree",
      ic.read_degree(ui_img) == 37, f"got {ic.read_degree(ui_img)}")

att_img = attempt_dir / img.filename
check("C: attempt copy exists", att_img.is_file())
check("C: attempt copy now HAS a sidecar",
      ic.sidecar_path(att_img).is_file())
check("C: attempt sidecar round-trips the same degree",
      ic.read_degree(att_img) == 37, f"got {ic.read_degree(att_img)}")
check("C: the two copies agree",
      ic.read_degree(ui_img) == ic.read_degree(att_img))

# D -- the whitelist is FILENAMES, not suffixes (trap 3b in manual_entry's
# own header), so the sidecar needs naming explicitly or it never reaches R2.
whitelist = (["parameters.json"] + [i.filename for i in [img]]
             + [ic.sidecar_path(i.filename).name for i in [img]])
check("D: whitelist carries the image", img.filename in whitelist)
check("D: whitelist carries its sidecar",
      ic.sidecar_path(att_img).name in whitelist,
      f"{ic.sidecar_path(att_img).name} not in {whitelist}")
check("D: the whitelisted sidecar name is the file really written",
      (attempt_dir / ic.sidecar_path(img.filename).name).is_file())

# E -- the live encode path view_images uses for an uncropped image.
from agents.shared import llm_provider                   # noqa: E402

e_manual = base64.b64decode(llm_provider.encode_image(att_img, is_render=True))
e_iso = base64.b64decode(llm_provider.encode_image(iso, is_render=True))
print(f"   encode_image: manual upload -> {long_edge(e_manual)}, "
      f"canonical render -> {long_edge(e_iso)}")
check("E: encode_image honours the manual upload's sidecar",
      long_edge(e_manual) == long_edge(
          ic.compress_for_model(att_img.read_bytes(), 37, floor=None)),
      f"got {long_edge(e_manual)}")
check("E: encode_image still applies the per-type degree to a real render",
      long_edge(e_iso) == long_edge(
          ic.compress_for_model(iso.read_bytes(), 55, is_render=True,
                                floor=ic._render_floor())),
      f"got {long_edge(e_iso)}")

print()
if _failures:
    print("FAILURES:", _failures)
    sys.exit(1)
print("MANUAL-UPLOAD COMPRESSION: PASS")
