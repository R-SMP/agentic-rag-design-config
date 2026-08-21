# DC-parameter primer — sources

The live assets are:

* `DC_prompt_fragments/dc_config/images/dc_params_primer.png` — the image the
  four DC agents (and the 5/3-agent Creator / Designer) receive at invoke
  time, injected by `agents/shared/dc_primer.py` behind
  `DC_PARAMS_PRIMER_ENABLED`.
* `DC_prompt_fragments/dc_config/dc_params_primer_text.txt` — the paired text
  block, sent in the same `HumanMessage` BEFORE the image.

This folder holds what regenerates them:

* `make_dc_params_primer.py` — rebuilds the PPTX and exports the full-size
  PNG (1094×364) from one display list.  Run it wherever PowerPoint export
  is available; it does not run on Railway.
* `dc_params_primer.pptx` — the last generated deck, kept so the drawing can
  be tweaked by hand if needed.

**The repo PNG is NOT the generator's output.**  It is the 85 % LANCZOS
downscale (930×309, ~383 Anthropic image tokens vs 531), chosen by the owner
on 2026-08-22 after comparing 100/85/75/65 % crops at 1:1 — 85 % was the
largest saving with no visible loss in the arrows or the 9 pt labels.  After
regenerating, reproduce that step:

```python
from PIL import Image
im = Image.open("dc_params_primer.png")          # 1094x364 generator output
im.resize((930, 309), Image.LANCZOS).save(
    "DC_prompt_fragments/dc_config/images/dc_params_primer.png",
    optimize=True)
```

Two rules the pipeline depends on:

1. The image is deliberately **exempt from `compress_for_model`** — the
   injection reads the file bytes directly, so the per-image compression
   sidecars do not apply.  Do not route it through `encode_image`.
2. The high-point bullet in the text block quotes the canonical sentence
   from `DC_prompt_fragments/dc_config/parameters.md` **verbatim** — keep
   them in lockstep (guarded by `extra_utilities/smoke_test_dc_primer.py`).
