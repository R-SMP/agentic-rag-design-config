"""Populate dc_parameter_schemas with the current propeller DC parameter set.

This script is the source-of-truth Python representation of the
propeller DC parameter inventory at ``schema_version = 1``. It mirrors
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
# Source of truth: schema_version = 1
# Mirrors DC_prompt_fragments/dc_config/parameters.md
# ------------------------------------------------------------------
SCHEMA_VERSION = 1

PROPELLER_DC_PARAMETERS_V1 = [
    # Global / ring
    {"param_name": "bladeCount",        "min_value": 3,    "max_value": 6,    "unit": "count",            "description": "Number of blades"},
    {"param_name": "impellerRadius",    "min_value": 60,   "max_value": 80,   "unit": "mm",               "description": "Outer radius of the impeller ring"},
    {"param_name": "impellerHeight",    "min_value": 4,    "max_value": 10,   "unit": "mm",               "description": "Height of the outer ring"},
    {"param_name": "impellerThickness", "min_value": 1,    "max_value": 5,    "unit": "mm",               "description": "Wall thickness of the outer ring"},
    # Inner blade section
    {"param_name": "innerThickness",    "min_value": 3,    "max_value": 24,   "unit": "% of chord",       "description": "Inner blade section profile thickness"},
    {"param_name": "innerMaxPos",       "min_value": 2,    "max_value": 8,    "unit": "tenths of chord",  "description": "Inner blade section chordwise position of max thickness"},
    {"param_name": "innerCamber",       "min_value": 0,    "max_value": 9,    "unit": "% of chord",       "description": "Inner blade section profile camber"},
    {"param_name": "innerChord",        "min_value": 3,    "max_value": 11,   "unit": "mm",               "description": "Inner blade section chord length"},
    {"param_name": "innerAngle",        "min_value": 2,    "max_value": 25,   "unit": "degrees",          "description": "Inner blade section angle of attack"},
    # Middle blade section
    {"param_name": "middlePos",         "min_value": 0.3,  "max_value": 0.7,  "unit": "x impellerRadius", "description": "Middle blade section radial position as multiplier of propeller radius"},
    {"param_name": "middleChord",       "min_value": 10,   "max_value": 30,   "unit": "mm",               "description": "Middle blade section chord length"},
    {"param_name": "middleAngle",       "min_value": 2,    "max_value": 25,   "unit": "degrees",          "description": "Middle blade section angle of attack"},
    # Outer blade section
    {"param_name": "outerThickness",    "min_value": 3,    "max_value": 24,   "unit": "% of chord",       "description": "Outer blade section profile thickness"},
    {"param_name": "outerMaxPos",       "min_value": 2,    "max_value": 8,    "unit": "tenths of chord",  "description": "Outer blade section chordwise position of max thickness"},
    {"param_name": "outerCamber",       "min_value": 0,    "max_value": 9,    "unit": "% of chord",       "description": "Outer blade section profile camber"},
    {"param_name": "outerChord",        "min_value": 10,   "max_value": 30,   "unit": "mm",               "description": "Outer blade section chord length"},
    {"param_name": "outerAngle",        "min_value": 2,    "max_value": 25,   "unit": "degrees",          "description": "Outer blade section angle of attack"},
]

assert len(PROPELLER_DC_PARAMETERS_V1) == 17, (
    f"Expected exactly 17 propeller parameters, got {len(PROPELLER_DC_PARAMETERS_V1)}. "
    "Cross-check against DC_prompt_fragments/dc_config/parameters.md."
)


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

    rows = PROPELLER_DC_PARAMETERS_V1
    print(f"Using connection URL from {url_source}.")
    print(f"Populating dc_parameter_schemas at {host_db}")
    print(f"  schema_version = {SCHEMA_VERSION}")
    print(f"  parameter count = {len(rows)}")
    print()

    inserted = 0
    skipped = 0
    with psycopg.connect(url, autocommit=True) as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO dc_parameter_schemas
                        (schema_version, param_name, min_value, max_value, unit, description)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (schema_version, param_name) DO NOTHING
                    """,
                    (
                        SCHEMA_VERSION,
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

    print(f"Inserted: {inserted}")
    print(f"Skipped (already present, due to ON CONFLICT DO NOTHING): {skipped}")
    print()

    # Verification: read everything back at this schema_version.
    print(f"Current rows in dc_parameter_schemas WHERE schema_version = {SCHEMA_VERSION}:")
    print()
    print(f"  {'param_name':22s} {'min':>8s}   {'max':>8s}   {'unit':<22s} description")
    print(f"  {'-'*22} {'-'*8}   {'-'*8}   {'-'*22} {'-'*40}")
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT param_name, min_value, max_value, unit, description, retired_at
                FROM dc_parameter_schemas
                WHERE schema_version = %s
                ORDER BY param_name
                """,
                (SCHEMA_VERSION,),
            )
            for name, mn, mx, unit, desc, retired in cur.fetchall():
                marker = "  (retired)" if retired is not None else ""
                desc_short = (desc or "")[:40]
                print(f"  {name:22s} {mn:>8}   {mx:>8}   {(unit or ''):22s} {desc_short}{marker}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
