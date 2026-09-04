"""Task 16.1 static tests for the Status Portal front-end (Python/pytest).

These analyze the vanilla HTML/CSS/JS files statically (no Node, no build). They
verify:
* the five screens exist with the required containers/elements,
* api.js references all four Portal_API endpoints,
* config.js contains only placeholders (no real ids, domains, or tokens),
* status_id containing "/" is not built into detail API paths (rejected/encoded).

Mirrors the existing IaC snapshot-test approach (static file-content analysis).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PUBLIC = Path(__file__).resolve().parents[1] / "src" / "public"

HTML_PAGES = {
    "index.html": "login-button",
    "status.html": "status-list",
    "status-detail.html": "status-detail",
    "reports.html": "report-list",
    "report-detail.html": "report-detail",
}


def _read(rel: str) -> str:
    return (PUBLIC / rel).read_text(encoding="utf-8")


# --- screens exist with required containers ---------------------------------
@pytest.mark.parametrize("page,container_id", sorted(HTML_PAGES.items()))
def test_each_screen_exists_with_its_container(page: str, container_id: str) -> None:
    assert (PUBLIC / page).is_file(), f"missing page: {page}"
    html = _read(page)
    assert f'id="{container_id}"' in html, f"{page} missing #{container_id}"
    # Every page wires the shared client + config.
    assert "config.js" in html
    assert "js/api.js" in html
    assert "js/pages.js" in html


def test_login_page_has_login_control() -> None:
    html = _read("index.html")
    assert 'id="login-button"' in html
    assert "Cognito" in html


# --- api.js references all four endpoints -----------------------------------
def test_api_client_references_all_four_endpoints() -> None:
    api = _read("js/api.js")
    assert "/status" in api
    assert "/status/" in api
    assert "/reports" in api
    assert "/reports/" in api
    # It uses fetch and attaches an Authorization header structure.
    assert ".fetch(" in api
    assert "Authorization" in api


def test_api_client_exposes_the_four_calls() -> None:
    api = _read("js/api.js")
    for fn in ("listStatus", "getStatus", "listReports", "getReport"):
        assert fn in api, f"api.js missing {fn}"


# --- config.js is placeholder-only ------------------------------------------
def test_config_contains_placeholder_keys_only() -> None:
    config = _read("config.js")
    for key in ("USER_POOL_ID", "APP_CLIENT_ID", "REGION", "API_BASE"):
        assert key in config, f"config.js missing {key}"


def test_config_has_no_real_values_domains_or_tokens() -> None:
    config = _read("config.js")

    # No real Cognito pool id like "ap-northeast-1_ABCDE12345".
    assert not re.search(r"[a-z]{2}-[a-z]+-\d_[A-Za-z0-9]{6,}", config), (
        "config.js appears to contain a real Cognito User Pool id"
    )
    # No real amazoncognito / execute-api / cloudfront domains.
    for domain in ("amazoncognito.com", "execute-api", "cloudfront.net", "amazonaws.com"):
        assert domain not in config, f"config.js must not embed real domain: {domain}"
    # No embedded bearer/JWT token value.
    assert "Bearer " not in config
    assert not re.search(r"eyJ[A-Za-z0-9_\-]{10,}", config), "config.js must not embed a JWT"
    # API base stays same-origin (no hard-coded scheme+host).
    assert "https://" not in config


def test_no_source_file_embeds_a_token_value() -> None:
    for path in PUBLIC.rglob("*"):
        if path.suffix not in {".js", ".html"}:
            continue
        content = path.read_text(encoding="utf-8")
        assert not re.search(r"eyJ[A-Za-z0-9_\-]{10,}", content), f"token literal in {path.name}"


# --- status_id "/" safety ----------------------------------------------------
def test_api_client_rejects_status_id_with_slash() -> None:
    api = _read("js/api.js")
    # buildStatusDetailPath rejects "/" and URL-encodes the id.
    assert "buildStatusDetailPath" in api
    assert 'indexOf("/")' in api
    assert "encodeURIComponent" in api


def test_pages_build_detail_links_via_safe_helpers() -> None:
    pages = _read("js/pages.js")
    # Detail navigation encodes ids and the API path building is centralized in
    # api.js's buildStatusDetailPath/buildReportDetailPath (which reject "/").
    assert "encodeURIComponent" in pages
    assert "getStatus" in pages
    assert "getReport" in pages
