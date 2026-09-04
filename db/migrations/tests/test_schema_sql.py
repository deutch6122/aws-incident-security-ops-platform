"""Static Task 6.2 DB schema tests; no DB connection and no AWS access.

Verifies the init migration DDL by inspecting the SQL as text/regex:
  - all 7 tables are created,
  - the required UNIQUE / FK ON DELETE CASCADE constraints exist,
  - audit_logs carries before/after and entity columns,
  - no credentials/secrets/role-with-password appear in the DDL.
"""

from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[1]
UP_SQL = (MIGRATIONS_DIR / "0001_init_schema.sql").read_text(encoding="utf-8")
DOWN_SQL = (MIGRATIONS_DIR / "0001_init_schema.down.sql").read_text(encoding="utf-8")

EXPECTED_TABLES = [
    "incidents",
    "incident_comments",
    "findings",
    "finding_triage",
    "alarm_events",
    "monthly_summaries",
    "audit_logs",
]


def _create_table_pattern(table: str) -> re.Pattern[str]:
    return re.compile(
        r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?" + re.escape(table) + r"\s*\(",
        re.IGNORECASE,
    )


def test_all_seven_tables_are_created() -> None:
    for table in EXPECTED_TABLES:
        assert _create_table_pattern(table).search(UP_SQL), f"missing CREATE TABLE {table}"


def test_exactly_seven_create_table_statements() -> None:
    creates = re.findall(r"CREATE\s+TABLE\b", UP_SQL, flags=re.IGNORECASE)
    assert len(creates) == 7, f"expected 7 CREATE TABLE statements, found {len(creates)}"


def test_external_id_unique_on_ingest_tables() -> None:
    # incidents / findings / alarm_events: external_id TEXT, UNIQUE and NOT NULL
    # (idempotent ingest key must always be present). Constraint ordering is not
    # asserted: both "TEXT UNIQUE NOT NULL" and "TEXT NOT NULL UNIQUE" pass.
    for table in ("incidents", "findings", "alarm_events"):
        block = _table_block(table)
        column_def = _column_definition(block, "external_id")
        assert column_def is not None, f"{table} must declare an external_id column"
        assert re.search(
            r"\bTEXT\b", column_def, flags=re.IGNORECASE
        ), f"{table}.external_id must be TEXT (got: {column_def!r})"
        assert re.search(
            r"\bUNIQUE\b", column_def, flags=re.IGNORECASE
        ), f"{table}.external_id must be UNIQUE (got: {column_def!r})"
        assert re.search(
            r"\bNOT\s+NULL\b", column_def, flags=re.IGNORECASE
        ), f"{table}.external_id must be NOT NULL (got: {column_def!r})"


def test_monthly_summaries_period_unique_not_null() -> None:
    block = _table_block("monthly_summaries")
    assert re.search(
        r"period\s+TEXT\s+UNIQUE\s+NOT\s+NULL", block, flags=re.IGNORECASE
    ), "monthly_summaries.period must be TEXT UNIQUE NOT NULL"


def test_child_tables_have_fk_on_delete_cascade() -> None:
    comments = _table_block("incident_comments")
    assert re.search(
        r"incident_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+incidents\s*\(\s*id\s*\)\s+ON\s+DELETE\s+CASCADE",
        comments,
        flags=re.IGNORECASE,
    ), "incident_comments must FK incidents(id) ON DELETE CASCADE"

    triage = _table_block("finding_triage")
    assert re.search(
        r"finding_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+findings\s*\(\s*id\s*\)\s+ON\s+DELETE\s+CASCADE",
        triage,
        flags=re.IGNORECASE,
    ), "finding_triage must FK findings(id) ON DELETE CASCADE"


def test_audit_logs_has_before_after_and_entity_columns() -> None:
    block = _table_block("audit_logs")
    for column in ("entity_type", "entity_id", "action", "before_value", "after_value"):
        assert re.search(
            r"\b" + column + r"\b", block, flags=re.IGNORECASE
        ), f"audit_logs must declare {column}"
    # before/after values stored as JSONB
    assert re.search(r"before_value\s+JSONB", block, flags=re.IGNORECASE)
    assert re.search(r"after_value\s+JSONB", block, flags=re.IGNORECASE)


def test_ddl_contains_no_credentials_or_roles() -> None:
    # Security: schema DDL must not embed credentials or create roles with
    # passwords. Comments are stripped first so that documentation prose (e.g.
    # "no passwords") does not trigger a false positive; only executable SQL is
    # inspected.
    forbidden = [
        r"\bPASSWORD\b",
        r"CREATE\s+ROLE",
        r"CREATE\s+USER",
        r"ALTER\s+ROLE",
        r"ALTER\s+USER",
        r"\bSECRET\b",
        r"postgres(?:ql)?://",  # connection string
    ]
    up_code = _strip_sql_comments(UP_SQL)
    down_code = _strip_sql_comments(DOWN_SQL)
    for pattern in forbidden:
        assert not re.search(pattern, up_code, flags=re.IGNORECASE), (
            f"forbidden credential/role token found in DDL: {pattern}"
        )
        assert not re.search(pattern, down_code, flags=re.IGNORECASE), (
            f"forbidden credential/role token found in down DDL: {pattern}"
        )


def _strip_sql_comments(sql: str) -> str:
    """Remove -- line comments and /* */ block comments from SQL text."""
    no_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    no_line = re.sub(r"--[^\n]*", " ", no_block)
    return no_line


def test_down_migration_drops_all_tables() -> None:
    for table in EXPECTED_TABLES:
        assert re.search(
            r"DROP\s+TABLE\s+(IF\s+EXISTS\s+)?" + re.escape(table) + r"\b",
            DOWN_SQL,
            flags=re.IGNORECASE,
        ), f"down migration must DROP TABLE {table}"


def _column_definition(block: str, column: str) -> str | None:
    """Return the single column-definition fragment for `column` inside a
    CREATE TABLE block.

    The fragment spans from the column name to the end of its definition
    (the next top-level comma or the end of the block). Inline `--` comments
    are stripped so that documentation prose (e.g. a trailing "-- ... UNIQUE
    NOT NULL" note) cannot satisfy the constraint assertions. Constraint
    ordering within the fragment is preserved, so callers can check for the
    presence of tokens without depending on their order.
    """
    body = _strip_sql_comments(block)
    match = re.search(r"\b" + re.escape(column) + r"\b", body, flags=re.IGNORECASE)
    if match is None:
        return None
    start = match.start()
    idx = match.end()
    depth = 0
    while idx < len(body):
        char = body[idx]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            break
        idx += 1
    return body[start:idx].strip()


def _table_block(table: str) -> str:
    """Return the text of a CREATE TABLE <table> ( ... ) statement."""
    match = _create_table_pattern(table).search(UP_SQL)
    assert match, f"missing CREATE TABLE {table}"
    start = match.end()
    depth = 1
    idx = start
    while idx < len(UP_SQL) and depth > 0:
        char = UP_SQL[idx]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        idx += 1
    return UP_SQL[start : idx - 1]
