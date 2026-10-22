"""The bucket switch (Railway bucket first, Cloudflare R2 fallback) and the
R2 -> Railway copy script.

OFFLINE (default, no network, no credentials):

* which bucket ``agents/shared/r2_uploader.py`` picks for every mix of
  ``S3_*`` / ``R2_*`` variables -- a complete S3 set wins, a PARTIAL S3 set
  disables the bucket instead of falling back to R2;
* the boto3 client each one builds (endpoint, region, addressing style,
  R2 jurisdiction) and that ``describe()`` never shows a secret;
* ``extra_utilities/scripts/copy_bucket.py`` against in-memory fake buckets:
  the source wrapper refuses every write, ``copy`` copies only what is
  missing or different and keeps the headers, a second run copies nothing,
  ``verify`` passes and then catches a tampered object, and the source is
  byte-identical afterwards.

LIVE (``--live``; needs the ``S3_*`` variables, e.g. ``--env-file .env``):
runs the app's real upload functions against the Railway bucket -- the
calls behind saving a session (``upload_directory``,
``upload_attempt_artefacts``, ``upload_bytes``) and the queue-log snapshot
(``upload_file``) -- then reads everything back with the same S3 calls the
retrieve tools and the chunks_mm mirror make (paginated
``list_objects_v2`` + ``get_object`` under ``R2_KEY_PREFIX``), and removes
it with ``delete_objects`` as the manual-entry rollback does.  Everything
lives under ``<R2_KEY_PREFIX>/_bucket_smoke_test/<UTC ts>/`` and is deleted
at the end.  ``--read-session <sid>`` additionally lists and downloads one
saved session (read only) to prove migrated data resolves.

Usage (repository root):
    py -3.13 extra_utilities/tests/smoke_test_bucket.py
    py -3.13 extra_utilities/tests/smoke_test_bucket.py --live --env-file <file>
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# is_enabled() asks engine.pack whether the active setup uses the database.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load(name: str, rel: str):
    # BY FILE PATH: agents/__init__ eagerly imports the whole agent stack.
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


r2 = _load("r2_uploader", "agents/shared/r2_uploader.py")
cb = _load("copy_bucket", "extra_utilities/scripts/copy_bucket.py")

FAILS: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("  ok    " if cond else "  FAIL  ") + label)
    if not cond:
        FAILS.append(label)


_ALL_VARS = (r2._S3_REQUIRED_ENV_VARS + r2._REQUIRED_ENV_VARS  # noqa: SLF001
             + ("S3_REGION", "S3_ADDRESSING_STYLE", "R2_JURISDICTION",
                "R2_KEY_PREFIX"))


@contextlib.contextmanager
def env(**values: str):
    """Run with ONLY *values* among the bucket variables."""
    saved = {k: os.environ.get(k) for k in _ALL_VARS}
    for k in _ALL_VARS:
        os.environ.pop(k, None)
    os.environ.update(values)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


S3 = dict(S3_ENDPOINT_URL="https://t3.storageapi.dev/", S3_BUCKET="mt-abc123",
          S3_ACCESS_KEY_ID="tid_s3key", S3_SECRET_ACCESS_KEY="s3-secret-value")
R2 = dict(R2_ACCOUNT_ID="acct42", R2_ACCESS_KEY_ID="r2key",
          R2_SECRET_ACCESS_KEY="r2-secret-value", R2_BUCKET_NAME="old-bucket")


# ---------------------------------------------------------------------------
# offline: bucket selection
# ---------------------------------------------------------------------------

def test_selection() -> None:
    print("[bucket selection]")
    with env():
        check(r2.backend() == "" and not r2.is_enabled(), "nothing set -> no bucket")
        check("no bucket is configured" in r2.config_problem(),
              "nothing set -> config_problem names both sets")
    with env(**R2):
        check(r2.backend() == "r2", "R2 only -> r2")
        check(r2.bucket_name() == "old-bucket", "R2 only -> R2_BUCKET_NAME")
        check(r2.config_problem() == "", "R2 only -> no config problem")
    with env(**S3):
        check(r2.backend() == "s3", "S3 only -> s3")
    with env(**S3, **R2):
        check(r2.backend() == "s3", "S3 + R2 -> s3 wins")
        check(r2.bucket_name() == "mt-abc123", "S3 + R2 -> S3_BUCKET")
        check(r2.bucket_name("r2") == "old-bucket", "bucket_name('r2') still answers")
    partial = {k: v for k, v in S3.items() if k != "S3_SECRET_ACCESS_KEY"}
    with env(**partial, **R2):
        check(r2.backend() == "" and not r2.is_enabled(),
              "PARTIAL S3 + complete R2 -> NO bucket (no silent R2 fallback)")
        check("S3_SECRET_ACCESS_KEY" in r2.config_problem(),
              "partial S3 -> config_problem names the missing variable")
        check(r2._client() is None, "partial S3 -> _client() is None")  # noqa: SLF001
    with env(**{**S3, "S3_BUCKET": "  "}):
        check(r2.backend() == "", "whitespace-only S3_BUCKET counts as missing")
    from engine import pack
    real = pack.uses_database
    try:
        pack.uses_database = lambda root=None: False
        with env(**S3, **R2):
            check(r2.backend() == "s3" and not r2.is_enabled(),
                  "a setup without `database: true` -> no bucket, even with S3_*")
            check(r2._client() is None, "... and _client() is None")  # noqa: SLF001
            check("database: true" in r2.config_problem()
                  and "not used" in r2.describe(),
                  "... config_problem() and describe() say why")
    finally:
        pack.uses_database = real
    with env(**S3, **R2):
        check(r2.is_enabled(), "the propeller setup (`database: true`) -> bucket in use")
    with env(**S3, **R2, R2_KEY_PREFIX="/web-v1/"):
        check(r2._key_prefix() == "web-v1/",  # noqa: SLF001
              "R2_KEY_PREFIX applies to the S3 bucket too ('web-v1/')")


def test_clients() -> None:
    print("[clients]")
    with env(**S3, **R2):
        c = r2._client()  # noqa: SLF001
        check(c.meta.endpoint_url == "https://t3.storageapi.dev",
              "S3 client endpoint = S3_ENDPOINT_URL (trailing / dropped)")
        check(c.meta.region_name == "auto", "S3 client region defaults to auto")
        check((c.meta.config.s3 or {}).get("addressing_style") == "virtual",
              "S3 client addressing style defaults to virtual")
        d = r2.describe()
        check("mt-abc123" in d and "t3.storageapi.dev" in d,
              "describe() names bucket and endpoint")
        check(not any(s in d for s in ("s3-secret-value", "tid_s3key",
                                       "r2-secret-value", "r2key")),
              "describe() shows no key or secret")
    with env(**{**S3, "S3_REGION": "eu-central-1", "S3_ADDRESSING_STYLE": "PATH"}):
        c = r2._client()  # noqa: SLF001
        check(c.meta.region_name == "eu-central-1", "S3_REGION is used")
        check((c.meta.config.s3 or {}).get("addressing_style") == "path",
              "S3_ADDRESSING_STYLE=PATH -> path")
    with env(**{**S3, "S3_ADDRESSING_STYLE": "sideways"}):
        c = r2._client()  # noqa: SLF001
        check((c.meta.config.s3 or {}).get("addressing_style") == "virtual",
              "unknown addressing style -> virtual")
    with env(**R2, R2_JURISDICTION="eu"):
        c = r2._client()  # noqa: SLF001
        check(c.meta.endpoint_url == "https://acct42.eu.r2.cloudflarestorage.com",
              "R2 client keeps the EU jurisdiction endpoint")
        check(c.meta.region_name == "auto", "R2 client region auto")
        d = r2.describe()
        check("acct42" not in d and "<R2_ACCOUNT_ID>.eu.r2" in d,
              "describe() masks the R2 account id")
    with env(**R2):
        check(r2.client_for("s3") is None, "client_for('s3') None without S3_*")
        check(r2.client_for("r2") is not None, "client_for('r2') with R2_*")


# ---------------------------------------------------------------------------
# offline: copy script against fake buckets
# ---------------------------------------------------------------------------

class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class FakeS3:
    """The few S3 calls copy_bucket makes, over a dict.  Single-part
    ETags are the MD5, as on R2."""

    def __init__(self, objects: dict[str, tuple[bytes, dict]] | None = None):
        self.objects = dict(objects or {})
        self.writes = 0

    def get_paginator(self, op: str):
        assert op == "list_objects_v2"
        fake = self

        class _P:
            def paginate(self, Bucket: str, Prefix: str = ""):
                keys = sorted(k for k in fake.objects if k.startswith(Prefix))
                for i in range(0, max(len(keys), 1), 2):   # 2 per page
                    yield {"Contents": [{
                        "Key": k, "Size": len(fake.objects[k][0]),
                        "ETag": '"' + hashlib.md5(fake.objects[k][0]).hexdigest() + '"',
                        "LastModified": datetime(2026, 10, 1, tzinfo=timezone.utc),
                    } for k in keys[i:i + 2]]}
        return _P()

    def get_object(self, Bucket: str, Key: str):
        data, headers = self.objects[Key]
        return {"Body": _Body(data), **headers}

    def put_object(self, Bucket: str, Key: str, Body: bytes, **headers):
        self.writes += 1
        self.objects[Key] = (Body, headers)
        return {"ETag": '"' + hashlib.md5(Body).hexdigest() + '"'}

    def delete_objects(self, **_kw):  # must never be reachable on the source
        raise AssertionError("delete_objects reached the fake source")


def _run(fn, args) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(args)
    return rc, buf.getvalue()


def test_copy_script() -> None:
    print("[copy_bucket.py]")
    ro = cb.ReadOnlyClient(FakeS3())
    for op in ("put_object", "delete_object", "delete_objects", "copy_object",
               "upload_file", "create_multipart_upload"):
        try:
            getattr(ro, op)
            check(False, f"source wrapper refuses {op}")
        except PermissionError:
            check(True, f"source wrapper refuses {op}")
    try:
        ro.get_paginator("list_object_versions")
        check(False, "source wrapper refuses other paginators")
    except PermissionError:
        check(True, "source wrapper refuses other paginators")

    meta = {"ContentType": "image/png", "CacheControl": "max-age=60",
            "Metadata": {"origin": "dh"}}
    src = FakeS3({
        "web-v1/ID001_x/user_inputs/images/a.png": (b"\x89PNG-a", meta),
        "web-v1/ID001_x/logs/session.log": (b"log line\n", {"ContentType": "text/plain"}),
        "web-v1/ID002_y/attempts/001__7/parameters.json": (b'{"bladeCount": 4}', {}),
        "web-v1/ID002_y/user_inputs/queries.txt": (b"query AAAA", {}),
        "other/root.txt": (b"outside the prefix", {}),
    })
    before = {k: (v[0], dict(v[1])) for k, v in src.objects.items()}
    dst = FakeS3({
        "web-v1/ID001_x/logs/session.log": (b"log line\n", {}),          # same
        "web-v1/ID002_y/attempts/001__7/parameters.json": (b"{}", {}),   # stale
        "web-v1/ID002_y/user_inputs/queries.txt": (b"query BBBB", {}),    # stale, same size
        "web-v1/ID999_new/logs/session.log": (b"after switch", {}),      # target only
    })
    cb._source = lambda: (cb.ReadOnlyClient(src), "old-bucket")  # noqa: SLF001
    cb._target = lambda: (dst, "mt-abc123")                     # noqa: SLF001
    cb.r2_uploader._endpoint_url = lambda which=None: "https://fake"  # noqa: SLF001

    with tempfile.TemporaryDirectory() as tmp:
        ns = argparse.Namespace(out=tmp, prefix="", workers=3, dry_run=True,
                                deep=False)
        rc, out = _run(cb.cmd_copy, ns)
        check(rc == 0 and dst.writes == 0 and "to copy: 4" in out,
              "--dry-run counts 4 to copy and writes nothing")

        ns.dry_run = False
        rc, out = _run(cb.cmd_copy, ns)
        check(rc == 0 and "copied 4, skipped 1, failed 0" in out,
              "copy: 4 copied (missing + stale, incl. same-size), 1 skipped (identical)")
        png = dst.objects["web-v1/ID001_x/user_inputs/images/a.png"]
        check(png[0] == b"\x89PNG-a" and png[1].get("ContentType") == "image/png"
              and png[1].get("CacheControl") == "max-age=60"
              and png[1].get("Metadata") == {"origin": "dh"},
              "copy keeps bytes, ContentType, Cache-Control, metadata")
        check(dst.objects["web-v1/ID002_y/attempts/001__7/parameters.json"][0]
              == b'{"bladeCount": 4}', "a stale target object is replaced")
        check(dst.objects["web-v1/ID002_y/user_inputs/queries.txt"][0]
              == b"query AAAA", "a SAME-SIZE stale object is replaced (MD5)")
        check("other/root.txt" in dst.objects,
              "keys outside R2_KEY_PREFIX are copied too (ALL content)")
        check("web-v1/ID999_new/logs/session.log" in dst.objects,
              "target-only objects are left alone")

        writes = dst.writes
        rc, out = _run(cb.cmd_copy, ns)
        check(rc == 0 and dst.writes == writes and "copied 0, skipped 5" in out,
              "second copy run copies nothing")

        rc, out = _run(cb.cmd_verify, ns)
        check(rc == 0 and "target-only: 1" in out and "OK" in out,
              "verify passes and lists the target-only key")
        ns.deep = True
        rc, out = _run(cb.cmd_verify, ns)
        check(rc == 0, "verify --deep passes")

        dst.objects["web-v1/ID001_x/logs/session.log"] = (b"log linX\n", {})
        rc, out = _run(cb.cmd_verify, ns)
        check(rc == 1 and "MISMATCH" in out,
              "verify --deep catches a same-size tampered object")
        ns.deep = False
        rc, out = _run(cb.cmd_verify, ns)
        check(rc == 1, "verify (ETag) catches it too")
        del dst.objects["web-v1/ID001_x/user_inputs/images/a.png"]
        rc, out = _run(cb.cmd_verify, ns)
        check(rc == 1 and "MISSING" in out, "verify catches a missing object")

        check(src.objects == before, "the source is byte-identical afterwards")

        ns_p = argparse.Namespace(out=tmp, prefix="web-v1/ID002_y/",
                                  workers=2, dry_run=True, deep=False)
        rc, out = _run(cb.cmd_copy, ns_p)
        check("R2: 2 objects" in out, "--prefix limits the run")

        rc, _ = _run(cb.cmd_snapshot, ns)
        snaps = sorted(Path(tmp).glob("r2_snapshot_*.csv"))
        check(rc == 0 and len(snaps) == 1, "snapshot writes a CSV")
        rc, _ = _run(cb.cmd_diff, argparse.Namespace(a=str(snaps[0]),
                                                     b=str(snaps[0])))
        check(rc == 0, "diff of identical snapshots -> 0")
        other = Path(tmp) / "changed.csv"
        other.write_text(snaps[0].read_text(encoding="utf-8")
                         .replace("other/root.txt", "other/renamed.txt"),
                         encoding="utf-8")
        rc, _ = _run(cb.cmd_diff, argparse.Namespace(a=str(snaps[0]),
                                                     b=str(other)))
        check(rc == 1, "diff of different snapshots -> 1")


# ---------------------------------------------------------------------------
# live: the app's own upload functions against the Railway bucket
# ---------------------------------------------------------------------------

def test_live(read_session: str | None) -> None:
    print("[live: Railway bucket]")
    check(r2.backend() == "s3", f"bucket in use: {r2.describe()}")
    if r2.backend() != "s3":
        return
    client, bucket = r2._client(), r2.bucket_name()  # noqa: SLF001
    prefix = r2._key_prefix()  # noqa: SLF001
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sid = f"_bucket_smoke_test/{ts}"
    print(f"  probe keys under {prefix}{sid}/ in {bucket}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        # Save-a-session shape: database/<sid>/<agent>/<field>.txt + user_inputs.
        sess = tmp_p / "session"
        (sess / "planner").mkdir(parents=True)
        (sess / "user_inputs" / "images").mkdir(parents=True)
        (sess / "planner" / "plan.txt").write_text("plan text", encoding="utf-8")
        (sess / "user_inputs" / "queries.txt").write_text("a query", encoding="utf-8")
        png = b"\x89PNG\r\n\x1a\n" + os.urandom(2048)
        (sess / "user_inputs" / "images" / "front.png").write_bytes(png)
        n = r2.upload_directory(sess, f"{sid}/",
                                suffixes=(".txt", ".png", ".jpg", ".jpeg"))
        check(n == 3, "upload_directory (save: answers + user_inputs) -> 3 files")

        att = tmp_p / "attempt"
        att.mkdir()
        (att / "parameters.json").write_text('{"bladeCount": 4}', encoding="utf-8")
        (att / "description.txt").write_text("attempt 1", encoding="utf-8")
        up, miss = r2.upload_attempt_artefacts(
            att, session_id=sid, attempt_nnn="001", global_attempt_id=0,
            whitelist=("parameters.json", "description.txt", "render_top.png"))
        check(sorted(up) == ["description.txt", "parameters.json"]
              and miss == ["render_top.png"],
              "upload_attempt_artefacts (save: attempts/001__0/)")

        check(r2.upload_bytes(b"safety body", f"{sid}/safety/attempt_001/x.txt"),
              "upload_bytes (save: safety folder)")

        log = tmp_p / "session.log"
        log.write_bytes(b"queue log line\n" * 500)
        check(r2.upload_file(log, f"{sid}/logs/snapshot_{ts}.log"),
              "upload_file (queue-log snapshot)")

    # Read back the way retrieval_common / db_writer_mm do: prefix + key.
    keys: list[str] = []
    for page in client.get_paginator("list_objects_v2").paginate(
            Bucket=bucket, Prefix=f"{prefix}{sid}/"):
        keys += [o["Key"] for o in page.get("Contents", []) or []]
    check(len(keys) == 7, f"paginated list finds all 7 probe objects ({len(keys)})")

    def get(k: str) -> bytes:
        return client.get_object(Bucket=bucket, Key=f"{prefix}{sid}/{k}")["Body"].read()

    check(get("planner/plan.txt") == b"plan text", "GET an answer file")
    check(get("user_inputs/images/front.png") == png, "GET an image, bytes equal")
    check(get("attempts/001__0/parameters.json") == b'{"bladeCount": 4}',
          "GET an attempt artefact (retrieve_attempt path)")
    check(get(f"logs/snapshot_{ts}.log") == b"queue log line\n" * 500,
          "GET the queue-log snapshot")
    head = client.head_object(Bucket=bucket,
                              Key=f"{prefix}{sid}/user_inputs/images/front.png")
    check(head.get("ContentType") == "image/png", "ContentType kept (image/png)")

    resp = client.delete_objects(Bucket=bucket,
                                 Delete={"Objects": [{"Key": k} for k in keys]})
    check(not resp.get("Errors"), "delete_objects (manual-entry rollback path)")
    left = client.list_objects_v2(Bucket=bucket, Prefix=f"{prefix}{sid}/")
    check(not left.get("Contents"), "probe objects are gone")

    if read_session:
        print(f"[live: read session {read_session}]")
        n, size = 0, 0
        for page in client.get_paginator("list_objects_v2").paginate(
                Bucket=bucket, Prefix=f"{prefix}{read_session}/"):
            for o in page.get("Contents", []) or []:
                body = client.get_object(Bucket=bucket, Key=o["Key"])["Body"].read()
                n += 1
                size += len(body)
                if len(body) != o["Size"]:
                    check(False, f"size of {o['Key']}")
        check(n > 0, f"{n} objects, {size} bytes downloaded")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--env-file")
    ap.add_argument("--read-session")
    args = ap.parse_args()

    test_selection()
    test_clients()
    test_copy_script()
    if args.live:
        if args.env_file:
            from dotenv import load_dotenv
            load_dotenv(args.env_file, override=True)
        test_live(args.read_session)

    print()
    if FAILS:
        print(f"FAILED: {len(FAILS)}")
        return 1
    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
