"""voyage-multimodal-3.5 through OpenRouter (``agents/shared/voyage_mm.py``).

OFFLINE (no network, no key): ``requests.post`` is replaced by a stand-in
that records each request and answers as told.

* the request for text, image and image+text, as document and as query:
  OpenRouter's URL, the key as a Bearer header, model
  ``voyageai/voyage-multimodal-3.5``, ``dimensions`` 2048, the input type,
  float encoding, ONE input whose parts are in order (text, then image);
* an image goes as a lossless WebP data URI that decodes to the very
  pixels sent (a large one shrunk to 1536 px on its long side, RGB);
* a vector of the wrong length stops at once (no retry); a failed call
  (HTTP 500, a network error, an answer without ``data`` or not JSON) is
  tried again,
  three times in all, with 2 s and 4 s waits, and the last error raised;
  a call that fails once and then answers returns the vector;
* without ``OPENROUTER_API_KEY`` the embed raises before any request and
  says which key; ``VOYAGE_API_KEY`` alone is not enough;
* the stored label is still ``voyage/voyage-multimodal-3.5/2048`` (the
  rows saved through Voyage's own SDK stay searchable) and the module no
  longer imports ``voyageai``.

Usage (repository root):
    py -3.13 extra_utilities/tests/smoke_test_voyage_openrouter.py
"""
from __future__ import annotations

import base64
import importlib.util
import io
import os
import sys
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    # BY FILE PATH: agents/__init__ eagerly imports the whole agent stack.
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


vm = _load("voyage_mm", "agents/shared/voyage_mm.py")

FAILS: list[str] = []
KEY = "sk-or-test-key"


def check(cond: bool, label: str) -> None:
    print(("  ok    " if cond else "  FAIL  ") + label)
    if not cond:
        FAILS.append(label)


class _Response:
    def __init__(self, status: int, body):
        self.status_code = status
        self._body = body
        self.text = body if isinstance(body, str) else repr(body)

    def json(self):
        if isinstance(self._body, str):
            raise ValueError("not JSON")  # what requests raises (a ValueError subclass)
        return self._body


class _Post:
    """Stands in for ``requests.post``: records calls, plays ``answers``."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls: list[dict] = []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, Exception):
            raise a
        return a


def _ok(n: int = 2048) -> _Response:
    return _Response(200, {"data": [{"embedding": [0.001 * i for i in range(n)]}]})


class _Run:
    """One embed with a stand-in post, no sleeping, and the key as given."""

    def __init__(self, post: _Post, key: str | None = KEY, voyage_key: str | None = None):
        self.post, self.key, self.voyage_key = post, key, voyage_key
        self.sleeps: list[float] = []

    def __enter__(self):
        self._saved = (vm.requests.post, vm.time.sleep,
                       os.environ.get("OPENROUTER_API_KEY"), os.environ.get("VOYAGE_API_KEY"))
        vm.requests.post = self.post
        vm.time.sleep = self.sleeps.append
        for name, value in (("OPENROUTER_API_KEY", self.key), ("VOYAGE_API_KEY", self.voyage_key)):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        return self

    def __exit__(self, *exc):
        vm.requests.post, vm.time.sleep = self._saved[0], self._saved[1]
        for name, value in zip(("OPENROUTER_API_KEY", "VOYAGE_API_KEY"), self._saved[2:]):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        return False


def _decode(uri: str) -> Image.Image | None:
    prefix = "data:image/webp;base64,"
    if not uri.startswith(prefix):
        return None
    im = Image.open(io.BytesIO(base64.b64decode(uri[len(prefix):])))
    im.load()
    return im


def _image(w: int, h: int, mode: str = "RGB") -> Image.Image:
    im = Image.new(mode, (w, h))
    px = im.load()
    for x in range(w):
        for y in range(h):
            v = (x * 7 + y * 13) % 256
            px[x, y] = (v, 255 - v, (x * y) % 256) if mode == "RGB" else (v, 255 - v, x % 256, 200)
    return im


def test_requests() -> None:
    print("The requests")
    text = "A propeller with five thin blades."
    im = _image(40, 30)
    cases = [
        ("text", lambda q: vm.embed_text(text, as_query=q), ["text"]),
        ("image", lambda q: vm.embed_image(im, as_query=q), ["image_url"]),
        ("image+text", lambda q: vm.embed_fused(text, im, as_query=q), ["text", "image_url"]),
    ]
    for as_query, input_type in ((False, "document"), (True, "query")):
        for name, fn, kinds in cases:
            post = _Post(_ok())
            with _Run(post):
                vec = fn(as_query)
            label = f"{name}, {input_type}"
            check(len(post.calls) == 1, f"{label}: one request")
            c = post.calls[0]
            body = c["json"]
            check(c["url"] == "https://openrouter.ai/api/v1/embeddings", f"{label}: OpenRouter's embeddings URL")
            check(c["headers"] == {"Authorization": f"Bearer {KEY}"}, f"{label}: the key as a Bearer header")
            check(isinstance(c["timeout"], (int, float)) and c["timeout"] > 0, f"{label}: a timeout")
            check(set(body) == {"model", "input", "dimensions", "input_type", "encoding_format"},
                  f"{label}: the body's fields")
            check(body["model"] == "voyageai/voyage-multimodal-3.5", f"{label}: model")
            check(body["dimensions"] == 2048, f"{label}: dimensions 2048")
            check(body["input_type"] == input_type, f"{label}: input_type {input_type}")
            check(body["encoding_format"] == "float", f"{label}: float encoding")
            check(len(body["input"]) == 1 and set(body["input"][0]) == {"content"}, f"{label}: one input")
            parts = body["input"][0]["content"]
            check([p["type"] for p in parts] == kinds, f"{label}: parts in order {kinds}")
            for p in parts:
                if p["type"] == "text":
                    check(p == {"type": "text", "text": text}, f"{label}: the text as given")
                else:
                    got = _decode(p["image_url"]["url"])
                    check(got is not None and got.format == "WEBP", f"{label}: a WebP data URI")
                    check(got is not None and got.convert("RGB").tobytes() == im.tobytes(),
                          f"{label}: lossless (the same pixels)")
            check(vec == [0.001 * i for i in range(2048)], f"{label}: the vector returned")


def test_images() -> None:
    print("Images")
    big = _image(2000, 1000, "RGBA")
    post = _Post(_ok())
    with _Run(post):
        vm.embed_image(big)
    got = _decode(post.calls[0]["json"]["input"][0]["content"][0]["image_url"]["url"])
    check(got is not None and got.size == (1536, 768), "a large image is shrunk to 1536 px, aspect kept")
    check(got is not None and got.mode == "RGB", "and sent as RGB")
    raw = io.BytesIO()
    _image(20, 10).save(raw, format="PNG")
    for name, src in (("bytes", raw.getvalue()), ("a path", None)):
        if src is None:
            p = Path(os.environ.get("TEMP", ".")) / "smoke_voyage_openrouter.png"
            p.write_bytes(raw.getvalue())
            src = str(p)
        post = _Post(_ok())
        with _Run(post):
            vm.embed_image(src)
        got = _decode(post.calls[0]["json"]["input"][0]["content"][0]["image_url"]["url"])
        check(got is not None and got.convert("RGB").tobytes() == _image(20, 10).tobytes(),
              f"an image given as {name} is sent unchanged")


def test_failures() -> None:
    print("Failures")
    post = _Post(_ok(1024))
    with _Run(post) as run:
        try:
            vm.embed_text("x")
            check(False, "a wrong vector length raises")
        except ValueError as exc:
            check("1024" in str(exc) and "2048" in str(exc), "a wrong vector length raises, naming both")
    check(len(post.calls) == 1 and run.sleeps == [], "and is not tried again")

    for name, answer, kind in (("HTTP 500", _Response(500, "upstream error"), RuntimeError),
                               ("a network error", ConnectionError("reset"), ConnectionError),
                               ("an answer without data", _Response(200, {"error": {"message": "x"}}), RuntimeError),
                               ("an answer that is not JSON", _Response(200, "<html>busy</html>"), RuntimeError)):
        post = _Post(answer)
        with _Run(post) as run:
            try:
                vm.embed_text("x")
                check(False, f"{name}: raises")
            except kind as exc:
                check(True, f"{name}: raises {type(exc).__name__} after the last try")
                if name == "HTTP 500":
                    check("500" in str(exc) and "upstream error" in str(exc), f"{name}: the error says the status")
                    check(KEY not in str(exc), f"{name}: the error never shows the key")
        check(len(post.calls) == 3, f"{name}: tried three times")
        check(run.sleeps == [2.0, 4.0], f"{name}: waits 2 s, then 4 s")

    post = _Post(_Response(429, "rate limited"), _ok())
    with _Run(post) as run:
        vec = vm.embed_text("x")
    check(len(post.calls) == 2 and len(vec) == 2048, "a failure then an answer returns the vector")


def test_key() -> None:
    print("The key")
    for name, voyage_key in (("no key", None), ("only VOYAGE_API_KEY", "pa-voyage")):
        post = _Post(_ok())
        with _Run(post, key=None, voyage_key=voyage_key):
            try:
                vm.embed_text("x")
                check(False, f"{name}: raises")
            except RuntimeError as exc:
                check("OPENROUTER_API_KEY" in str(exc), f"{name}: raises, naming OPENROUTER_API_KEY")
        check(post.calls == [], f"{name}: no request made")


def test_label() -> None:
    print("The stored label")
    check(vm.embedding_model_string() == "voyage/voyage-multimodal-3.5/2048",
          "embedding_model_string() is still voyage/voyage-multimodal-3.5/2048")
    check((vm.VOYAGE_MM_MODEL, vm.VOYAGE_MM_DIMS) == ("voyage-multimodal-3.5", 2048),
          "VOYAGE_MM_MODEL / VOYAGE_MM_DIMS as the Database options panel shows them")
    src = (REPO_ROOT / "agents/shared/voyage_mm.py").read_text(encoding="utf-8")
    check("import voyageai" not in src, "voyage_mm no longer imports voyageai")
    req = (REPO_ROOT / "requirements-web.txt").read_text(encoding="utf-8")
    check("voyageai" not in req, "requirements-web.txt no longer lists voyageai")


def main() -> int:
    test_requests()
    test_images()
    test_failures()
    test_key()
    test_label()
    if FAILS:
        print(f"FAILED: {len(FAILS)}")
        for f in FAILS:
            print("  - " + f)
        return 1
    print("PASS smoke_test_voyage_openrouter")
    return 0


if __name__ == "__main__":
    sys.exit(main())
