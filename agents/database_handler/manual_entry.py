"""Write ONE hand-curated entry into the RAG database.

A manual entry is stored exactly as a saved session would be, so that
``database_search``, ``retrieve_user_inputs`` and ``retrieve_attempt`` find
it with no special-casing.  What makes it recognisable is its session id:
the ``MANUAL_`` prefix (``retrieval_common.MANUAL_SESSION_PREFIX``) is what
both retrieve tools key their ``origin="manual_upload"`` attribute off, and
it is the single predicate the list/delete views scope themselves to.

It is NOT a design run, and three things follow:

* **No ``extracted_inputs.txt``.**  Nothing ran the User Input Inspector,
  and inventing a four-section extraction would claim a structure the free
  prose does not have.  ``retrieve_user_inputs`` falls back to the raw text
  under ``<user_query>`` with a "manually-written data point" marker.
* **The text is embedded AS WRITTEN** -- ``insert_chunk(skip_stitch=True)``.
  The stitcher exists to naturalise an agent's field/question/answer triple;
  here there is no question and the owner wrote the text deliberately.
* **Nothing is generated.**  No geometry, no mesh, no renders.  This path
  stores what it is given and nothing else.

This module owns the WRITE only.  It deliberately knows nothing about HTTP:
the busy guards (``_TURN_IN_FLIGHT`` / ``_END_IN_FLIGHT`` / ``_BOX.session``
/ ``_require_no_queue``) belong to ``web_app``, which must refuse before
calling in here -- see W13, Stage A is single-user-at-a-time on disk.

Three traps this module exists to get right, each verified 2026-09-15:

1. ``upload_directory``'s ``suffixes`` default is ``(".txt",)``.  Omitting
   the argument uploads no images and no ``.compression.json`` sidecars --
   silently, behind a success return.
2. ``attempt_label`` must be ``<YYYYMMDD>_<HHMMSS>_<NNN>_<slug>``.
   ``retrieve_attempt._ATTEMPT_LABEL_RE`` is ``^\\d+_\\d+_(\\d+)_``, so a
   label with ONE numeric group before the NNN is skipped with only a log
   line, leaving a correct Postgres row the agent is told is ``not_found``.
3b. ``upload_attempt_artefacts``'s ``whitelist`` is a list of FILENAMES, not
   suffixes, and it defaults to ``attempt_artefact_whitelist()`` -- the
   canonical artefact names.  A manual image matches none of them, so passing
   a suffix tuple (or nothing) uploads NOTHING and returns an empty list,
   quietly: the entry then retrieves with parameters and no images.
4. ``dc_attempts.attempt_label`` carries a standalone global ``UNIQUE`` while
   ``upsert_attempt``'s ``ON CONFLICT`` targets ``(session_id,
   attempt_label)`` only, and it has no ``UniqueViolation`` handler.  The
   timestamped label makes a collision practically impossible; the explicit
   handler below turns "practically" into "reported".

Traps 1 and 3b are the same mistake in two places: assuming an upload
helper's filter parameter means what the caller wants it to mean.  Both were
found by a test that counted what actually reached R2.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from dataclasses import dataclass, field as _dc_field
from datetime import datetime
from pathlib import Path

from psycopg import errors as pg_errors

from agents.shared import postgres_pool, r2_uploader
from agents.database_handler import db_writer
from tools import retrieval_common

logger = logging.getLogger("propeller_agent")

# Everything user_inputs/ may carry.  NOT the uploader's default, which is
# (".txt",) -- see trap 1 in the module docstring.
_USER_INPUT_SUFFIXES = (".txt", ".png", ".jpg", ".jpeg", ".json")

# The chunks.field value for curated text.  A new value needs no
# registration: `field` is an optional metafilter key in database_search,
# not a whitelist of values, and the LLM-facing tool pins metafilters=None
# anyway.  Verified 2026-09-15.
FIELD_MANUAL = "User Uploaded Content"
AGENT_MANUAL = "User"

# New entries use the 16-parameter set, like any new session.
SCHEMA_VERSION = 2
DC_NAME = "propeller"


class ManualEntryError(RuntimeError):
    """Refused before anything was written, or rolled back after."""


@dataclass
class ManualImage:
    """One uploaded image, with the two things only the uploader knows."""

    filename: str                 # original name, e.g. "ring_ref.png"
    data: bytes                   # full resolution; never downscaled here
    note: str = ""                # may be blank -- an empty _note.txt is
    #                               still written, so pair_input_images sees
    #                               a valid pair rather than an orphan
    compression_degree: int = 0   # the slider value, 0-100


@dataclass
class ManualEntryResult:
    session_id: str
    attempt_id: int | None
    chunk_outcome: str
    # upload_directory returns a COUNT; upload_attempt_artefacts returns
    # (uploaded_keys, failed_keys).  Kept in the shapes they really are.
    n_user_input_files: int = 0
    r2_attempt_keys: list[str] = _dc_field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate(
    *,
    text: str,
    images: list[ManualImage],
    parameters: dict[str, float],
    is_user_input_image: bool,
    is_render: bool,
) -> None:
    """Raise :class:`ManualEntryError` if the entry could not be retrieved.

    The image rule is not arbitrary: ``retrieve_user_inputs`` only ever
    reads ``<sid>/user_inputs/``, and ``retrieve_attempt`` only ever reads
    an attempt folder.  An image with both toggles off would be stored
    somewhere neither tool looks, so no agent could ever open it.
    """
    if not text or not text.strip():
        raise ManualEntryError("A text query is required; it is the thing "
                               "that gets embedded and searched.")
    if images and not (is_user_input_image or is_render):
        raise ManualEntryError(
            "At least one of 'user input image' / 'render' must be on when "
            "images are attached, or the images would be stored where no "
            "retrieval tool looks.")
    for img in images:
        if Path(img.filename).suffix.lower() not in (".png", ".jpg", ".jpeg"):
            raise ManualEntryError(
                f"{img.filename!r}: only .png / .jpg / .jpeg are accepted.")
        if not 0 <= img.compression_degree <= 100:
            raise ManualEntryError(
                f"{img.filename!r}: compression degree must be 0-100.")
    for name, value in parameters.items():
        try:
            float(value)
        except (TypeError, ValueError):
            raise ManualEntryError(
                f"Parameter {name!r} is not numeric ({value!r}).  "
                f"upsert_attempt_parameters casts with float() outside any "
                f"try/except, so a non-numeric value would abort the whole "
                f"write before a single row landed.") from None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def mint_session_id(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return (retrieval_common.MANUAL_SESSION_PREFIX
            + now.strftime("%Y%m%d_%H%M%S"))


def mint_attempt_label(now: datetime | None = None, *, nnn: str = "001",
                       slug: str = "manual") -> str:
    """``<YYYYMMDD>_<HHMMSS>_<NNN>_<slug>`` -- see trap 2.

    The two numeric groups before the NNN are load-bearing, not cosmetic:
    ``retrieve_attempt`` parses the NNN out of this string and skips any
    attempt whose label does not match.
    """
    now = now or datetime.now()
    return f"{now.strftime('%Y%m%d_%H%M%S')}_{nnn}_{slug}"


def _stage(staging: Path, text: str, images: list[ManualImage], *,
           to_user_inputs: bool, parameters: dict[str, float] | None,
           attempt_nnn: str) -> tuple[Path, Path | None]:
    """Build a session-shaped tree in a throwaway folder.

    Outside ``inputs/`` and ``attempts/`` deliberately: the live tree is the
    running session's, and a half-built manual entry must never be visible
    to anything that walks it.
    """
    ui = staging / "user_inputs"
    ui.mkdir(parents=True, exist_ok=True)
    # Bare prose, no "--- [ts] USER ---" header: a manual entry had no
    # conversation, and fabricating a turn would make the file claim one.
    (ui / "queries.txt").write_text(text, encoding="utf-8")

    if to_user_inputs and images:
        imgs = ui / "images"
        imgs.mkdir(exist_ok=True)
        for img in images:
            stem = Path(img.filename).stem
            (imgs / img.filename).write_bytes(img.data)
            # Written even when blank, so image+note pairing stays valid.
            (imgs / f"{stem}_note.txt").write_text(img.note, encoding="utf-8")
            # BESIDE the image: that is where image_compression.read_degree
            # looks, and it is why .json must be in the suffix list.
            (imgs / f"{stem}.compression.json").write_text(
                json.dumps({"degree": img.compression_degree}),
                encoding="utf-8")

    attempt_dir: Path | None = None
    if parameters is not None:
        attempt_dir = staging / "attempts" / attempt_nnn
        attempt_dir.mkdir(parents=True, exist_ok=True)
        (attempt_dir / "parameters.json").write_text(
            json.dumps(parameters, indent=2), encoding="utf-8")
        for img in images:
            (attempt_dir / img.filename).write_bytes(img.data)
    return ui, attempt_dir


def _rollback(session_id: str) -> None:
    """Undo a half-written entry.

    Deletes the ``sessions`` row -- ``chunks``, ``chunks_mm``,
    ``dc_attempts`` and (two hops, via dc_attempts) ``dc_attempt_parameters``
    all cascade -- then the R2 objects under ``user_inputs/`` and
    ``attempts/``.

    ``<sid>/safety/`` is deliberately NOT deleted: if the text reached the
    safety folder, that copy is the only surviving record of what the owner
    wrote, and destroying it would turn a recoverable failure into a loss.
    """
    try:
        with postgres_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM sessions WHERE session_id = %s",
                            (session_id,))
                conn.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[manual_entry]  rollback: could not delete the "
                       f"sessions row for {session_id}: {exc}")
    try:
        client = r2_uploader._client()               # noqa: SLF001
        if client is None:
            return
        bucket = r2_uploader._env("R2_BUCKET_NAME")  # noqa: SLF001
        for sub in ("user_inputs/", "attempts/"):
            prefix = f"{r2_uploader._key_prefix()}{session_id}/{sub}"  # noqa: SLF001
            keys = []
            for page in client.get_paginator("list_objects_v2").paginate(
                    Bucket=bucket, Prefix=prefix):
                for obj in page.get("Contents", []) or []:
                    keys.append({"Key": obj["Key"]})
            if keys:
                client.delete_objects(Bucket=bucket,
                                      Delete={"Objects": keys})
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[manual_entry]  rollback: R2 cleanup for "
                       f"{session_id} did not complete: {exc}")


def purge_r2(session_id: str) -> int:
    """Delete EVERY R2 object under ONE manual entry, safety folder included.

    REFUSES a session id without the ``MANUAL_`` prefix.  The guarantee lives
    here rather than in the caller: this deletes irreversibly, and the one
    thing it must never be able to do is reach a real saved session because
    someone wired it up wrongly later.

    Distinct from :func:`_rollback`, which KEEPS ``<sid>/safety/`` -- there
    the failure is the system's and that copy may be the only surviving
    record of the text.  Here the owner asked for the entry to go, so it
    goes, safety copy included.

    Returns the number of objects removed.
    """
    if not session_id.startswith(retrieval_common.MANUAL_SESSION_PREFIX):
        raise ManualEntryError(
            f"purge_r2 refuses {session_id!r}: it deletes irreversibly, and "
            f"only manually uploaded entries may be deleted this way.")
    client = r2_uploader._client()                    # noqa: SLF001
    if client is None:
        return 0
    bucket = r2_uploader._env("R2_BUCKET_NAME")       # noqa: SLF001
    prefix = f"{r2_uploader._key_prefix()}{session_id}/"  # noqa: SLF001
    keys = []
    for page in client.get_paginator("list_objects_v2").paginate(
            Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            keys.append({"Key": obj["Key"]})
    for i in range(0, len(keys), 1000):   # delete_objects caps at 1000
        batch = keys[i:i + 1000]
        if batch:
            client.delete_objects(Bucket=bucket, Delete={"Objects": batch})
    logger.info(f"[manual_entry]  purged {len(keys)} R2 objects under "
                f"{session_id}/")
    return len(keys)


# ---------------------------------------------------------------------------
# The write
# ---------------------------------------------------------------------------
def create_manual_entry(
    *,
    text: str,
    images: list[ManualImage] | None = None,
    parameters: dict[str, float] | None = None,
    is_user_input_image: bool = False,
    is_render: bool = False,
    # TRUE by default -- see the note in the endpoint.  `chunks` alone is
    # not enough: which table database_search reads is decided by the
    # Database-options mode, and the live default reads `chunks_mm`.
    mirror_multimodal: bool = True,
) -> ManualEntryResult:
    """Write one curated entry.  Ordered, because each step reads the last.

    Returns the ids the caller needs to verify or later delete the entry.
    Raises :class:`ManualEntryError` having rolled back, rather than leaving
    a ``sessions`` row that no ``chunks`` row points at.
    """
    images = list(images or [])
    parameters = dict(parameters or {})
    validate(text=text, images=images, parameters=parameters,
             is_user_input_image=is_user_input_image, is_render=is_render)

    # An attempt is written when there are parameters to record, OR when
    # images were marked as renders -- otherwise those images would have no
    # attempt folder to live in and retrieve_attempt could never reach them,
    # which is the very thing `validate` refuses.  The handover specifies
    # only the parameters case; this closes the gap it leaves open.
    want_attempt = bool(parameters) or (is_render and bool(images))
    now = datetime.now()
    session_id = mint_session_id(now)
    attempt_label = mint_attempt_label(now)
    attempt_nnn = "001"
    staging = Path(tempfile.mkdtemp(prefix="manual_entry_"))
    attempt_id: int | None = None

    try:
        ui_dir, attempt_dir = _stage(
            staging, text, images,
            to_user_inputs=is_user_input_image,
            parameters=parameters if want_attempt else None,
            attempt_nnn=attempt_nnn)

        # 1. the sessions row.  user_provided_images gates whether
        #    retrieve_user_inputs lists images at all.
        with postgres_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO sessions (session_id, session_ts, dc_name,"
                    " dc_inspector_enabled, schema_version,"
                    " user_provided_images)"
                    " VALUES (%s, NOW(), %s, %s, %s, %s)",
                    (session_id, DC_NAME, False, SCHEMA_VERSION,
                     bool(images) and is_user_input_image))
                conn.commit()

        # 2. the attempt, if any.  Before the R2 upload, because the key
        #    layout embeds the global id the upsert returns.
        if want_attempt:
            try:
                attempt_id = db_writer.upsert_attempt(
                    session_id=session_id,
                    attempt_label=attempt_label,
                    schema_version=SCHEMA_VERSION,
                    parameters_json=parameters,
                    has_geometry=False,
                    has_renders=bool(images) and is_render,
                )
            except pg_errors.UniqueViolation as exc:
                # attempt_label is globally UNIQUE while ON CONFLICT covers
                # (session_id, attempt_label) only -- see trap 3.
                raise ManualEntryError(
                    f"attempt_label {attempt_label!r} already exists under a "
                    f"different session; retry (the label is "
                    f"second-resolution).") from exc
            if parameters:
                db_writer.upsert_attempt_parameters(
                    attempt_id=attempt_id, parameters=parameters)

        # 3. R2, via the existing helpers -- never by hand-building keys.
        n_ui = r2_uploader.upload_directory(
            ui_dir,
            remote_prefix=f"{session_id}/user_inputs/",
            suffixes=_USER_INPUT_SUFFIXES,   # trap 1
        )
        attempt_keys: list[str] = []
        if attempt_dir is not None and attempt_id is not None:
            uploaded, _failed = r2_uploader.upload_attempt_artefacts(
                attempt_dir,
                session_id=session_id,
                attempt_nnn=attempt_nnn,
                global_attempt_id=attempt_id,
                # FILENAMES, not suffixes -- see trap 4.  The default is
                # attempt_artefact_whitelist(), the canonical artefact names,
                # which a manual image never matches.
                whitelist=(["parameters.json"]
                           + [i.filename for i in images]),
            )
            attempt_keys = list(uploaded)

        # 4. the searchable row.  LAST of the required steps: it is the one
        #    that makes the entry findable, so nothing is searchable until
        #    everything it points at exists.
        outcome = db_writer.insert_chunk(
            session_id=session_id,
            attempt_id=attempt_id,
            agent_from=AGENT_MANUAL,
            agents_to=list(db_writer.DEFAULT_AGENTS_TO_ACL),
            field=FIELD_MANUAL,
            field_type="Semantic",
            question=None,
            body=text,
            dc_name=DC_NAME,
            skip_stitch=True,          # embed the text as written
            safety_scope="session",
            safety_filename=f"{session_id}__manual_entry.txt",
        )
        outcome_name = getattr(outcome, "name", str(outcome))
        if outcome_name == "SAFETY":
            # The text is in <sid>/safety/, but nothing is searchable, and a
            # sessions row with no chunks is dead weight that would still
            # show up in the manual-entry list as though it worked.
            raise ManualEntryError(
                "The text could not be embedded; it was written to the R2 "
                "safety folder and the rest of the entry was rolled back.")

        # 5. multimodal mirror.  Reads chunks AND R2, so it can only run
        #    once both exist.  Best-effort BY DESIGN, and that is what
        #    makes defaulting it on safe: a Voyage failure here leaves a
        #    fully working text-only entry rather than losing the upload.
        #
        #    It produces the same row shapes a real saved session gets --
        #    one fused (image + <name>_note.txt) row per user image via
        #    voyage_mm.embed_fused, so the note is the embedding_input,
        #    plus one row per attempt render.
        if mirror_multimodal:
            try:
                from agents.database_handler import db_writer_mm
                db_writer_mm.mirror_session_to_mm(session_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[manual_entry]  multimodal mirror for "
                               f"{session_id} failed (entry is still "
                               f"searchable by text): {exc}")

        logger.info(f"[manual_entry]  wrote {session_id} "
                    f"(attempt_id={attempt_id}, images={len(images)}, "
                    f"params={len(parameters)})")
        return ManualEntryResult(
            session_id=session_id, attempt_id=attempt_id,
            chunk_outcome=outcome_name,
            n_user_input_files=int(n_ui),
            r2_attempt_keys=attempt_keys)

    except ManualEntryError:
        _rollback(session_id)
        raise
    except Exception as exc:  # noqa: BLE001
        _rollback(session_id)
        raise ManualEntryError(
            f"Manual entry {session_id} failed and was rolled back: "
            f"{type(exc).__name__}: {exc}") from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)
