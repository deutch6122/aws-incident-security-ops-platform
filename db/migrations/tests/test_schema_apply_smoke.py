"""Task 6.3 schema-apply smoke test (local PostgreSQL container only).

This test applies the *forward* migration ``0001_init_schema.sql`` to a real,
throwaway **local** PostgreSQL container (via ``testcontainers``) and then
verifies against a live catalog that:

  - all 7 Product_A tables exist (Req 8.1);
  - the idempotent-ingest keys ``external_id`` on incidents / findings /
    alarm_events are UNIQUE and NOT NULL;
  - ``monthly_summaries.period`` is UNIQUE and NOT NULL;
  - the child FKs (incident_comments -> incidents, finding_triage -> findings)
    are declared ``ON DELETE CASCADE``;
  - (optional) applying the *down* migration drops all 7 tables again.

Scope / safety notes
--------------------
* AWS is **never** touched. No AWS CLI, no credentials, no Secrets Manager, no
  Aurora, no boto/moto. The only external dependency is a **local** PostgreSQL
  container that testcontainers starts and tears down.
* Credentials here are testcontainers' own local-only defaults (``test`` /
  ``test``). No real secret value is embedded. These never leave the local
  Docker network and are not AWS/Secrets Manager values.
* The PostgreSQL image is pinned to ``postgres:16-alpine`` to stay consistent
  with the Aurora PostgreSQL 16-series engine used by the aurora module.

Skip behaviour (why this file does not fail on the current environment)
----------------------------------------------------------------------
This test is designed to *skip* — not fail — when it cannot run:

  1. If ``testcontainers`` or ``psycopg`` are not importable, ``pytest.importorskip``
     skips the module (dependencies are intentionally not installed here).
  2. If the Docker daemon is unavailable / not running, starting the container
     raises, and we ``pytest.skip("Docker daemon unavailable")``.

So on a machine with Docker stopped and the smoke deps not installed, this test
skips cleanly while the static ``test_schema_sql.py`` suite still runs.

To actually run it, see ``db/migrations/tests/README.md``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# --- Dependency gating -------------------------------------------------------
# Skip the whole module if the smoke-test deps are not installed. These are NOT
# installed as part of Task 6.3; install via requirements-smoke.txt to run.
psycopg = pytest.importorskip(
    "psycopg", reason="psycopg not installed (see requirements-smoke.txt)"
)
postgres_module = pytest.importorskip(
    "testcontainers.postgres",
    reason="testcontainers[postgres] not installed (see requirements-smoke.txt)",
)
PostgresContainer = postgres_module.PostgresContainer

# Pinned to align with Aurora PostgreSQL 16-series (aurora module engine).
POSTGRES_IMAGE = "postgres:16-alpine"

MIGRATIONS_DIR = Path(__file__).resolve().parents[1]
UP_SQL_PATH = MIGRATIONS_DIR / "0001_init_schema.sql"
DOWN_SQL_PATH = MIGRATIONS_DIR / "0001_init_schema.down.sql"

EXPECTED_TABLES = [
    "incidents",
    "incident_comments",
    "findings",
    "finding_triage",
    "alarm_events",
    "monthly_summaries",
    "audit_logs",
]

# Ingest tables whose external_id must be UNIQUE + NOT NULL (idempotent ingest).
EXTERNAL_ID_TABLES = ["incidents", "findings", "alarm_events"]


def _connection_kwargs(container: "PostgresContainer") -> dict:
    """Build psycopg connection kwargs from the local container.

    Values come entirely from testcontainers' local defaults; no AWS/Secrets
    Manager value is used. Falls back gracefully across testcontainers versions.
    """
    host = container.get_container_host_ip()
    port = int(container.get_exposed_port(5432))
    # testcontainers exposes these via attributes across supported versions.
    user = getattr(container, "username", None) or getattr(container, "POSTGRES_USER", "test")
    password = getattr(container, "password", None) or getattr(
        container, "POSTGRES_PASSWORD", "test"
    )
    dbname = getattr(container, "dbname", None) or getattr(container, "POSTGRES_DB", "test")
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "dbname": dbname,
    }


@pytest.fixture(scope="module")
def pg_connection():
    """Start a throwaway local PostgreSQL container and yield a psycopg conn.

    Skips (does not fail) when the Docker daemon is unavailable, so the current
    Docker-less environment stays green.
    """
    try:
        container = PostgresContainer(POSTGRES_IMAGE)
        container.start()
    except Exception as exc:  # noqa: BLE001 - any startup failure => skip, not fail
        pytest.skip(f"Docker daemon unavailable: {exc}")

    conn = None
    try:
        conn = psycopg.connect(**_connection_kwargs(container))
        conn.autocommit = True
        yield conn
    finally:
        if conn is not None:
            conn.close()
        try:
            container.stop()
        except Exception:  # noqa: BLE001 - best-effort teardown
            pass


@pytest.fixture(scope="module")
def applied_schema(pg_connection):
    """Apply the forward migration once for the module."""
    up_sql = UP_SQL_PATH.read_text(encoding="utf-8")
    with pg_connection.cursor() as cur:
        cur.execute(up_sql)
    return pg_connection


def _existing_tables(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
        )
        return {row[0] for row in cur.fetchall()}


def test_all_seven_tables_exist(applied_schema) -> None:
    """Req 8.1: the 7 Product_A tables are present after applying the migration."""
    tables = _existing_tables(applied_schema)
    for table in EXPECTED_TABLES:
        assert table in tables, f"expected table {table!r} to exist after migration"


@pytest.mark.parametrize("table", EXTERNAL_ID_TABLES)
def test_external_id_is_not_null(applied_schema, table: str) -> None:
    """external_id must be NOT NULL on the idempotent-ingest tables."""
    with applied_schema.cursor() as cur:
        cur.execute(
            """
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = 'external_id'
            """,
            (table,),
        )
        row = cur.fetchone()
    assert row is not None, f"{table}.external_id column must exist"
    assert row[0] == "NO", f"{table}.external_id must be NOT NULL"


@pytest.mark.parametrize("table", EXTERNAL_ID_TABLES)
def test_external_id_is_unique(applied_schema, table: str) -> None:
    """external_id must be covered by a UNIQUE (or PK) constraint.

    Verified against pg_constraint / pg_attribute so we assert the *live*
    catalog, not the DDL text.
    """
    with applied_schema.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class t   ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY (c.conkey)
            WHERE n.nspname = 'public'
              AND t.relname = %s
              AND c.contype IN ('u', 'p')          -- unique or primary key
              AND a.attname = 'external_id'
              AND array_length(c.conkey, 1) = 1     -- single-column constraint
            LIMIT 1
            """,
            (table,),
        )
        assert cur.fetchone() is not None, (
            f"{table}.external_id must be covered by a single-column UNIQUE constraint"
        )


def test_monthly_summaries_period_unique_not_null(applied_schema) -> None:
    """monthly_summaries.period must be UNIQUE NOT NULL."""
    with applied_schema.cursor() as cur:
        cur.execute(
            """
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'monthly_summaries'
              AND column_name = 'period'
            """
        )
        row = cur.fetchone()
        assert row is not None, "monthly_summaries.period column must exist"
        assert row[0] == "NO", "monthly_summaries.period must be NOT NULL"

        cur.execute(
            """
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class t   ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY (c.conkey)
            WHERE n.nspname = 'public'
              AND t.relname = 'monthly_summaries'
              AND c.contype IN ('u', 'p')
              AND a.attname = 'period'
              AND array_length(c.conkey, 1) = 1
            LIMIT 1
            """
        )
        assert cur.fetchone() is not None, (
            "monthly_summaries.period must be covered by a single-column UNIQUE constraint"
        )


@pytest.mark.parametrize(
    ("child_table", "fk_column", "parent_table"),
    [
        ("incident_comments", "incident_id", "incidents"),
        ("finding_triage", "finding_id", "findings"),
    ],
)
def test_child_fk_on_delete_cascade(
    applied_schema, child_table: str, fk_column: str, parent_table: str
) -> None:
    """Child FKs must reference the parent PK with ON DELETE CASCADE.

    ``confdeltype = 'c'`` in pg_constraint means ON DELETE CASCADE.
    """
    with applied_schema.cursor() as cur:
        cur.execute(
            """
            SELECT c.confdeltype, cf.relname AS referenced_table
            FROM pg_constraint c
            JOIN pg_class t   ON t.oid = c.conrelid
            JOIN pg_class cf  ON cf.oid = c.confrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY (c.conkey)
            WHERE n.nspname = 'public'
              AND t.relname = %s
              AND c.contype = 'f'          -- foreign key
              AND a.attname = %s
            LIMIT 1
            """,
            (child_table, fk_column),
        )
        row = cur.fetchone()
    assert row is not None, f"{child_table}.{fk_column} must have a FK constraint"
    confdeltype, referenced_table = row
    assert referenced_table == parent_table, (
        f"{child_table}.{fk_column} must reference {parent_table}, got {referenced_table}"
    )
    assert confdeltype == "c", (
        f"{child_table}.{fk_column} FK must be ON DELETE CASCADE (confdeltype='c'), "
        f"got {confdeltype!r}"
    )


def test_down_migration_drops_all_tables(applied_schema) -> None:
    """Optional: applying the down migration removes all 7 tables.

    Runs last (module-scoped schema is already applied). After this the module
    connection has an empty public schema; no further table assertions follow.
    """
    down_sql = DOWN_SQL_PATH.read_text(encoding="utf-8")
    with applied_schema.cursor() as cur:
        cur.execute(down_sql)

    remaining = _existing_tables(applied_schema)
    for table in EXPECTED_TABLES:
        assert table not in remaining, (
            f"table {table!r} should be dropped by the down migration"
        )
