"""Copy every object of the Cloudflare R2 bucket into a Railway bucket.

The source is READ ONLY: the R2 client is wrapped so that only list /
get / head calls go through (any other method raises before a request
is sent), and the R2 token used for the copy should itself be an
"Object Read only" token.  The Cloudflare content stays exactly as it
is; ``snapshot`` + ``diff`` prove it.

Keys are copied one-for-one, prefix included (``web-v1/<sid>/...``):
Postgres stores session-rooted keys and the app adds ``R2_KEY_PREFIX``
at run time, so the Railway service must keep the SAME prefix.

Credentials come from the environment (or ``--env-file``), the same
names the app reads -- see ``agents/shared/r2_uploader.py``:

* source  = the ``R2_*`` set (``R2_ACCOUNT_ID``, ``R2_ACCESS_KEY_ID``,
  ``R2_SECRET_ACCESS_KEY``, ``R2_BUCKET_NAME``, ``R2_JURISDICTION``)
* target  = the ``S3_*`` set (``S3_ENDPOINT_URL``, ``S3_BUCKET``,
  ``S3_ACCESS_KEY_ID``, ``S3_SECRET_ACCESS_KEY``, optional
  ``S3_REGION`` / ``S3_ADDRESSING_STYLE``)

Commands (run from the repository root)::

    py -3.13 extra_utilities/scripts/copy_bucket.py snapshot --env-file X --out DIR
    py -3.13 extra_utilities/scripts/copy_bucket.py copy     --env-file X --out DIR [--dry-run]
    py -3.13 extra_utilities/scripts/copy_bucket.py verify   --env-file X --out DIR [--deep]
    py -3.13 extra_utilities/scripts/copy_bucket.py diff     A.csv B.csv

* ``snapshot`` lists the R2 bucket into ``r2_snapshot_<ts>.csv`` (key,
  size, etag, last_modified).  Take one before and one after the copy.
* ``copy`` copies every R2 object missing from (or different in) the
  target, keeping ContentType, Cache-Control, Content-Encoding,
  Content-Disposition and user metadata.  Each body's MD5 is checked
  against the R2 ETag before the PUT and the target's answer after it.
  Re-runnable: objects already in the target with the same size and
  MD5 are skipped, so a second run after the switch-over picks up only
  what was saved to R2 in between.  ``--dry-run`` only counts.
* ``verify`` compares both listings: every R2 key must be in the target
  with the same size (and MD5 where both ETags are plain MD5s).
  ``--deep`` downloads every target object and checks its MD5.  Keys
  only in the target (sessions saved after the switch-over) are listed
  but are not an error.
* ``diff`` compares two snapshots; exit 1 when they differ.

Every command writes a CSV report into ``--out`` (default: a new
``bucket_copy_<UTC ts>/`` folder in the current directory) and exits 1
on any failure or mismatch.  ``--prefix`` limits a run to one key
prefix (for a first trial on one session).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import logging
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]

# Load the app's bucket module BY FILE PATH so we don't trigger
# agents/__init__'s eager import of the whole agent stack.  The bucket
# settings (endpoints, addressing style, R2 jurisdiction) are therefore
# exactly the ones the app uses.
_spec = importlib.util.spec_from_file_location(
    "r2_uploader", REPO_ROOT / "agents" / "shared" / "r2_uploader.py")
r2_uploader = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r2_uploader)  # type: ignore[union-attr]

logger = logging.getLogger("copy_bucket")

_MD5_ETAG = re.compile(r"^[0-9a-f]{32}$")

# Headers carried over from the source object on copy.
_COPIED_HEADERS = ("ContentType", "CacheControl", "ContentEncoding",
                   "ContentDisposition", "ContentLanguage")


class ReadOnlyClient:
    """A boto3 S3 client that can only read.

    Any method outside :attr:`ALLOWED` raises ``PermissionError`` before
    a request is built, so no code path in this script can write to,
    or delete from, the source bucket.
    """

    ALLOWED = frozenset({"list_objects_v2", "get_object", "head_object",
                         "get_paginator", "head_bucket"})

    def __init__(self, client: Any) -> None:
        self._client = client

    def __getattr__(self, name: str) -> Any:
        if name not in self.ALLOWED:
            raise PermissionError(
                f"copy_bucket: {name!r} is not allowed on the source "
                f"bucket (read only).")
        attr = getattr(self._client, name)
        if name == "get_paginator":
            def _paginator(op: str):
                if op != "list_objects_v2":
                    raise PermissionError(
                        f"copy_bucket: paginator {op!r} is not allowed "
                        f"on the source bucket.")
                return attr(op)
            return _paginator
        return attr


def _clean_etag(etag: str | None) -> str:
    return (etag or "").strip('"').lower()


def _is_md5(etag: str) -> bool:
    return bool(_MD5_ETAG.match(etag))


def _list(client: Any, bucket: str, prefix: str) -> Iterator[dict]:
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            yield {
                "key": obj["Key"],
                "size": int(obj.get("Size", 0)),
                "etag": _clean_etag(obj.get("ETag")),
                "last_modified": (obj["LastModified"].isoformat()
                                  if obj.get("LastModified") else ""),
            }


def _load_env(env_file: str | None) -> None:
    if not env_file:
        return
    from dotenv import load_dotenv
    if not Path(env_file).is_file():
        sys.exit(f"--env-file {env_file} does not exist.")
    # override: the file chosen for this run beats whatever the shell has.
    load_dotenv(env_file, override=True)


def _source() -> tuple[ReadOnlyClient, str]:
    client = r2_uploader.client_for(r2_uploader.BACKEND_R2)
    if client is None:
        sys.exit("Source not configured: set R2_ACCOUNT_ID / "
                 "R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET_NAME.")
    return (ReadOnlyClient(client),
            r2_uploader.bucket_name(r2_uploader.BACKEND_R2))


def _target() -> tuple[Any, str]:
    client = r2_uploader.client_for(r2_uploader.BACKEND_S3)
    if client is None:
        sys.exit("Target not configured: set S3_ENDPOINT_URL / S3_BUCKET / "
                 "S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY.")
    return client, r2_uploader.bucket_name(r2_uploader.BACKEND_S3)


def _out_dir(arg: str | None) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(arg) if arg else Path.cwd() / f"bucket_copy_{ts}"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _human(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{n} B"


# ---------------------------------------------------------------------------
# snapshot / diff
# ---------------------------------------------------------------------------

def cmd_snapshot(args: argparse.Namespace) -> int:
    src, src_bucket = _source()
    out = _out_dir(args.out)
    rows = list(_list(src, src_bucket, args.prefix))
    path = out / f"r2_snapshot_{_ts()}.csv"
    _write_csv(path, ["key", "size", "etag", "last_modified"], rows)
    total = sum(r["size"] for r in rows)
    print(f"R2 bucket {src_bucket}: {len(rows)} objects, {_human(total)} "
          f"-> {path}")
    return 0


def _read_snapshot(path: str) -> dict[str, tuple[str, str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["key"]: (r["size"], r["etag"], r["last_modified"])
                for r in csv.DictReader(fh)}


def cmd_diff(args: argparse.Namespace) -> int:
    a, b = _read_snapshot(args.a), _read_snapshot(args.b)
    gone = sorted(set(a) - set(b))
    new = sorted(set(b) - set(a))
    changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    print(f"{args.a}: {len(a)} objects; {args.b}: {len(b)} objects")
    print(f"  removed: {len(gone)}  added: {len(new)}  changed: {len(changed)}")
    for label, keys in (("removed", gone), ("added", new),
                        ("changed", changed)):
        for k in keys[:20]:
            print(f"    {label}: {k}")
        if len(keys) > 20:
            print(f"    ... {len(keys) - 20} more {label}")
    return 0 if not (gone or new or changed) else 1


# ---------------------------------------------------------------------------
# copy
# ---------------------------------------------------------------------------

def _same(src: dict, dst: dict | None) -> bool:
    """True when *dst* already holds *src*'s bytes (size + MD5 if known)."""
    if dst is None or dst["size"] != src["size"]:
        return False
    if _is_md5(src["etag"]) and _is_md5(dst["etag"]):
        return src["etag"] == dst["etag"]
    # A multipart ETag on either side is not an MD5: size has to do.
    return True


def _copy_one(src: ReadOnlyClient, src_bucket: str, dst: Any,
              dst_bucket: str, obj: dict) -> dict:
    row = dict(obj, md5="", target_etag="", status="", detail="")
    try:
        resp = src.get_object(Bucket=src_bucket, Key=obj["key"])
        body = resp["Body"].read()
        md5 = hashlib.md5(body).hexdigest()
        row["md5"] = md5
        if len(body) != obj["size"]:
            row.update(status="failed",
                       detail=f"read {len(body)} bytes, listed {obj['size']}")
            return row
        if _is_md5(obj["etag"]) and md5 != obj["etag"]:
            row.update(status="failed", detail="body MD5 != R2 ETag")
            return row
        put: dict[str, Any] = {"Bucket": dst_bucket, "Key": obj["key"],
                               "Body": body}
        for h in _COPIED_HEADERS:
            if resp.get(h):
                put[h] = resp[h]
        if resp.get("Metadata"):
            put["Metadata"] = resp["Metadata"]
        answer = dst.put_object(**put)
        target_etag = _clean_etag(answer.get("ETag"))
        row["target_etag"] = target_etag
        if _is_md5(target_etag) and target_etag != md5:
            row.update(status="failed", detail="target ETag != body MD5")
            return row
        row["status"] = "copied"
        return row
    except Exception as exc:  # noqa: BLE001 — reported per key
        row.update(status="failed", detail=f"{type(exc).__name__}: {exc}")
        return row


def cmd_copy(args: argparse.Namespace) -> int:
    src, src_bucket = _source()
    dst, dst_bucket = _target()
    out = _out_dir(args.out)
    print(f"source: R2 bucket {src_bucket} (read only)")
    print(f"target: {dst_bucket} at "
          f"{r2_uploader._endpoint_url(r2_uploader.BACKEND_S3)}")  # noqa: SLF001

    src_objs = list(_list(src, src_bucket, args.prefix))
    dst_objs = {o["key"]: o for o in _list(dst, dst_bucket, args.prefix)}
    todo = [o for o in src_objs if not _same(o, dst_objs.get(o["key"]))]
    skipped = [dict(o, status="skipped", detail="already in target")
               for o in src_objs if _same(o, dst_objs.get(o["key"]))]
    total = sum(o["size"] for o in src_objs)
    todo_bytes = sum(o["size"] for o in todo)
    print(f"R2: {len(src_objs)} objects, {_human(total)}; target already "
          f"has {len(skipped)}; to copy: {len(todo)} ({_human(todo_bytes)})")
    if args.dry_run:
        print("--dry-run: nothing copied.")
        return 0

    rows: list[dict] = list(skipped)
    lock = threading.Lock()
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(_copy_one, src, src_bucket, dst, dst_bucket, o)
                   for o in todo]
        for fut in as_completed(futures):
            row = fut.result()
            with lock:
                rows.append(row)
                done += 1
                if row["status"] == "failed":
                    print(f"  FAILED {row['key']}: {row['detail']}")
                if done % 200 == 0 or done == len(todo):
                    print(f"  {done}/{len(todo)}")

    rows.sort(key=lambda r: r["key"])
    path = out / f"copy_report_{_ts()}.csv"
    _write_csv(path, ["key", "size", "etag", "md5", "target_etag",
                      "status", "detail"], rows)
    failed = [r for r in rows if r["status"] == "failed"]
    copied = [r for r in rows if r["status"] == "copied"]
    print(f"copied {len(copied)}, skipped {len(skipped)}, "
          f"failed {len(failed)} -> {path}")
    return 1 if failed else 0


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

def cmd_verify(args: argparse.Namespace) -> int:
    src, src_bucket = _source()
    dst, dst_bucket = _target()
    out = _out_dir(args.out)
    src_objs = {o["key"]: o for o in _list(src, src_bucket, args.prefix)}
    dst_objs = {o["key"]: o for o in _list(dst, dst_bucket, args.prefix)}

    rows: list[dict] = []
    for key, s in sorted(src_objs.items()):
        d = dst_objs.get(key)
        if d is None:
            rows.append(dict(s, status="missing", detail="not in target"))
        elif d["size"] != s["size"]:
            rows.append(dict(s, status="mismatch",
                             detail=f"target size {d['size']}"))
        elif (_is_md5(s["etag"]) and _is_md5(d["etag"])
              and s["etag"] != d["etag"]):
            rows.append(dict(s, status="mismatch", detail="ETag differs"))
        else:
            rows.append(dict(s, status="ok", detail=(
                "size+md5" if _is_md5(s["etag"]) and _is_md5(d["etag"])
                else "size only")))

    if args.deep:
        def _check(row: dict) -> dict:
            if row["status"] != "ok":
                return row
            try:
                body = dst.get_object(Bucket=dst_bucket,
                                      Key=row["key"])["Body"].read()
            except Exception as exc:  # noqa: BLE001
                return dict(row, status="mismatch",
                            detail=f"GET failed: {type(exc).__name__}")
            md5 = hashlib.md5(body).hexdigest()
            if len(body) != row["size"] or (
                    _is_md5(row["etag"]) and md5 != row["etag"]):
                return dict(row, status="mismatch",
                            detail="downloaded bytes differ")
            return dict(row, detail="downloaded, md5 ok")
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            rows = list(pool.map(_check, rows))

    only_target = [dict(d, status="target_only", detail="saved after copy?")
                   for k, d in sorted(dst_objs.items()) if k not in src_objs]
    path = out / f"verify_report_{_ts()}.csv"
    _write_csv(path, ["key", "size", "etag", "status", "detail"],
               rows + only_target)
    bad = [r for r in rows if r["status"] != "ok"]
    src_bytes = sum(o["size"] for o in src_objs.values())
    dst_bytes = sum(o["size"] for k, o in dst_objs.items() if k in src_objs)
    print(f"R2: {len(src_objs)} objects, {_human(src_bytes)}; target holds "
          f"{len(src_objs) - len([r for r in rows if r['status'] == 'missing'])}"
          f" of them, {_human(dst_bytes)}; target-only: {len(only_target)}")
    for r in bad[:20]:
        print(f"  {r['status'].upper()} {r['key']}: {r['detail']}")
    print(("OK" if not bad else f"{len(bad)} PROBLEM(S)") + f" -> {path}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy the Cloudflare R2 bucket into a Railway bucket "
                    "(R2 is never written).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("snapshot", "copy", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--env-file", help="a .env file with the R2_* and "
                       "S3_* variables (overrides the shell's)")
        p.add_argument("--out", help="folder for the CSV reports")
        p.add_argument("--prefix", default="",
                       help="only keys starting with this (full key, "
                            "prefix included, e.g. web-v1/ID097_...)")
        if name != "snapshot":
            p.add_argument("--workers", type=int, default=8)
        if name == "copy":
            p.add_argument("--dry-run", action="store_true")
        if name == "verify":
            p.add_argument("--deep", action="store_true",
                           help="download every target object and check "
                                "its MD5")
    d = sub.add_parser("diff")
    d.add_argument("a")
    d.add_argument("b")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    if args.cmd == "diff":
        return cmd_diff(args)
    _load_env(args.env_file)
    return {"snapshot": cmd_snapshot, "copy": cmd_copy,
            "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
