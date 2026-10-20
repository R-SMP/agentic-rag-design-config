"""Offline check of the online Studio (MAS-blueprint P7b-lite,
``python -m studio --online``, ``studio/HOSTING.md``).

1. NO CODE, NO STUDIO: without ``INVITE_CODE`` it does not start, and makes
   no workspace.
2. THE SHARED SETUP: the workspace gets a copy of the example, byte for
   byte; a restart keeps what is there (an edit survives it).
3. THE WAY IN: without the cookie every call answers 401 (the setup, a
   download, a picture, an unknown call); the page, its scripts, the health
   answer (``/api/config``), ``session`` and the guide (``/static/guide.html``,
   its sections, linked from the toolbar and the landing page) do not.  A wrong code sets no
   cookie; the right one does, and with it the Studio answers; a cookie with
   a changed signature, or older than 30 days, does not open it.
4. ONLINE: the setup says so (the configurator's address and name -- the
   example's -- also before the code, for the access-code page; Start again
   offered); Prepare for GitHub is unavailable with its online reason;
   Start again refuses without the word replace, and with it brings the
   example back byte for byte, nothing listed as changed.
5. LOCAL STAYS OPEN: ``python -m studio`` without ``--online`` asks for no
   code.  The image carries the Studio and never the workspace
   (``.dockerignore``); git leaves the workspace out (``.gitignore``).
   Outside git, the engine's version is the commit Railway built.

Takes about two minutes.  Run from the repo root:
    py -3.13 extra_utilities/tests/smoke_test_online.py
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ["DATABASE_URL"] = ""
os.environ["DATABASE_PUBLIC_URL"] = ""
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from studio import package as K                  # noqa: E402
from studio.server import ACCESS_COOKIE, Access  # noqa: E402

FAILURES: list[str] = []
CODE = "smoke-online-code-qzx"
SECRET = "smoke-online-secret-qzx"


def check(ok: bool, what: str) -> None:
    if not ok:
        FAILURES.append(what)


def _run(group, tag: str):
    try:
        return group()
    except Exception as exc:                         # noqa: BLE001
        import traceback
        check(False, f"{tag} crashed: {type(exc).__name__}: {exc}\n{traceback.format_exc()[-1500:]}")
        return None


def snapshot(folder: Path) -> dict[str, bytes]:
    return {rel: p.read_bytes() for rel, p in K.setup_files(folder).items()}


class Studio:
    """``python -m studio`` (online or not) on a free port."""

    def __init__(self, args: list[str], env: dict):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.proc = subprocess.Popen([sys.executable, "-m", "studio", "--port", str(self.port),
                                      "--workers", "0", *args], cwd=str(ROOT), env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=10)
                return
            except OSError:
                if self.proc.poll() is not None:
                    break
                time.sleep(0.3)
        raise RuntimeError("the Studio did not start: " + (self.proc.stdout.read().decode("utf-8", "replace")
                                                            if self.proc.poll() is not None else ""))

    def req(self, path: str, args=None, cookie: str | None = None, method: str | None = None):
        """(status, headers, parsed JSON or raw bytes)."""
        data = None if args is None else json.dumps({"args": list(args)}).encode("utf-8")
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data,
                                   method=method or ("POST" if data is not None else "GET"),
                                   headers={"Content-Type": "application/json",
                                            **({"Cookie": f"{ACCESS_COOKIE}={cookie}"} if cookie else {})})
        try:
            with urllib.request.urlopen(r, timeout=600) as resp:
                status, headers, body = resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            status, headers, body = e.code, dict(e.headers), e.read()
        try:
            return status, headers, json.loads(body)
        except ValueError:
            return status, headers, body

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def _env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("INVITE_CODE", "CONFIGURATOR_URL", "STUDIO_SECRET")}
    env.update(extra)
    return env


def check_no_code(tmp: Path) -> str:
    ws = tmp / "ws_nocode"
    r = subprocess.run([sys.executable, "-m", "studio", "--online", "--workspace", str(ws), "--port", "1"],
                       cwd=str(ROOT), env=_env(), capture_output=True, text=True, timeout=120)
    check(r.returncode == 2 and "INVITE_CODE" in r.stderr and not ws.exists(),
          f"[START] online without INVITE_CODE: {r.returncode} {r.stderr[-300:]}")
    return "no code, no start"


def check_online(tmp: Path) -> str:
    example = tmp / "example" / "dc_pack"
    shutil.copytree(ROOT / "dc_pack", example, ignore=shutil.ignore_patterns("__pycache__"))
    ws = tmp / "ws"
    env = _env(INVITE_CODE=CODE, STUDIO_SECRET=SECRET, CONFIGURATOR_URL="https://example.invalid/app")
    args = ["--online", "--workspace", str(ws), "--pack", str(example)]
    st = Studio(args, env)
    try:
        shared = ws / "dc_pack"
        check(snapshot(shared) == snapshot(example), "[SHARED] the workspace is not a copy of the example")
        # the way in
        for path, a in (("/api/get_all", []), ("/download/setup", None),
                        ("/pack/assets/general-profile.png", None), ("/api/no_such_call", [])):
            status, _h, body = st.req(path, a)
            check(status == 401 and isinstance(body, dict) and body.get("auth"),
                  f"[GATE] {path} without the code: {status}")
        for path in ("/", "/static/studio.js", "/static/bridge.js"):
            check(st.req(path)[0] == 200, f"[GATE] {path} is not served before the code")
        # the guide opens before the code, whole, and the page links to it
        status, _h, guide = st.req("/static/guide.html")
        text = guide.decode("utf-8") if isinstance(guide, bytes) else ""
        check(status == 200 and all(h in text for h in (
            "Getting started", "What it is", "1. Open the Studio", "2. Make the setup yours", "3. Validate",
            "4. Save your work", "5. Deploy it", "6. What it cannot do yet")),
              f"[GUIDE] the guide before the code: {status}, sections missing")
        js = (ROOT / "studio" / "web" / "studio.js").read_text(encoding="utf-8")
        check(js.count("/static/guide.html") == 2, "[GUIDE] the toolbar and the landing page do not both link the guide")
        status, _h, body = st.req("/api/config")
        check(status == 200 and body.get("online") is True, f"[GATE] the health answer: {status} {body}")
        _s, _h, body = st.req("/api/session", [])
        check(body.get("online") is True and body.get("authed") is False, f"[GATE] session: {body}")
        check(body.get("configurator") == {"url": "https://example.invalid/app", "name": "propeller"},
              f"[ONLINE] the configurator's link before the code: {body.get('configurator')}")
        check("configuratorLink()" in js.split("function renderLogin", 1)[1].split("\n  function ", 1)[0],
              "[ONLINE] the access-code page does not offer the configurator")
        status, headers, body = st.req("/api/auth", ["not the code"])
        check(status == 401 and "set-cookie" not in {k.lower() for k in headers},
              f"[GATE] a wrong code: {status} {headers.get('set-cookie')}")
        status, headers, body = st.req("/api/auth", [CODE])
        cookie = next((v.split(";", 1)[0].split("=", 1)[1] for k, v in headers.items()
                       if k.lower() == "set-cookie" and v.startswith(ACCESS_COOKIE + "=")), None)
        check(status == 200 and cookie and "HttpOnly" in (headers.get("set-cookie") or headers.get("Set-Cookie") or ""),
              f"[GATE] the right code: {status} {headers}")
        _s, _h, body = st.req("/api/session", [], cookie)
        check(body.get("authed") is True, f"[GATE] session with the cookie: {body}")
        status, _h, body = st.req("/api/get_all", [], cookie)
        check(status == 200 and body.get("ok"), f"[GATE] get_all with the cookie: {status}")
        d = body.get("data") or {}
        issued, sig = (cookie or "0.0").split(".", 1)
        bad = issued + "." + ("0" if sig[0] != "0" else "1") + sig[1:]
        check(st.req("/api/get_all", [], bad)[0] == 401, "[GATE] a cookie with a changed signature opens it")
        old = Access(CODE, SECRET.encode("utf-8"))
        stamp = str(int(time.time()) - 31 * 86400)
        check(st.req("/api/get_all", [], f"{stamp}.{old._sign(stamp)}")[0] == 401,
              "[GATE] a cookie older than 30 days opens it")
        check(st.req("/api/session", [], old.token())[2].get("authed") is True,
              "[GATE] a cookie signed with STUDIO_SECRET does not open it")
        # online
        check(d.get("online") is True
              and d.get("configurator") == {"url": "https://example.invalid/app", "name": "propeller"}
              and d.get("can_reset") is True, f"[ONLINE] the setup's data: {d.get('online')} "
                                              f"{d.get('configurator')} {d.get('can_reset')}")
        check(d.get("prepare", {}).get("available") is False and "Online" in (d["prepare"].get("why") or ""),
              f"[ONLINE] Prepare for GitHub: {d.get('prepare')}")
        status, _h, body = st.req("/download/package", None, cookie)
        check(status == 200 and isinstance(body, bytes) and body[:2] == b"PK",
              f"[ONLINE] the full package with the cookie: {status}")
        s = next(x for x in d["slots"] if x["slot"] == "dc_name")
        _s, _h, body = st.req("/api/save_field", ["dc_name", None, {"all": "a shared change"},
                                                  {"all": s["values"]["7"]}], cookie)
        check(body.get("ok"), f"[ONLINE] an edit: {body}")
        _s, _h, body = st.req("/api/reset_to_example", ["yes"], cookie)
        check(body.get("ok") is False and "replace" in (body.get("error") or ""),
              f"[ONLINE] Start again without the word: {body}")
        _s, _h, body = st.req("/api/reset_to_example", ["replace"], cookie)
        check(body.get("ok") and snapshot(shared) == snapshot(example),
              f"[ONLINE] Start again: {str(body)[:300]}")
        _s, _h, body = st.req("/api/get_all", [], cookie)
        check(body["data"]["changed"] == [], f"[ONLINE] after Start again, changed: {body['data']['changed'][:4]}")
        # an edit survives a restart (the workspace is not copied again)
        _s, _h, body = st.req("/api/save_field", ["dc_name", None, {"all": "kept across a restart"},
                                                  {"all": s["values"]["7"]}], cookie)
        check(body.get("ok"), f"[SHARED] the edit before the restart: {body}")
    finally:
        st.stop()
    st = Studio(args, env)
    try:
        status, headers, _b = st.req("/api/auth", [CODE])
        cookie = next(v.split(";", 1)[0].split("=", 1)[1] for k, v in headers.items()
                      if k.lower() == "set-cookie")
        _s, _h, body = st.req("/api/get_all", [], cookie)
        name = next(x for x in body["data"]["slots"] if x["slot"] == "dc_name")["values"]["7"]
        check(name == "kept across a restart", f"[SHARED] after a restart the setup is {name!r}")
    finally:
        st.stop()
    return "online: gate, shared setup, Start again, restart"


def check_local(tmp: Path) -> str:
    copy = tmp / "local" / "dc_pack"
    shutil.copytree(ROOT / "dc_pack", copy, ignore=shutil.ignore_patterns("__pycache__"))
    st = Studio(["--pack", str(copy)], _env(INVITE_CODE=CODE))
    try:
        _s, _h, body = st.req("/api/session", [])
        check(body.get("online") is False and body.get("authed") is True
              and body.get("configurator") is None, f"[LOCAL] session: {body}")
        check(st.req("/api/config")[0] == 200, "[LOCAL] no health answer")
    finally:
        st.stop()
    dock = K.IgnoreRules((ROOT / ".dockerignore").read_text(encoding="utf-8"))
    check(not dock.ignored("studio", True) and dock.ignored("workspace", True),
          "[LOCAL] .dockerignore: the image must carry studio/ and never workspace/")
    git = K.IgnoreRules((ROOT / ".gitignore").read_text(encoding="utf-8"))
    check(git.ignored("workspace", True), "[LOCAL] .gitignore does not leave workspace/ out")
    old = os.environ.get("RAILWAY_GIT_COMMIT_SHA")
    os.environ["RAILWAY_GIT_COMMIT_SHA"] = "abcdef1234567890"
    try:
        check(K.engine_version(tmp) == "abcdef1",
              f"[LOCAL] outside git, the engine version is {K.engine_version(tmp)!r}")
    finally:
        if old is None:
            os.environ.pop("RAILWAY_GIT_COMMIT_SHA", None)
        else:
            os.environ["RAILWAY_GIT_COMMIT_SHA"] = old
    return "local: open, ignore files, version"


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="online_smoke_"))
    summary = []
    try:
        summary.append(_run(lambda: check_no_code(tmp), "[START]"))
        summary.append(_run(lambda: check_online(tmp), "[ONLINE]"))
        summary.append(_run(lambda: check_local(tmp), "[LOCAL]"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("; ".join(str(s) for s in summary))
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - online, the Studio needs its access code for every call, keeps one shared "
          "setup that starts from the example and survives a restart, starts again only on "
          "'replace', and leaves Prepare to the downloaded package; locally it stays open.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
