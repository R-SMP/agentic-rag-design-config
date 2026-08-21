"""Populate dc_parameter_schemas with the current propeller DC parameter set.

This script is the source-of-truth Python representation of the
propeller DC parameter inventory: ``schema_version = 1`` (17 params —
history) and ``schema_version = 2`` (16 params — ``impellerHeight``
removed, the CURRENT set new sessions use).  It mirrors
``DC_prompt_fragments/dc_config/parameters.md`` and
``DC_prompt_fragments/dc_config/parameter_keys.txt`` exactly — keep
the three in sync if any change here lands.

Usage (from the repo root):
    python extra_utilities/db_design/populate_dc_parameter_schemas.py

Reads DATABASE_PUBLIC_URL (preferred for local dev) or DATABASE_URL
from the repo-root .env via the same load_dotenv() pattern as
config.py.

Idempotent: ``INSERT ... ON CONFLICT (schema_version, param_name) DO
NOTHING`` means re-running the script after the rows are present is a
no-op.

When schema_version evolves (per architecture doc §1 evolution rules
— add / remove / rename a parameter, or change a range), DO NOT
mutate the V1 list below. Instead:
  1. Add a new constant, e.g. PROPELLER_DC_PARAMETERS_V2.
  2. Update main() to accept the target version on the command line
     (or insert both V1 and V2 in one run; both are immutable history).
  3. For retirements: don't delete from V1 — set retired_at on the V1
     row directly (UPDATE dc_parameter_schemas SET retired_at = NOW()
     WHERE schema_version = 1 AND param_name = '...').
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(REPO_ROOT / ".env")


# ------------------------------------------------------------------
# Immutable per-version parameter sets.  Each schema_version is history:
# rows are only ever APPENDED (INSERT ... ON CONFLICT DO NOTHING), never
# overwritten or deleted.  Mirrors DC_prompt_fragments/dc_config/parameters.md.
# ------------------------------------------------------------------
PROPELLER_DC_PARAMETERS_V1 = [
    # Global / ring
    {"param_name": "bladeCount",        "min_value": 3,    "max_value": 6,    "unit": "count",            "description": "Number of blades"},
    {"param_name": "impellerRadius",    "min_value": 60,   "max_value": 80,   "unit": "mm",               "description": "Outer radius of the impeller ring"},
    {"param_name": "impellerHeight",    "min_value": 4,    "max_value": 10,   "unit": "mm",               "description": "Height of the outer ring"},
    {"param_name": "impellerThickness", "min_value": 1,    "max_value": 5,    "unit": "mm",               "description": "Wall thickness of the outer ring"},
    # Inner blade section
    {"param_name": "innerThickness",    "min_value": 3,    "max_value": 24,   "unit": "% of chord",       "description": "Inner blade section profile thickness"},
    {"param_name": "innerMaxPos",       "min_value": 2,    "max_value": 8,    "unit": "tenths of chord",  "description": "Inner blade section chordwise position of max camber (high-point)"},
    {"param_name": "innerCamber",       "min_value": 0,    "max_value": 9,    "unit": "% of chord",       "description": "Inner blade section profile camber"},
    {"param_name": "innerChord",        "min_value": 3,    "max_value": 11,   "unit": "mm",               "description": "Inner blade section chord length"},
    {"param_name": "innerAngle",        "min_value": 2,    "max_value": 25,   "unit": "degrees",          "description": "Inner blade section angle of attack"},
    # Middle blade section
    {"param_name": "middlePos",         "min_value": 0.3,  "max_value": 0.7,  "unit": "x impellerRadius", "description": "Middle blade section radial position as multiplier of propeller radius"},
    {"param_name": "middleChord",       "min_value": 10,   "max_value": 30,   "unit": "mm",               "description": "Middle blade section chord length"},
    {"param_name": "middleAngle",       "min_value": 2,    "max_value": 25,   "unit": "degrees",          "description": "Middle blade section angle of attack"},
    # Outer blade section
    {"param_name": "outerThickness",    "min_value": 3,    "max_value": 24,   "unit": "% of chord",       "description": "Outer blade section profile thickness"},
    {"param_name": "outerMaxPos",       "min_value": 2,    "max_value": 8,    "unit": "tenths of chord",  "description": "Outer blade section chordwise position of max camber (high-point)"},
    {"param_name": "outerCamber",       "min_value": 0,    "max_value": 9,    "unit": "% of chord",       "description": "Outer blade section profile camber"},
    {"param_name": "outerChord",        "min_value": 10,   "max_value": 30,   "unit": "mm",               "description": "Outer blade section chord length"},
    {"param_name": "outerAngle",        "min_value": 2,    "max_value": 25,   "unit": "degrees",          "description": "Outer blade section angle of attack"},
]

assert len(PROPELLER_DC_PARAMETERS_V1) == 17, (
    f"Expected exactly 17 propeller parameters, got {len(PROPELLER_DC_PARAMETERS_V1)}. "
    "Cross-check against DC_prompt_fragments/dc_config/parameters.md."
)

# schema_version = 2 — impellerHeight REMOVED (the outer-ring height is now
# DERIVED from the outer blade section, not an input; see
# tools/generate_mesh/ring_height.py).  The CURRENT set new sessions use
# (agents/shared/session.py schema_version default = 2).  APPENDED alongside
# V1; V1's rows (including its impellerHeight row) are left untouched as
# history.  Derived from V1 as independent dict copies so the 16 shared
# params stay identical to V1's.
PROPELLER_DC_PARAMETERS_V2 = [
    dict(row) for row in PROPELLER_DC_PARAMETERS_V1
    if row["param_name"] != "impellerHeight"
]

assert len(PROPELLER_DC_PARAMETERS_V2) == 16, (
    f"Expected exactly 16 V2 propeller parameters (V1 minus impellerHeight), "
    f"got {len(PROPELLER_DC_PARAMETERS_V2)}."
)

# Every schema version to (idempotently, append-only) populate.
_SCHEMA_SETS: dict[int, list] = {
    1: PROPELLER_DC_PARAMETERS_V1,
    2: PROPELLER_DC_PARAMETERS_V2,
}


def main() -> int:
    url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    url_source = (
        "DATABASE_PUBLIC_URL"
        if os.environ.get("DATABASE_PUBLIC_URL")
        else "DATABASE_URL"
    )
    if not url:
        print(
            f"Neither DATABASE_PUBLIC_URL nor DATABASE_URL is set in environment. "
            f"Expected to find at least one in {REPO_ROOT / '.env'}",
            file=sys.stderr,
        )
        return 2

    try:
        host_db = url.split("@", 1)[1]
    except IndexError:
        host_db = "<unparseable url>"

    print(f"Using connection URL from {url_source}.")
    print(f"Populating dc_parameter_schemas at {host_db}")
    print(f"  schema versions: {sorted(_SCHEMA_SETS)}  (APPEND-only)")
    print()

    # APPEND each version's rows.  ON CONFLICT DO NOTHING never overwrites an
    # existing row, so re-running is safe and prior versions stay immutable.
    with psycopg.connect(url, autocommit=True) as conn:
        with conn.cursor() as cur:
            for version, rows in sorted(_SCHEMA_SETS.items()):
                inserted = skipped = 0
                for row in rows:
                    cur.execute(
                        """
                        INSERT INTO dc_parameter_schemas
                            (schema_version, param_name, min_value, max_value, unit, description)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (schema_version, param_name) DO NOTHING
                        """,
                        (
                            version,
                            row["param_name"],
                            row["min_value"],
                            row["max_value"],
                            row["unit"],
                            row["description"],
                        ),
                    )
                    if cur.rowcount == 1:
                        inserted += 1
                    else:
                        skipped += 1
                print(f"  schema_version {version}: {len(rows)} params — "
                      f"inserted {inserted}, skipped {skipped} (already present)")

    print()
    # Verification: read back each version.
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            for version in sorted(_SCHEMA_SETS):
                print(f"Rows WHERE schema_version = {version}:")
                print(f"  {'param_name':22s} {'min':>8s}   {'max':>8s}   {'unit':<22s} description")
                print(f"  {'-'*22} {'-'*8}   {'-'*8}   {'-'*22} {'-'*40}")
                cur.execute(
                    """
                    SELECT param_name, min_value, max_value, unit, description, retired_at
                    FROM dc_parameter_schemas
                    WHERE schema_version = %s
                    ORDER BY param_name
                    """,
                    (version,),
                )
                for name, mn, mx, unit, desc, retired in cur.fetchall():
                    marker = "  (retired)" if retired is not None else ""
                    desc_short = (desc or "")[:40]
                    print(f"  {name:22s} {mn:>8}   {mx:>8}   {(unit or ''):22s} {desc_short}{marker}")
                print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
