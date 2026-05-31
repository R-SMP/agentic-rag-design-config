"""Smoke-test the Cloudflare R2 mirror used by the Database Handler.

Walks through every step that has to succeed for the DH's end-of-save
``upload_directory`` call to actually push files to R2.  Each step is
isolated and reported individually so a failure points at the exact
break (env var missing, boto3 not installed, auth bad, bucket name
wrong, network blocked, etc.) rather than the generic ``[R2] upload
failed`` warning the production path logs.

Usage
-----
Inside the running container::

    docker compose --env-file <project>/.env exec app \\
        python extra_utilities/smoke_test_r2_upload.py

Exits 0 when every step passes, 1 otherwise.  Always prints a tail
summary so the user can paste the output here to debug.

The script does NOT depend on a Session / Orchestrator / Streamlit
context — it imports only ``agents/shared/r2_uploader.py`` and
boto3 directly.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

# When this script is invoked as ``python extra_utilities/smoke_test_…``,
# Python puts ``extra_utilities/`` (not the project root) on sys.path
# first, so ``import agents…`` cannot find the package.  Prepend the
# project root explicitly — same one-liner the existing
# ``smoke_test_base_chain_agent.py`` uses.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Small reporting helpers — keep output simple and grep-friendly.
# ---------------------------------------------------------------------------

_OK = 0
_FAIL = 1
_RESULT = _OK


def _hdr(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def _ok(msg: str) -> None:
    print(f"  OK   {msg}")


def _fail(msg: str, exc: BaseException | None = None) -> None:
    global _RESULT
    _RESULT = _FAIL
    print(f"  FAIL {msg}")
    if exc is not None:
        print(f"       {type(exc).__name__}: {exc}")


def _info(msg: str) -> None:
    print(f"  ..   {msg}")


def _mask(value: str, head: int = 4, tail: int = 4) -> str:
    if not value:
        return "(empty)"
    if len(value) <= head + tail:
        return "*" * len(value)
    return f"{value[:head]}…{value[-tail:]}  (len={len(value)})"


# ---------------------------------------------------------------------------
# 1. Env vars present?
# ---------------------------------------------------------------------------
_hdr("Step 1 — environment variables")

REQUIRED = (
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET_NAME",
)
OPTIONAL = ("R2_KEY_PREFIX", "R2_JURISDICTION")

env_values: dict[str, str] = {}
missing: list[str] = []
for name in REQUIRED:
    raw = (os.environ.get(name) or "").strip()
    env_values[name] = raw
    if not raw:
        missing.append(name)
    elif name == "R2_ACCOUNT_ID":
        _ok(f"{name} = {_mask(raw, head=6, tail=4)}")
    elif name == "R2_BUCKET_NAME":
        _ok(f"{name} = {raw!r}")
    else:
        _ok(f"{name} = {_mask(raw)}")

for name in OPTIONAL:
    raw = (os.environ.get(name) or "").strip()
    env_values[name] = raw
    _info(f"{name} = {raw!r} (optional)")

if missing:
    _fail(f"missing required env vars: {', '.join(missing)}")
    print()
    print("→ Add the listed names to your project-root .env file, then")
    print("  recreate the container so they propagate:")
    print()
    print("    docker compose --env-file <project>/.env up -d "
          "--force-recreate")
    print()
    print("  …then re-run this script.  Stopping here.")
    sys.exit(_RESULT)


# ---------------------------------------------------------------------------
# 2. boto3 + r2_uploader importable?
# ---------------------------------------------------------------------------
_hdr("Step 2 — boto3 + r2_uploader import")

try:
    import boto3  # noqa: F401
    from botocore.config import Config  # noqa: F401
    from botocore.exceptions import ClientError  # noqa: F401
    _ok("boto3 + botocore imported")
except Exception as exc:
    _fail("boto3 / botocore import failed — is it in the running image?", exc)
    print()
    print("→ ``boto3>=1.34.0`` was added to requirements.txt; the running")
    print("  image must be rebuilt with ``--build`` so pip installs it.")
    print()
    print("    docker compose --env-file <project>/.env up -d --build")
    print()
    sys.exit(_RESULT)

try:
    from agents.shared import r2_uploader  # noqa: E402
    _ok(f"agents.shared.r2_uploader imported from {r2_uploader.__file__}")
except Exception as exc:
    _fail("could not import agents.shared.r2_uploader", exc)
    sys.exit(_RESULT)

if not r2_uploader.is_enabled():
    _fail(
        "r2_uploader.is_enabled() returned False — one of the four "
        "required env vars is still empty inside the module."
    )
    sys.exit(_RESULT)
_ok("r2_uploader.is_enabled() = True")


# ---------------------------------------------------------------------------
# 3. boto3 client construction + endpoint URL
# ---------------------------------------------------------------------------
_hdr("Step 3 — boto3 client + endpoint URL")

# Build the endpoint via r2_uploader's own helper so the smoke
# matches production behaviour for R2_JURISDICTION exactly.
endpoint = r2_uploader._endpoint_url()
_info(f"endpoint URL  = {endpoint}")
_info(
    f"jurisdiction = "
    f"{env_values.get('R2_JURISDICTION', '') or '(standard)'!r}"
)
_info(f"bucket       = {env_values['R2_BUCKET_NAME']!r}")
_info(f"key prefix   = {env_values.get('R2_KEY_PREFIX', '')!r}")

try:
    client = r2_uploader._client()  # uses the same code path the DH uses
    if client is None:
        _fail("r2_uploader._client() returned None")
        sys.exit(_RESULT)
    _ok("client constructed")
except Exception as exc:
    _fail("r2_uploader._client() raised", exc)
    sys.exit(_RESULT)


# ---------------------------------------------------------------------------
# 4. Auth check via list_objects_v2 (probes auth + bucket existence).
#    AccessDenied here is EXPECTED for the default "Object Read &
#    Write" R2 token — those tokens grant put/get but NOT ListBucket.
#    We fall through to Step 5 (put_object), which is what the DH
#    actually does at runtime.
# ---------------------------------------------------------------------------
_hdr("Step 4 — auth probe (list_objects_v2, MaxKeys=1)")

bucket = env_values["R2_BUCKET_NAME"]
list_permitted = False
try:
    resp = client.list_objects_v2(Bucket=bucket, MaxKeys=1)
    n = resp.get("KeyCount", 0)
    _ok(f"bucket reachable + list allowed; {n} object(s) returned")
    list_permitted = True
    if n > 0:
        sample = resp["Contents"][0]
        _info(
            f"sample existing key = {sample.get('Key')!r} "
            f"({sample.get('Size', 0)} bytes)"
        )
except Exception as exc:
    msg = str(exc).lower()
    if "accessdenied" in msg or "access denied" in msg:
        _info(
            "list_objects_v2 returned AccessDenied — this is EXPECTED "
            "for object-level R2 tokens.  Such tokens grant put/get "
            "but not ListBucket; the DH only uses put, so this is not "
            "a problem."
        )
        _info("→ continuing with the put_object checks…")
    elif "invalidaccesskeyid" in msg:
        _fail(
            "Access Key ID does not exist on this Cloudflare account.",
            exc,
        )
        print("       → Re-issue the R2 API token in the dashboard.")
        sys.exit(_RESULT)
    elif "signaturedoesnotmatch" in msg:
        _fail(
            "Secret Access Key is wrong (or copied with stray "
            "whitespace).",
            exc,
        )
        print("       → Re-issue the R2 API token; copy the secret freshly.")
        sys.exit(_RESULT)
    elif "nosuchbucket" in msg:
        _fail(
            "Bucket name does not exist on this Cloudflare account.",
            exc,
        )
        print(
            "       → R2_BUCKET_NAME must be the literal bucket name "
            "(no path).  Check the dashboard for the exact name."
        )
        sys.exit(_RESULT)
    elif "could not connect" in msg or "name or service not known" in msg:
        _fail(
            "Network: the container cannot reach the R2 endpoint.",
            exc,
        )
        print(
            "       → Verify R2_ACCOUNT_ID and the container's outbound "
            "DNS / firewall."
        )
        sys.exit(_RESULT)
    else:
        # Unknown error — fail loudly so the user sees it but ALSO
        # fall through to the put_object check, which may still
        # succeed and is the truer signal for the DH's case.
        _fail(
            "list_objects_v2 failed with an unexpected error.  "
            "Falling through to put_object checks anyway — the DH "
            "only writes, so put is what matters at runtime.",
            exc,
        )


# ---------------------------------------------------------------------------
# 5. Direct put_object — bypasses the uploader helper so we know any
#    failure here is purely a boto3 / R2 problem.
# ---------------------------------------------------------------------------
_hdr("Step 5 — direct put_object (boto3 path)")

ts = int(time.time())
direct_key = f"_smoke_tests/direct_{ts}.txt"
direct_body = (
    f"R2 smoke test — direct put_object\n"
    f"timestamp: {ts}\n"
    f"endpoint:  {endpoint}\n"
    f"bucket:    {bucket}\n"
)
try:
    client.put_object(
        Bucket=bucket,
        Key=direct_key,
        Body=direct_body.encode("utf-8"),
        ContentType="text/plain",
    )
    _ok(f"put_object succeeded — key = {direct_key!r}")
except Exception as exc:
    _fail("put_object failed", exc)
    sys.exit(_RESULT)


# ---------------------------------------------------------------------------
# 6. r2_uploader.upload_file — same path the DH uses for one file.
# ---------------------------------------------------------------------------
_hdr("Step 6 — r2_uploader.upload_file (single file)")

with tempfile.NamedTemporaryFile(
    mode="w", suffix=".txt", delete=False, encoding="utf-8"
) as tmp:
    tmp.write(
        f"R2 smoke test — r2_uploader.upload_file\n"
        f"timestamp: {ts}\n"
        f"bucket:    {bucket}\n"
    )
    tmp_path = Path(tmp.name)

try:
    uploader_key = f"_smoke_tests/uploader_{ts}.txt"
    ok = r2_uploader.upload_file(tmp_path, uploader_key)
    if ok:
        _ok(
            f"upload_file returned True — key = "
            f"{r2_uploader._key_prefix() + uploader_key!r}"
        )
    else:
        _fail("upload_file returned False (see the log warning above)")
finally:
    try:
        tmp_path.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# 7. r2_uploader.upload_directory — the exact call the DH makes.
# ---------------------------------------------------------------------------
_hdr("Step 7 — r2_uploader.upload_directory (mirrors the DH path)")

with tempfile.TemporaryDirectory(prefix="r2_smoke_") as td:
    root = Path(td)
    # Mimic the DH layout: <session>/<agent>/<field>.txt
    session_id = f"_smoke_tests/session_{ts}"
    (root / "orchestrator").mkdir(parents=True, exist_ok=True)
    (root / "receptionist").mkdir(parents=True, exist_ok=True)
    (root / "orchestrator" / "session_summary.txt").write_text(
        "--- Session ID ---\n_smoke_test\n\n"
        "--- Field ---\nSession summary\n\n"
        "--- Answer ---\nGenerated by smoke_test_r2_upload.py\n",
        encoding="utf-8",
    )
    (root / "receptionist" / "user_query_problem.txt").write_text(
        "--- Session ID ---\n_smoke_test\n\n"
        "--- Field ---\nUser query problem\n\n"
        "--- Answer ---\nNo problems detected.\n",
        encoding="utf-8",
    )
    # Sidecar that should NOT be uploaded (suffix filter = .txt only).
    (root / "orchestrator" / "session_summary.meta.json").write_text(
        '{"smoke_test": true}\n', encoding="utf-8"
    )

    try:
        n_up = r2_uploader.upload_directory(
            root,
            remote_prefix=session_id,
            suffixes=(".txt",),
        )
        if n_up == 2:
            _ok(f"upload_directory returned {n_up} (matches 2 .txt files)")
        else:
            _fail(
                f"upload_directory returned {n_up}, expected 2 — "
                "some files failed silently (see warnings above)."
            )
    except Exception as exc:
        _fail("upload_directory raised", exc)


# ---------------------------------------------------------------------------
# 7b. r2_uploader.upload_attempt_artefacts — the Path 1 (per-attempt)
#     call the DH makes inside the force-tool turn.  Regression test
#     for the doubled-prefix bug: the resulting key MUST contain
#     ``R2_KEY_PREFIX`` exactly once, even when R2_KEY_PREFIX is set.
# ---------------------------------------------------------------------------
_hdr("Step 7b — r2_uploader.upload_attempt_artefacts (Path 1 / regression)")

with tempfile.TemporaryDirectory(prefix="r2_smoke_attempt_") as td:
    attempt_dir = Path(td)
    # The whitelist drives which files inside attempt_dir get uploaded.
    # Drop one file from each side — present and absent — so we cover
    # both ``uploaded`` and ``missing`` return shapes.
    (attempt_dir / "description.txt").write_text(
        "smoke test description\n", encoding="utf-8"
    )
    (attempt_dir / "parameters.json").write_text(
        '{"smoke_test": true}\n', encoding="utf-8"
    )
    # Intentionally do NOT create propeller_mesh.obj / render_*.png so
    # the function reports them as missing.

    smoke_sid = f"_smoke_tests/session_{ts}"
    smoke_nnn = "999"
    try:
        uploaded, missing = r2_uploader.upload_attempt_artefacts(
            attempt_dir,
            session_id=smoke_sid,
            attempt_id=smoke_nnn,
        )
    except Exception as exc:
        _fail("upload_attempt_artefacts raised", exc)
    else:
        if set(uploaded) == {"description.txt", "parameters.json"}:
            _ok(
                f"upload_attempt_artefacts: 2 uploaded "
                f"({uploaded}), {len(missing)} missing"
            )
        else:
            _fail(
                f"upload_attempt_artefacts: uploaded={uploaded!r} "
                f"(expected description.txt + parameters.json)"
            )

        # Regression: verify the resulting R2 key has the prefix
        # exactly once.  We can't list the bucket on object-only
        # tokens, so we head_object the deterministic key shape
        # produced by upload_attempt_artefacts.
        prefix = r2_uploader._key_prefix()
        expected_key = (
            f"{prefix}{smoke_sid}/attempts/{smoke_nnn}/"
            f"{smoke_sid}__{smoke_nnn}__description.txt"
        )
        try:
            client.head_object(Bucket=bucket, Key=expected_key)
            _ok(
                f"head_object found the expected key — prefix applied "
                f"EXACTLY ONCE: {expected_key!r}"
            )
        except Exception as exc:
            _fail(
                f"head_object on {expected_key!r} failed — Path 1 "
                f"may be writing to a different key shape "
                f"(doubled-prefix regression?)",
                exc,
            )
            # Probe the doubled-prefix path explicitly so the failure
            # message can pinpoint the regression vs. some other issue.
            if prefix:
                doubled_key = (
                    f"{prefix}{prefix}{smoke_sid}/attempts/{smoke_nnn}/"
                    f"{smoke_sid}__{smoke_nnn}__description.txt"
                )
                try:
                    client.head_object(Bucket=bucket, Key=doubled_key)
                    print(
                        f"       → DOUBLED-PREFIX regression confirmed: "
                        f"key {doubled_key!r} EXISTS.  See "
                        f"agents/shared/r2_uploader.py:"
                        f"upload_attempt_artefacts."
                    )
                except Exception:
                    print(
                        "       → doubled-prefix path also empty; "
                        "the failure is something else (auth? bucket?)."
                    )


# ---------------------------------------------------------------------------
# 8. List back what we just uploaded — only if the token permits it.
#    Object-level R2 tokens get AccessDenied here; that's fine, the
#    Cloudflare dashboard is the source of truth for those tokens.
# ---------------------------------------------------------------------------
_hdr("Step 8 — list back the smoke-test keys")

if not list_permitted:
    _info(
        "skipping — this R2 token does not have ListBucket permission "
        "(Step 4 returned AccessDenied)."
    )
    print(
        "       → Open the Cloudflare R2 dashboard for bucket "
        f"{bucket!r} and verify the keys under "
        f"{r2_uploader._key_prefix() + '_smoke_tests/'!r}."
    )
    print(
        "       → If you want list-back to work here, create a "
        "second R2 API token with broader scope (Admin Read & Write, "
        "or Object + ListBucket) and use it for this script only."
    )
else:
    try:
        list_prefix = r2_uploader._key_prefix() + "_smoke_tests/"
        resp = client.list_objects_v2(Bucket=bucket, Prefix=list_prefix)
        keys = [obj.get("Key") for obj in (resp.get("Contents") or [])]
        if keys:
            _ok(f"{len(keys)} key(s) present under prefix {list_prefix!r}:")
            for k in keys:
                print(f"       - {k}")
        else:
            _fail(
                "no keys returned under the smoke-test prefix — earlier "
                "uploads claimed success but nothing landed.  Check the "
                "Cloudflare R2 dashboard manually under bucket "
                f"{bucket!r}."
            )
    except Exception as exc:
        _fail("list_objects_v2 on the smoke prefix failed", exc)


# ---------------------------------------------------------------------------
# Tail summary
# ---------------------------------------------------------------------------
_hdr("Summary")
if _RESULT == _OK:
    print("  ALL STEPS PASSED.  The R2 mirror is reachable from this")
    print("  container.  The DH's end-of-save upload should now work.")
    print()
    print(
        f"  Smoke-test keys left in the bucket under "
        f"{r2_uploader._key_prefix() + '_smoke_tests/'!r} — delete "
        "them when you're done if you'd rather keep the bucket clean."
    )
else:
    print("  ONE OR MORE STEPS FAILED — see the FAIL lines above.")
    print()
    print("  Paste the full output of this script (it does not print")
    print("  secret values) so the failure mode can be diagnosed.")

sys.exit(_RESULT)
