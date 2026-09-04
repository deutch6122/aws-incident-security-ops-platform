"""Unit, Property 11, and Terraform/Python naming consistency tests."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from naming import ENVIRONMENT, MAX_RESOURCE_NAME_LENGTH, PROJECT, resource_name

TESTS_DIR = Path(__file__).resolve().parent
DEV_ROOT = TESTS_DIR.parent
EXPECTED_NAME_PATTERN = re.compile(r"^ops-platform-dev-.+")
SAFE_SUFFIX_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _is_valid_suffix(value: str) -> bool:
    return (
        SAFE_SUFFIX_PATTERN.fullmatch(value) is not None
        and len(f"{PROJECT}-{ENVIRONMENT}-{value}") <= MAX_RESOURCE_NAME_LENGTH
    )


@st.composite
def safe_suffixes(draw: st.DrawFn) -> str:
    segment = st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
        min_size=1,
        max_size=12,
    )
    parts = draw(st.lists(segment, min_size=1, max_size=4))
    suffix = "-".join(parts)
    return suffix[:46].rstrip("-")


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [
        ("vpc", "ops-platform-dev-vpc"),
        ("api-2", "ops-platform-dev-api-2"),
        ("a" * 46, f"ops-platform-dev-{'a' * 46}"),
    ],
)
def test_resource_name_accepts_safe_suffixes(suffix: str, expected: str) -> None:
    assert resource_name(suffix) == expected


@pytest.mark.parametrize(
    "suffix",
    ["", " ", "api server", "API", "api_server", "-api", "api-", "api--server", "a" * 47],
)
def test_resource_name_rejects_unsafe_suffixes(suffix: str) -> None:
    with pytest.raises(ValueError):
        resource_name(suffix)


def test_resource_name_rejects_non_string_input() -> None:
    with pytest.raises(TypeError):
        resource_name(123)  # type: ignore[arg-type]


# Feature: aws-incident-security-ops-platform, Property 11: For any Platform が作成するリソース定義について、そのリソース名は命名規則 ops-platform-dev-<resource> のパターン（^ops-platform-dev-.+）に一致しなければならない
# **Validates: Requirements 19.1**
@given(
    st.one_of(
        safe_suffixes(),
        st.text(min_size=0, max_size=100),
        st.sampled_from(
            ["", " ", "UPPER", "has space", "symbol!", "-leading", "trailing-", "double--dash", "x" * 100]
        ),
    )
)
@settings(max_examples=100)
def test_property_11_resource_names_follow_platform_convention(resource: str) -> None:
    if _is_valid_suffix(resource):
        generated = resource_name(resource)
        assert EXPECTED_NAME_PATTERN.fullmatch(generated)
        assert len(generated) <= MAX_RESOURCE_NAME_LENGTH
        assert "--" not in generated
        assert not generated.endswith("-")
    else:
        with pytest.raises(ValueError):
            resource_name(resource)


def test_terraform_and_python_naming_contracts_are_aligned() -> None:
    variables = (DEV_ROOT / "variables.tf").read_text(encoding="utf-8")
    locals_tf = (DEV_ROOT / "locals.tf").read_text(encoding="utf-8")
    backend_example = (DEV_ROOT / "backend.tf.example").read_text(encoding="utf-8")

    project_default = re.search(
        r'variable "project".*?default\s*=\s*"([^"]+)"', variables, re.DOTALL
    )
    env_default = re.search(
        r'variable "env".*?default\s*=\s*"([^"]+)"', variables, re.DOTALL
    )

    assert project_default and project_default.group(1) == PROJECT
    assert env_default and env_default.group(1) == ENVIRONMENT
    assert 'name_prefix = "${var.project}-${var.env}"' in locals_tf
    assert 'logical_name => "${local.name_prefix}-${suffix}"' in locals_tf
    assert 'regex("^[a-z0-9]+(-[a-z0-9]+)*$", suffix)' in variables
    assert 'length("${var.project}-${var.env}-${suffix}") <= 63' in variables
    assert "use_lockfile = true" in backend_example
