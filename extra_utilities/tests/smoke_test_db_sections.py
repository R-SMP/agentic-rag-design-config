"""One database, one section per configurator (``engine/db_sections.py``),
offline: a stand-in database that knows the schemas and tables the code
asks about, never a real one.  Five groups:

1. NAMES -- a configurator's section is its folder's name, lower case,
   other characters as ``_``, not starting with a digit, at most 63
   characters; ``public``, ``information_schema`` and ``pg_*`` are refused.
   The schema file makes pgvector and the session counter in ``public``
   and every table unqualified, in the section.
2. MAKE AND MOVE -- making a section runs CREATE SCHEMA, the search_path
   and the schema file, and is refused when the section holds any table;
   moving a database made before sections moves the seven tables from
   ``public``, parents first, and is refused unless ``public`` holds all
   seven and the section none; making a section on such a database is
   refused (an empty section would hide its tables) and names the move.
3. THE POOL -- a configurator whose section is missing has no database
   (``is_enabled`` False, the reason names the section and the Database
   view), asked again after the re-check time; made, it has one; each
   section has its own pool, whose connections get ``search_path`` = the
   section, public, and go back idle; loading another configurator gives
   its own pool; an unreachable database is reported by the callers as
   before (``is_enabled`` True); no URL, or no ``database: true``, have
   their own reasons; ``close_pool`` closes every pool.
4. THE APP -- ``GET /api/db_section`` says the section and its state;
   ``POST /api/db_admin/create_section`` wants the Database view's
   password and makes the section once; ``/api/parameter_schema`` says
   why there is no database; the reset wipes, and names, the loaded
   configurator's section only.
5. THE SCRIPTS -- ``apply_schema.py`` runs in a section (``--section``,
   ``--shared``), ``populate_dc_parameter_schemas.py`` refuses a missing
   section, ``move_tables_to_section.py`` refuses and moves as group 2.

Run from the repo root:
    py -3.13 extra_utilities/tests/smoke_test_db_sections.py
"""
from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")

import config                               # noqa: E402
from engine import db_sections as D         # noqa: E402

FAILURES: list[str] = []


def check(ok: bool, msg: str) -> None:
    if not ok:
        FAILURES.append(msg)


# --------------------------------------------------------------------------
# the stand-in database
# --------------------------------------------------------------------------

class FakeDB:
    """Schemas and the tables in them, and every statement sent."""

    def __init__(self, schemas: "dict[str, set[str]] | None" = None):
        self.schemas = {"public": set()}
        self.schemas.update(schemas or {})
        self.log: list[tuple[str, str]] = []          # (search_path's first schema, statement)
        self.reachable = True


class FakeCursor:
    def __init__(self, conn):
        self.conn, self.rows = conn, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, q, params=None):
        db, text = self.conn.db, q if isinstance(q, str) else q.as_string(None)
        db.log.append((self.conn.path, text))
        self.rows = []
        idents = re.findall(r'"([^"]+)"', text)
        if "information_schema.tables" in text:
            self.rows = [(t,) for t in sorted(db.schemas.get(params[0], set()))]
        elif text.startswith("CREATE SCHEMA"):
            db.schemas.setdefault(idents[0], set())
        elif text.startswith("SET search_path"):
            self.conn.path = idents[0]
        elif text == D.SCHEMA_SQL.read_text(encoding="utf-8"):
            db.schemas.setdefault(self.conn.path, set()).update(D.TABLES)
        elif text.startswith("ALTER TABLE"):
            src, table, dst = idents
            db.schemas[src].discard(table)
            db.schemas.setdefault(dst, set()).add(table)
        elif text.upper().startswith("SELECT COUNT(*)"):
            self.rows = [(0,)]

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConn:
    def __init__(self, db: FakeDB):
        self.db, self.path, self.commits = db, "public", 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return FakeCursor(self)

    def execute(self, q, params=None):
        c = FakeCursor(self)
        c.execute(q, params)
        return c

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


# --------------------------------------------------------------------------
# 1. names
# --------------------------------------------------------------------------

def check_names() -> None:
    for folder, want in (("propeller", "propeller"), ("vacuum_hose_adapter", "vacuum_hose_adapter"),
                         ("My Setup-2", "my_setup_2"), ("3d_printer", "s_3d_printer"), ("x" * 70, "x" * 63)):
        got = D.section_of(Path("setups") / folder)
        check(got == want, f"[NAMES] {folder!r} -> {got!r}, want {want!r}")
    for bad in ("public", "Public", "information_schema", "pg_catalog", "pg_x"):
        try:
            D.section_of(bad)
            check(False, f"[NAMES] {bad!r} was taken as a section")
        except D.SectionError:
            pass
    check(D.search_path("propeller").as_string(None) == 'SET search_path TO "propeller", "public"',
          f"[NAMES] search_path: {D.search_path('propeller').as_string(None)}")
    sql = D.SCHEMA_SQL.read_text(encoding="utf-8")
    statements = [ln for ln in sql.splitlines() if re.match(r"\s*CREATE ", ln)]
    check("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;" in statements
          and any(ln.startswith("CREATE SEQUENCE IF NOT EXISTS public.session_counter") for ln in statements),
          "[NAMES] the schema file does not make pgvector and the session counter in public")
    tables = re.findall(r"^CREATE TABLE (\S+) \(", sql, re.M)
    check(sorted(tables) == sorted(D.TABLES),
          f"[NAMES] the schema file's tables {tables} are not the layout's, unqualified")


# --------------------------------------------------------------------------
# 2. make and move
# --------------------------------------------------------------------------

def check_make_move() -> None:
    db = FakeDB()
    conn = FakeConn(db)
    made = D.create(conn, "propeller")
    sent = [t for _p, t in db.log if not t.startswith("SELECT")]
    check(made == list(D.TABLES) and sent[:2] == ['CREATE SCHEMA IF NOT EXISTS "propeller"',
                                                 'SET search_path TO "propeller", "public"']
          and len(sent) == 3 and conn.path == "propeller" and D.ready(conn, "propeller"),
          f"[MAKE] made {made}, sent {[s[:60] for s in sent]}")
    check(conn.commits == 0, "[MAKE] create committed: the caller's block does")
    try:
        D.create(conn, "propeller")
        check(False, "[MAKE] a section made twice")
    except D.SectionError as exc:
        check("already has a section 'propeller'" in str(exc), f"[MAKE] twice: {exc}")
    db.schemas["half"] = {"sessions"}
    try:
        D.create(conn, "half")
        check(False, "[MAKE] a section holding one table made again")
    except D.SectionError:
        pass
    check(not D.ready(conn, "half") and not D.ready(conn, "nowhere"), "[MAKE] a part or no section read as ready")
    before = FakeDB({"public": set(D.TABLES)})
    try:
        D.create(FakeConn(before), "propeller")
        check(False, "[MAKE] a section made on a database whose tables are in public")
    except D.SectionError as exc:
        check("move_tables_to_section.py propeller" in str(exc) and "propeller" not in before.schemas,
              f"[MAKE] on a database made before sections: {exc}")

    # a database made before sections
    old = FakeDB({"public": set(D.TABLES)})
    conn = FakeConn(old)
    moved = D.move_shared_into(conn, "propeller")
    alters = [t for _p, t in old.log if t.startswith("ALTER TABLE")]
    check(moved == list(D.TABLES) and old.schemas["public"] == set() and old.schemas["propeller"] == set(D.TABLES)
          and alters == [f'ALTER TABLE "public"."{t}" SET SCHEMA "propeller"' for t in D.TABLES],
          f"[MOVE] {alters}")
    for schemas, why in (({"public": set(D.TABLES), "propeller": {"sessions"}}, "already holds"),
                         ({"public": set(D.TABLES) - {"chunks_mm"}}, "missing ['chunks_mm']")):
        db = FakeDB(schemas)
        try:
            D.move_shared_into(FakeConn(db), "propeller")
            check(False, f"[MOVE] moved with {schemas}")
        except D.SectionError as exc:
            check(why in str(exc) and not any(t.startswith("ALTER") for _p, t in db.log),
                  f"[MOVE] refused with {exc}")


# --------------------------------------------------------------------------
# 3. the pool
# --------------------------------------------------------------------------

class StubPool:
    opened: list = []

    def __init__(self, conninfo, configure, **kw):
        self.conninfo, self.configure, self.kw, self.closed = conninfo, configure, kw, False
        self.conns = []
        StubPool.opened.append(self)

    def open(self, wait=True, timeout=None):
        pass

    @contextlib.contextmanager
    def connection(self):
        conn = FakeConn(DB)
        self.configure(conn)
        self.conns.append(conn)
        yield conn

    def close(self):
        self.closed = True

    check_connection = staticmethod(lambda conn: None)


DB = FakeDB()


@contextlib.contextmanager
def stand_ins(url="postgresql://u:secret@db.example:5432/railway"):
    """The pool's database, connections and pgvector, stood in for."""
    import psycopg
    from agents.shared import postgres_pool as PP
    saved = (config.DATABASE_PUBLIC_URL, config.DATABASE_URL, psycopg.connect, PP.ConnectionPool,
             PP.register_vector, config.DC_PACK_DIR)
    vectors = []

    def connect(u, **kw):
        if not DB.reachable:
            raise OSError("could not connect")
        return FakeConn(DB)

    config.DATABASE_PUBLIC_URL, config.DATABASE_URL = url, ""
    psycopg.connect, PP.ConnectionPool = connect, StubPool
    PP.register_vector = vectors.append
    PP.close_pool()
    try:
        yield PP, vectors
    finally:
        PP.close_pool()
        (config.DATABASE_PUBLIC_URL, config.DATABASE_URL, psycopg.connect, PP.ConnectionPool,
         PP.register_vector, config.DC_PACK_DIR) = saved


def _setup(tmp: Path, name: str, database: bool = True) -> Path:
    d = tmp / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "pack.yaml").write_text("pack_format: 1\n" + ("database: true\n" if database else ""), encoding="utf-8")
    return d


def check_pool() -> None:
    global DB
    tmp = Path(tempfile.mkdtemp(prefix="db_sections_"))
    try:
        prop, hose, nodb = _setup(tmp, "propeller"), _setup(tmp, "vacuum_hose_adapter"), _setup(tmp, "plain", False)
        DB = FakeDB()
        StubPool.opened = []
        with stand_ins() as (PP, vectors):
            config.DC_PACK_DIR = prop
            check(PP.section() == "propeller", f"[POOL] section {PP.section()}")
            check(PP.is_enabled() is False and PP.get_pool() is None,
                  "[POOL] a configurator with no section has the database")
            reason = PP.disabled_reason()
            check("no section for this configurator (propeller)" in reason and "Database view" in reason
                  and "secret" not in reason, f"[POOL] the reason: {reason}")
            try:
                with PP.connection():
                    pass
                check(False, "[POOL] a connection without a section")
            except PP.PostgresDisabledError as exc:
                check("propeller" in str(exc), f"[POOL] connection() says: {exc}")
            # made elsewhere: seen after the re-check time, not before
            D.create(FakeConn(DB), "propeller")
            check(PP.is_enabled() is False, "[POOL] a missing section asked again at once")
            saved_ttl = PP._MISSING_RECHECK_SEC
            PP._MISSING_RECHECK_SEC = 0.0
            try:
                check(PP.is_enabled() is True and PP.disabled_reason() == "",
                      "[POOL] a section made meanwhile is not seen after the re-check time")
            finally:
                PP._MISSING_RECHECK_SEC = saved_ttl
            pool = PP.get_pool()
            with PP.connection() as conn:
                pass
            check(isinstance(pool, StubPool) and pool.conninfo.endswith("db.example:5432/railway")
                  and conn.path == "propeller" and conn.commits == 1 and len(vectors) == 1
                  and ("public", 'SET search_path TO "propeller", "public"') in DB.log,
                  f"[POOL] the propeller's connection: path {conn.path}, commits {conn.commits}, "
                  f"vector {len(vectors)}")
            check(PP.get_pool() is pool, "[POOL] a second pool for the same section")
            # another configurator: its own section, its own pool
            config.DC_PACK_DIR = hose
            check(PP.is_enabled() is False and "vacuum_hose_adapter" in PP.disabled_reason(),
                  "[POOL] the hose adapter took the propeller's section")
            made = PP.create_section()
            check(made == {"section": "vacuum_hose_adapter", "tables": list(D.TABLES)} and PP.is_enabled(),
                  f"[POOL] create_section: {made}")
            try:
                PP.create_section()
                check(False, "[POOL] create_section made a section twice")
            except D.SectionError:
                pass
            hose_pool = PP.get_pool()
            with PP.connection() as conn2:
                pass
            check(hose_pool is not pool and conn2.path == "vacuum_hose_adapter" and len(StubPool.opened) == 2,
                  f"[POOL] the hose adapter's pool: path {conn2.path}, pools {len(StubPool.opened)}")
            config.DC_PACK_DIR = prop
            check(PP.get_pool() is pool, "[POOL] back to the propeller, not its pool")
            # no database: true; then an unreachable database
            config.DC_PACK_DIR = nodb
            check(not PP.is_enabled() and "does not use the database" in PP.disabled_reason(),
                  f"[POOL] no database: true: {PP.disabled_reason()}")
            config.DC_PACK_DIR = _setup(tmp, "turbine")
            DB.reachable = False
            check(PP.section_ready() is None and PP.is_enabled() is True,
                  "[POOL] an unreachable database turns the database off instead of reporting it")
            DB.reachable = True
            # a database made before sections: the reason says move, not make
            DB.schemas["public"] = set(D.TABLES)
            config.DC_PACK_DIR = _setup(tmp, "older")
            reason = PP.disabled_reason()
            check(not PP.is_enabled() and "move_tables_to_section.py older" in reason
                  and "Database view" not in reason, f"[POOL] tables in public: {reason}")
            DB.schemas["public"] = set()
            PP.close_pool()
            check(all(p.closed for p in StubPool.opened) and not PP._pools,
                  "[POOL] close_pool left a pool open")
        with stand_ins(url="") as (PP, _v):
            config.DC_PACK_DIR = prop
            check(not PP.is_enabled() and PP.disabled_reason().startswith("No database is configured"),
                  f"[POOL] no URL: {PP.disabled_reason()}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 4. the app
# --------------------------------------------------------------------------

def check_app() -> None:
    global DB
    from fastapi.testclient import TestClient
    import web_app
    DB = FakeDB()
    StubPool.opened = []
    saved_pw = os.environ.get(web_app.DB_PASSWORD_ENV)
    os.environ[web_app.DB_PASSWORD_ENV] = "pw-for-the-test"
    try:
        with stand_ins() as (PP, _v):
            config.DC_PACK_DIR = ROOT / "setups" / "propeller"
            client = TestClient(web_app.app)
            d = client.get("/api/db_section").json()
            check(d == {"section": "propeller", "ready": False, "reason": PP.disabled_reason(), "move": False}
                  and "no section" in d["reason"], f"[APP] db_section, missing: {d}")
            DB.schemas["public"] = set(D.TABLES)
            d = client.get("/api/db_section").json()
            check(d["move"] is True and "move_tables_to_section.py propeller" in d["reason"],
                  f"[APP] db_section, tables in public: {d}")
            DB.schemas["public"] = set()
            d = client.get("/api/parameter_schema").json()
            check(d.get("database") is False and "no section for this configurator (propeller)" in d.get("message", ""),
                  f"[APP] parameter_schema without a section: {d.get('message')}")
            r = client.post("/api/parameter_schema/upload")
            check(r.status_code == 503 and "propeller" in r.json().get("detail", ""),
                  f"[APP] upload without a section: {r.status_code} {r.text[:200]}")
            d = client.post("/api/db_admin/reset", json={"password": "pw-for-the-test",
                                                         "phrase": web_app.RESET_PHRASE}).json()
            check(d.get("ok") is False and "propeller" in d.get("error", ""), f"[APP] reset without a section: {d}")
            d = client.post("/api/db_admin/create_section", json={"password": "wrong"}).json()
            check(d == {"ok": False, "error": "Password rejected."} and "propeller" not in DB.schemas,
                  f"[APP] create with a wrong password: {d}")
            d = client.post("/api/db_admin/create_section", json={"password": "pw-for-the-test"}).json()
            check(d.get("ok") is True and d.get("section") == "propeller" and DB.schemas.get("propeller") == set(D.TABLES),
                  f"[APP] create: {d}")
            d = client.post("/api/db_admin/create_section", json={"password": "pw-for-the-test"}).json()
            check(d.get("ok") is False and "already has a section" in d.get("error", ""), f"[APP] create twice: {d}")
            d = client.get("/api/db_section").json()
            check(d == {"section": "propeller", "ready": True, "reason": "", "move": False},
                  f"[APP] db_section, made: {d}")
            DB.log.clear()
            d = client.post("/api/db_admin/reset", json={"password": "pw-for-the-test",
                                                         "phrase": web_app.RESET_PHRASE}).json()
            wiped = [p for p, t in DB.log if t.startswith("TRUNCATE")]
            check(d.get("ok") is True and d.get("section") == "propeller" and wiped == ["propeller"],
                  f"[APP] reset: {d}, TRUNCATE in {wiped}")
    finally:
        if saved_pw is None:
            os.environ.pop(web_app.DB_PASSWORD_ENV, None)
        else:
            os.environ[web_app.DB_PASSWORD_ENV] = saved_pw


# --------------------------------------------------------------------------
# 5. the scripts (a database they cannot reach: their arguments and refusals)
# --------------------------------------------------------------------------

def _run(args: list[str], env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=str(ROOT), env=env, capture_output=True,
                          text=True, encoding="utf-8", timeout=120)


def check_scripts() -> None:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", DATABASE_URL="", DATABASE_PUBLIC_URL="")
    env.pop("DC_PACK_DIR", None)
    dd = "extra_utilities/db_design/"
    r = _run([dd + "apply_schema.py", "--help"], env)
    check(r.returncode == 0 and "--section" in r.stdout and "--shared" in r.stdout,
          f"[SCRIPTS] apply_schema --help: {r.stdout[-300:]} {r.stderr[-300:]}")
    r = _run([dd + "apply_schema.py", dd + "database_PostgreSQL_schema_v10.sql"], env)
    check(r.returncode == 2 and "Neither DATABASE_PUBLIC_URL nor DATABASE_URL" in r.stderr,
          f"[SCRIPTS] apply_schema with no database: {r.returncode} {r.stderr[-300:]}")
    r = _run([dd + "move_tables_to_section.py", "--help"], env)
    check(r.returncode == 0 and "--dry-run" in r.stdout, f"[SCRIPTS] move --help: {r.stderr[-300:]}")
    r = _run([dd + "move_tables_to_section.py", "propeller"], env)
    check(r.returncode == 2 and "DATABASE" in r.stderr, f"[SCRIPTS] move with no database: {r.stderr[-300:]}")
    src = (ROOT / dd / "populate_dc_parameter_schemas.py").read_text(encoding="utf-8")
    check("db_sections.ready(conn, section)" in src and "conn.commit()" in src.split("db_sections.search_path(section)")[1][:80],
          "[SCRIPTS] populate_dc_parameter_schemas does not refuse a missing section, or loses the search_path "
          "to its dry run's rollback")


def main() -> int:
    for fn in (check_names, check_make_move, check_pool, check_app, check_scripts):
        try:
            fn()
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(False, f"[{fn.__name__}] crashed: {type(exc).__name__}: {exc}")
    print("names, make and move, the pool, the app, the scripts")
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - each configurator reads and writes its own section of the database, named after its "
          "folder, with one session counter for all; a missing section means no database until it is made "
          "(the Database view, apply_schema.py), and a database made before sections is moved whole "
          "(move_tables_to_section.py).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
