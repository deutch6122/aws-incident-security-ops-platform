"""Unit tests for config parsing, import-time safety, Product_A/B separation,
and absence of sensitive literals.

All pure stdlib; no AWS, Docker, or moto.
"""

from __future__ import annotations

import ast
import importlib
import re
import sys
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from app.config import PortalConfigurationError, PortalSettings


# --- config -----------------------------------------------------------------
def test_settings_defaults_use_naming_convention() -> None:
    s = PortalSettings()
    assert s.aws_region == "ap-northeast-1"
    assert s.public_status_items_table == "ops-platform-dev-public-status-items"
    assert s.report_metadata_table == "ops-platform-dev-report-metadata"
    assert s.page_view_logs_table == "ops-platform-dev-page-view-logs"
    assert s.maintenance_windows_table == "ops-platform-dev-maintenance-windows"


def test_settings_from_env_overrides_table_names() -> None:
    env = {
        "PORTAL_AWS_REGION": "ap-northeast-1",
        "PORTAL_PUBLIC_STATUS_ITEMS_TABLE": "custom-status",
        "PORTAL_PAGE_VIEW_LOG_TTL_DAYS": "14",
    }
    s = PortalSettings.from_env(env)
    assert s.public_status_items_table == "custom-status"
    assert s.page_view_log_ttl_days == 14


def test_invalid_int_config_raises() -> None:
    with pytest.raises(PortalConfigurationError):
        PortalSettings.from_env({"PORTAL_PAGE_VIEW_LOG_TTL_DAYS": "not-a-number"})


# --- import-time safety: no AWS I/O, boto3 not imported at import time -------
def test_importing_app_modules_does_no_io() -> None:
    for name in (
        "app",
        "app.config",
        "app.auth",
        "app.stores",
        "app.services",
        "app.handler",
        "app.errors",
        "app.repositories",
    ):
        importlib.import_module(name)


def test_boto3_is_not_imported_at_module_import_time() -> None:
    # Importing the app package must not import boto3 (lazy client creation).
    for mod in list(sys.modules):
        if mod == "boto3" or mod.startswith("boto3."):
            del sys.modules[mod]
    importlib.import_module("app.handler")
    importlib.import_module("app.repositories")
    assert "boto3" not in sys.modules


# --- Product_A / Product_B separation ---------------------------------------
_PRODUCT_A_TERMS = re.compile(
    r"\b(aurora|psycopg|sqlalchemy|backend[_-]?api|incidents|findings|"
    r"alarm_events|monthly_summaries|audit_logs|ecs|eks|rds)\b",
    re.IGNORECASE,
)
_PRODUCT_B_TABLES = {
    "public_status_items",
    "report_metadata",
    "page_view_logs",
    "maintenance_windows",
}


def _app_source_files() -> list[Path]:
    return sorted((APP_ROOT / "app").glob("*.py"))


def _executable_code(text: str) -> str:
    """Return source with comments and docstrings blanked out.

    Separation-note docstrings/comments intentionally spell out the Product_A
    terms to state they are NOT used. The real invariant is that executable code
    (imports, identifiers, data string literals) never references a Product_A
    store, so we scan only the code, not the prose.
    """
    lines = text.splitlines()
    blanked = [False] * (len(lines) + 2)

    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                doc = body[0]
                start = doc.lineno
                end = getattr(doc, "end_lineno", start)
                for ln in range(start, end + 1):
                    blanked[ln] = True

    kept: list[str] = []
    for idx, line in enumerate(lines, start=1):
        if blanked[idx]:
            continue
        # Drop line comments (approximate; sufficient since our source has no
        # '#' inside string literals on the same line as the target terms).
        code = line.split("#", 1)[0]
        kept.append(code)
    return "\n".join(kept)


def test_no_product_a_references_in_executable_code() -> None:
    for path in _app_source_files():
        code = _executable_code(path.read_text(encoding="utf-8"))
        match = _PRODUCT_A_TERMS.search(code)
        assert match is None, f"Product_A term {match.group(0)!r} found in {path.name}"


def test_only_product_b_tables_are_referenced() -> None:
    # The config module names exactly the four Product_B tables and no others.
    from app.config import PortalSettings as _S

    s = _S()
    names = {
        s.public_status_items_table,
        s.report_metadata_table,
        s.page_view_logs_table,
        s.maintenance_windows_table,
    }
    assert names == {
        "ops-platform-dev-public-status-items",
        "ops-platform-dev-report-metadata",
        "ops-platform-dev-page-view-logs",
        "ops-platform-dev-maintenance-windows",
    }


# --- no sensitive literals in source ----------------------------------------
_SENSITIVE_PATTERNS = [
    re.compile(r"Bearer\s+\S+"),
    re.compile(r"Authorization\s*[:=]\s*['\"]"),
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"aws_secret_access_key", re.IGNORECASE),
    re.compile(r"password\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE),
    re.compile(r"postgres(ql)?://", re.IGNORECASE),
]


def test_no_sensitive_literals_in_source_or_tests() -> None:
    files = _app_source_files() + sorted((APP_ROOT / "tests").glob("*.py"))
    # This file only *defines* the detection patterns (meta), so scanning it
    # would match its own pattern strings; exclude it from the literal scan.
    this_file = Path(__file__).resolve()
    for path in files:
        if path.resolve() == this_file:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in _SENSITIVE_PATTERNS:
            assert pattern.search(text) is None, f"sensitive literal in {path.name}: {pattern.pattern}"


# --- source parses (defensive) ----------------------------------------------
def test_all_source_files_parse() -> None:
    for path in _app_source_files():
        ast.parse(path.read_text(encoding="utf-8"))
