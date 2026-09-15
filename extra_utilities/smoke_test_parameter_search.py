"""Smoke test for the parameter (masked-RMSE) search -- architecture T1.

    python extra_utilities/smoke_test_parameter_search.py

Covers ``tools/database_search/param_rank.py`` and the ``parameters``
branch of ``database_search``: the per-agent tool schema, the validation
layer, the ranking SQL, the emitted XML, the ACL, and the guards on
mixing a text query with a parameter vector.

Sections A, B and F need NOTHING but the repo.  C, D and E need a live
Postgres and SKIP (not fail) without one, so the file stays useful as a
fast structural check when the database is unreachable.

READ-ONLY against the database: every statement it issues is a SELECT.
``_log_rag_query`` is neutralised and its payload inspected in memory
instead -- a smoke test should not leave rows in the real ``rag_queries``
table, and a parameter query has no ``query_text`` prefix to clean up by.

Why the bootstrap
-----------------
``agents/__init__.py`` imports the whole chain, which drags in the 3D and
Rhino stack.  ``prompt_pdf/bootstrap.py`` stubs exactly those, but by
default it also stubs psycopg/tiktoken/boto3 -- which this test needs for
real.  They are removed from its stub set before installing, so the DB and
token stack are genuine and only the 3D/LLM plumbing is fake.  Nothing
under test is stubbed.

Exit codes: 0 all assertions passed, 1 anything failed.
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "extra_utilities" / "prompt_pdf"))
import bootstrap                                            # noqa: E402

# Keep the database, storage and tokeniser stacks REAL.
bootstrap.STUB_ROOTS -= {"psycopg", "psycopg_pool", "pgvector", "tiktoken",
                         "boto3", "botocore"}
bootstrap.install()

def _find_env() -> Path | None:
    """The nearest ``.env`` at or above the repo root.

    Normally that is ``<repo>/.env``.  The walk upward exists for git
    WORKTREES: one lives at ``<main>/.claude/worktrees/<name>`` and has
    no ``.env`` of its own, so without this the live sections silently
    skip on a developer machine and the test reports PASS having checked
    only a third of itself.
    """
    for base in (_REPO_ROOT, *_REPO_ROOT.parents):
        candidate = base / ".env"
        if candidate.exists():
            return candidate
    return None


_ENV = _find_env()
if _ENV is not None:
    for _line in io.open(_ENV, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(),
                                  _v.strip().strip('"').strip("'"))

from agents.shared import postgres_pool                      # noqa: E402
from tools.database_search import param_rank                 # noqa: E402
from tools.database_search.database_search import (          # noqa: E402
    AnchorHit, _database_search_impl, _emit_anchor_block, _emit_no_results,
    _emit_search_meta, _similarity_score, make_database_search_tool,
    SearchMeta)
from tools.database_search import database_search as DS      # noqa: E402

_FAILS: list[str] = []
_SKIPS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print("   %-5s %s%s" % ("OK" if ok else "FAIL", name,
                            "" if ok else "  -- " + detail))
    if not ok:
        _FAILS.append(name)


def section(title: str) -> None:
    print()
    print("=" * 74)
    print(title)
    print("=" * 74)


# The three agents the owner scoped this to.  DCIC exists in topologies 7
# and 5, DCII only in 7, the Design Engineer only in 3.
WITH_PARAMS = ("dc_input_creator", "dc_input_inspector", "design_engineer")
WITHOUT_PARAMS = ("planner", "user_input_inspector", "dc_output_inspector",
                  "receptionist", "orchestrator", "tool_caller",
                  "requirements_analyst")

# A hand-built schema so section B needs no database.  Values are the real
# declared ranges from dc_parameter_schemas v2.
FAKE_SCHEMA = {
    "bladeCount": (3.0, 6.0),
    "impellerRadius": (60.0, 80.0),
    "innerAngle": (2.0, 25.0),
    "middlePos": (0.3, 0.7),
}


# ===================================================================
section("A.  The per-agent tool schema")
# ===================================================================

def _schema(agent):
    t = make_database_search_tool(agent)
    s = t.args_schema.model_json_schema()
    return t, s, s.get("properties", {})


for _a in WITH_PARAMS:
    check(f"{_a:<22} HAS parameters", "parameters" in _schema(_a)[2])
for _a in WITHOUT_PARAMS:
    check(f"{_a:<22} does NOT", "parameters" not in _schema(_a)[2])

_t3, _s3, _p3 = _schema("dc_input_creator")
_t7, _s7, _p7 = _schema("planner")

check("the tool NAME is the same either way",
      _t3.name == _t7.name == "database_search")
check("query and n keep their names and order",
      list(_p3)[:2] == ["query", "n"], str(list(_p3)))
check("parameters is optional", "parameters" not in _s3.get("required", []))

# `from __future__ import annotations` makes every annotation a STRING,
# resolved by get_type_hints() against MODULE globals -- so a doc constant
# defined inside the factory would silently vanish from the schema.
check("the argument descriptions survived get_type_hints",
      "CLOSEST saved attempts" in _p3["parameters"].get("description", ""),
      repr(_p3["parameters"])[:160])
check("the query doc is shared by both variants",
      "Natural-language search query" in _p3["query"]["description"]
      and "Natural-language search query" in _p7["query"]["description"])
check("only the parameter variant is told they are exclusive",
      "supplying both is an error" in _p3["query"]["description"]
      and "supplying both" not in _p7["query"]["description"])

try:
    make_database_search_tool("not_an_agent")
    _bind_ok = False
except ValueError:
    _bind_ok = True
check("an unknown agent slug fails loudly at bind time", _bind_ok)

# W41: both stay pinned in BOTH variants.
_seen: list[dict] = []
_real_impl = DS._database_search_impl
DS._database_search_impl = lambda **kw: (_seen.append(kw) or "<stub/>")
try:
    make_database_search_tool("dc_input_creator").invoke(
        {"query": "", "n": 2, "parameters": {"bladeCount": 5}})
    check("parameters reach the impl",
          _seen[-1].get("parameters") == {"bladeCount": 5})
    check("caller_agent is closure-captured, not an LLM argument",
          _seen[-1]["caller_agent"] == "dc_input_creator"
          and "caller_agent" not in _p3)
    make_database_search_tool("planner").invoke({"query": "x", "n": 2})
    check("the plain variant sends no parameters kwarg",
          "parameters" not in _seen[-1])
    check("attempt_specific_flag / metafilters stay pinned (W41)",
          _seen[-1]["attempt_specific_flag"] is False
          and _seen[-1]["metafilters"] is None)
finally:
    DS._database_search_impl = _real_impl


# ===================================================================
section("B.  Validation  (pure -- no database)")
# ===================================================================
for _name, _arg, _want in (
    ("empty dict refused", {}, True),
    ("unknown key refused", {"nope": 1}, True),
    ("non-numeric refused", {"bladeCount": "five"}, True),
    ("bool refused (bool is a subclass of int)", {"bladeCount": True}, True),
    ("above-range refused", {"bladeCount": 20}, True),
    ("below-range refused", {"middlePos": 0.1}, True),
    ("in-range accepted", {"bladeCount": 5}, False),
    ("a float for an int-typed param is fine", {"bladeCount": 4.5}, False),
    ("range endpoints are inclusive", {"bladeCount": 3}, False),
):
    try:
        param_rank.validate_query(_arg, FAKE_SCHEMA)
        _raised = False
    except param_rank.ParameterQueryError:
        _raised = True
    check(_name, _raised == _want, f"raised={_raised} expected={_want}")

check("key order does not change the query",
      param_rank.validate_query({"bladeCount": 5, "middlePos": 0.5},
                                FAKE_SCHEMA)
      == param_rank.validate_query({"middlePos": 0.5, "bladeCount": 5},
                                   FAKE_SCHEMA))

# The role equivalence: chunks.agents_to names SEVEN-agent roles, so a
# topology-3 agent matching on its own name sees nothing.
check("a 7-agent agent expands to itself alone",
      param_rank.acl_identities("planner") == ["planner"])
check("the Design Engineer inherits DCIC + DCII + Tool Caller",
      param_rank.acl_identities("design_engineer")
      == ["dc_input_creator", "dc_input_inspector", "design_engineer",
          "tool_caller"])
check("the Requirements Analyst inherits UII + DCOI",
      param_rank.acl_identities("requirements_analyst")
      == ["dc_output_inspector", "requirements_analyst",
          "user_input_inspector"])


# ===================================================================
section("F.  The semantic path is untouched")
# ===================================================================
# A parameter hit and a semantic hit differ ONLY by matched_keys being
# set, and that is what the emitter branches on.  If this regresses,
# every existing agent's search output changes.
_sem = AnchorHit(session_id="ID1_x", attempt_id=None, attempt_label=None,
                 dist=0.13, best_chunk_id=7)
_par = AnchorHit(session_id="ID1_x", attempt_id=44, attempt_label="003_y",
                 dist=0.13, best_chunk_id=-1, matched_keys=2, n_queried=3)
_sem_xml = _emit_anchor_block(_sem, [], False, [])
_par_xml = _emit_anchor_block(_par, [], True, [])
check("a semantic hit still emits score=",
      'score="0.87"' in _sem_xml and "closeness=" not in _sem_xml, _sem_xml)
check("a parameter hit emits closeness= and never score=",
      'closeness="0.87"' in _par_xml and "score=" not in _par_xml, _par_xml)
check("a parameter hit carries matched_keys (D8.2)",
      'matched_keys="2/3"' in _par_xml, _par_xml)

_meta_sem = SearchMeta(n_requested=5, n_returned=1, attempt_specific=False,
                       metafilters_repr="{}", embedding_model="m/m/1",
                       skipped_due_to_model_mismatch=0)
_meta_par = SearchMeta(n_requested=5, n_returned=1, attempt_specific=True,
                       metafilters_repr="{}", embedding_model="m/m/1",
                       skipped_due_to_model_mismatch=0,
                       search_kind="parameters", parameters_repr="{'a': 1}")
check("the semantic header still reports embedding_model",
      "embedding_model=" in _emit_search_meta(_meta_sem))
check("the parameter header reports NEITHER embedding_model NOR the "
      "mismatch count -- nothing was embedded",
      "embedding_model=" not in _emit_search_meta(_meta_par)
      and "skipped_due_to_model_mismatch" not in _emit_search_meta(_meta_par),
      _emit_search_meta(_meta_par))
check("the parameter header says which kind of search ran",
      'search_kind="parameters"' in _emit_search_meta(_meta_par))
check("both locked no-results wordings survive",
      _emit_no_results(False) == "<no_results>No results found.</no_results>"
      and "relaxing them" in _emit_no_results(True))
check("the parameter search gets its own third wording",
      "parameters you supplied" in _emit_no_results(False, "parameters"))
check("closeness is just 1 - rmse, to 3 d.p.",
      _similarity_score(0.134) == 0.866)


# ===================================================================
# Live sections
# ===================================================================
_LIVE = True
try:
    if not postgres_pool.is_enabled():
        _LIVE = False
    else:
        with postgres_pool.connection() as _c:
            with _c.cursor() as _cur:
                _cur.execute("SELECT 1")
except Exception as _exc:                                    # noqa: BLE001
    _LIVE = False
    print(f"\n(no live database: {type(_exc).__name__}: {_exc})")

if not _LIVE:
    _SKIPS.append("C/D/E (live Postgres)")
    section("C/D/E.  SKIPPED -- no live Postgres")
else:
    # ===============================================================
    section("C.  Ranking against the live corpus")
    # ===============================================================
    with postgres_pool.connection() as conn:
        schema = param_rank.active_schema(conn)
        check("the active schema is one row per parameter, not two "
              "(W46: retired_at IS NULL alone matches v1 AND v2)",
              len(schema) == 16, f"{len(schema)} keys")
        check("impellerHeight is not searchable (F46c / W46)",
              "impellerHeight" not in schema)

        with conn.cursor() as cur:
            cur.execute("SELECT attempt_id FROM dc_attempts "
                        "ORDER BY attempt_id LIMIT 1")
            row = cur.fetchone()
        if row is None:
            _SKIPS.append("C ranking (no attempts saved)")
            print("   (no attempts saved -- ranking checks skipped)")
        else:
            probe = row[0]
            with conn.cursor() as cur:
                cur.execute("SELECT param_name, raw_value FROM "
                            "dc_attempt_parameters WHERE attempt_id=%s",
                            (probe,))
                full = {k: float(v) for k, v in cur.fetchall()}
            hits = param_rank.rank_attempts(
                conn, caller_agent="dc_input_creator",
                params=param_rank.validate_query(full, schema), n=3)
            check("an attempt's own vector finds it first",
                  hits and hits[0].attempt_id == probe)
            check("a self-match scores exactly 1.000",
                  hits[0].closeness == 1.0, str(hits[0].closeness))
            check("matched_keys is not doubled (W46)",
                  hits[0].matched_keys == len(full),
                  f"{hits[0].matched_keys}/{len(full)}")

            sub = param_rank.validate_query({"bladeCount": 5}, schema)
            r1 = param_rank.rank_attempts(
                conn, caller_agent="dc_input_creator", params=sub, n=5)
            r2 = param_rank.rank_attempts(
                conn, caller_agent="dc_input_creator", params=sub, n=5)
            check("the same query gives the same order",
                  [h.attempt_id for h in r1] == [h.attempt_id for h in r2])
            check("n counts distinct ATTEMPTS",
                  len({h.attempt_id for h in r1}) == len(r1))
            check("results are ordered closest-first",
                  [h.rmse for h in r1] == sorted(h.rmse for h in r1))

            # The ACL is the whole reason a ranking is safe to expose.
            reach = {who: len(param_rank.rank_attempts(
                conn, caller_agent=who, params=sub, n=500))
                for who in ("dc_input_creator", "design_engineer",
                            "receptionist")}
            print(f"   reachable attempts: {reach}")
            check("the DC Input Creator reaches attempts",
                  reach["dc_input_creator"] > 0)
            check("the Design Engineer reaches them too, via the role "
                  "equivalence", reach["design_engineer"] > 0)
            check("an agent with no attempt-level grant reaches NONE -- "
                  "the ACL is load-bearing",
                  reach["receptionist"] == 0, str(reach["receptionist"]))

    # ===============================================================
    section("D.  End-to-end XML")
    # ===============================================================
    _logged: list[dict] = []
    _calls: list[int] = []
    _real_log = DS._log_rag_query
    DS._log_rag_query = lambda **kw: _logged.append(kw)

    def _impl(**kw):
        """Call the impl with this test's fixed arguments, and COUNT it.

        Counting rather than hard-coding a total is the point: invariant
        11 says every call is logged, and an assertion written as
        ``len(_logged) == 6`` stops testing that the moment someone adds
        a case -- it just starts failing for the wrong reason.
        """
        _calls.append(1)
        kw.setdefault("caller_agent", "dc_input_creator")
        kw.setdefault("query", "")
        kw.setdefault("n", 3)
        kw.setdefault("attempt_specific_flag", False)
        kw.setdefault("metafilters", None)
        return _database_search_impl(**kw)

    try:
        # BOTH backends, deliberately.  W47 is the trap where the
        # expansion's embedding_model must follow the TABLE rather than
        # settings, and the two tables carry different model strings --
        # so a test that exercises only one of them cannot see the bug.
        # `chunks_mm` is the live default, which is precisely why it must
        # not be the one left untested.
        from workflow_settings import db_options_config as _dbo
        for _mode in (_dbo.MODE_TEXT_ONLY, _dbo.MODE_SINGLE_VECTOR):
            xml = _impl(db_mode=_mode,
                        parameters={"bladeCount": 5,
                                    "impellerRadius": 70.0})
            if _mode == _dbo.MODE_TEXT_ONLY:
                print(xml[:600])
            check(f"[{_mode}] the header says it was a parameter search",
                  'search_kind="parameters"' in xml)
            check(f"[{_mode}] the query vector is echoed back",
                  "bladeCount" in xml)
            if "<no_results>" in xml:
                continue
            check(f"[{_mode}] hits carry closeness and matched_keys",
                  "closeness=" in xml and "matched_keys=" in xml)
            check(f"[{_mode}] anchors are attempts", "<attempt " in xml)
            check(f"[{_mode}] no <qa> is falsely marked best_match -- "
                  f"the match was on numbers, not text",
                  'best_match="true"' not in xml)
            check(f"[{_mode}] Q+A text actually came back (W47: a "
                  f"backend/model mismatch looks exactly like an empty "
                  f"result)", "<answer>" in xml, xml[:400])
            check(f"[{_mode}] available_attempts is advertised",
                  "<available_attempts" in xml)

        # =========================================================
        section("E.  Mixing the two inputs, and the error categories")
        # =========================================================
        both = _impl(query="thin rings", parameters={"bladeCount": 5})
        check("supplying BOTH is refused", 'error="both_inputs"' in both,
              both[:200])
        check("...and says what to do instead", "twice" in both)
        check("...and nothing was searched", "<session" not in both)

        blank = _impl(query="   ", parameters={"bladeCount": 5})
        check("a whitespace-only query is not 'both'",
              'search_kind="parameters"' in blank, blank[:200])

        bad = _impl(parameters={"bladeCount": 99})
        check("an out-of-range value is its own error category",
              'error="invalid_parameters"' in bad, bad[:200])
        check("...and names the legal range", "3..6" in bad, bad[:200])

        unknown = _impl(parameters={"numBlades": 5})
        check("an unknown key is refused with the real vocabulary",
              'error="invalid_parameters"' in unknown
              and "bladeCount" in unknown)

        check("EVERY call was logged, error paths included "
              "(invariant 11)",
              len(_logged) == len(_calls),
              f"{len(_logged)} rows for {len(_calls)} calls")
        check("the parameter vector reaches rag_queries.query_params -- "
              "the column exists for this, no migration needed",
              _logged[-1].get("query_params") == {"numBlades": 5},
              str(_logged[-1].get("query_params")))
    finally:
        DS._log_rag_query = _real_log
    postgres_pool.close_pool()


print()
print("=" * 74)
if _SKIPS:
    print("SKIPPED:", "; ".join(_SKIPS))
if _FAILS:
    print("FAILURES:", _FAILS)
    sys.exit(1)
print("PARAMETER SEARCH: PASS")
sys.exit(0)
