"""Static Task 14.1 cognito-module configuration tests; no Terraform or AWS access."""

from __future__ import annotations

import re
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
MAIN = (MODULE_DIR / "main.tf").read_text(encoding="utf-8")
VARIABLES = (MODULE_DIR / "variables.tf").read_text(encoding="utf-8")
OUTPUTS = (MODULE_DIR / "outputs.tf").read_text(encoding="utf-8")
VERSIONS = (MODULE_DIR / "versions.tf").read_text(encoding="utf-8")
README = (MODULE_DIR / "README.md").read_text(encoding="utf-8")


def _strip_comments(text: str) -> str:
    return "\n".join(re.sub(r"#.*$", "", line) for line in text.splitlines())


MAIN_CODE = _strip_comments(MAIN)


def _resource_block(resource_type: str, resource_name: str) -> str:
    match = re.search(
        rf'resource "{resource_type}" "{resource_name}" \{{(.*?)(?=\nresource |\Z)',
        MAIN,
        re.DOTALL,
    )
    assert match, f"resource {resource_type}.{resource_name} was not found"
    return match.group(1)


def test_versions_pin_terraform_and_aws_provider() -> None:
    assert 'required_version = ">= 1.10"' in VERSIONS
    assert 'version = "~> 5.0"' in VERSIONS


def test_user_pool_exists() -> None:
    assert 'resource "aws_cognito_user_pool" "this"' in MAIN


def test_app_client_exists() -> None:
    assert 'resource "aws_cognito_user_pool_client" "portal"' in MAIN


def test_app_client_has_no_client_secret() -> None:
    # A browser SPA cannot keep a secret; the public App Client must not generate
    # one (Requirement 9.1/9.2).
    block = _resource_block("aws_cognito_user_pool_client", "portal")
    assert "generate_secret = false" in block
    assert "generate_secret = true" not in MAIN


def test_hosted_ui_uses_code_flow_for_public_pkce_client() -> None:
    block = _resource_block("aws_cognito_user_pool_client", "portal")
    assert 'allowed_oauth_flows                  = ["code"]' in block
    assert "allowed_oauth_flows_user_pool_client = true" in block
    assert 'supported_identity_providers         = ["COGNITO"]' in block
    assert "implicit" not in block.lower()
    assert "callback_urls" in block and "logout_urls" in block
    assert 'resource "aws_cognito_user_pool_domain" "portal"' in MAIN


def test_callback_and_logout_lists_are_nonempty_and_validated() -> None:
    for name, expected in (
        ("cognito_callback_urls", "http://localhost:5173/callback"),
        ("cognito_logout_urls", "http://localhost:5173/"),
    ):
        match = re.search(rf'variable "{name}" \{{(.*?)\n\}}', VARIABLES, re.DOTALL)
        assert match, f"{name} variable missing"
        body = match.group(1)
        assert expected in body
        assert "length(var." in body and "> 0" in body
        assert "alltrue" in body
    keep = re.search(r'variable "cognito_keep_localhost_urls" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert keep and "default     = false" in keep.group(1)


def test_user_pool_has_password_policy_and_recovery() -> None:
    block = _resource_block("aws_cognito_user_pool", "this")
    assert "password_policy {" in block
    assert "minimum_length" in block
    assert "account_recovery_setting {" in block
    assert "username_configuration {" in block


def test_password_minimum_length_variable_is_bounded() -> None:
    match = re.search(r'variable "password_minimum_length" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert match, "password_minimum_length variable missing"
    body = match.group(1)
    assert "validation {" in body
    assert ">= 8" in body and "<= 99" in body


def test_naming_uses_prefix_and_common_tags_applied() -> None:
    assert "var.name_prefix" in MAIN
    # Only the User Pool is taggable (App Client does not accept tags).
    assert "merge(var.common_tags" in MAIN


def test_issuer_url_built_locally_without_real_id() -> None:
    match = re.search(r'output "issuer_url" \{(.*?)\n\}', OUTPUTS, re.DOTALL)
    assert match, "issuer_url output missing"
    body = match.group(1)
    assert "https://cognito-idp.${local.region}.amazonaws.com/" in body
    assert "aws_cognito_user_pool.this.id" in body
    # No concrete pool id / account id literal embedded.
    assert not re.search(r"amazonaws\.com/[a-z]{2}-[a-z]+-\d_", OUTPUTS)


def test_does_not_reference_product_a_resources() -> None:
    lowered = MAIN_CODE.lower()
    for forbidden in (
        "aws_rds",
        "aurora",
        "aws_eks",
        "aws_ecs",
        "aws_sqs",
        "rds_cluster",
        "eks_cluster",
        "backend-api",
        "backend_api",
    ):
        assert forbidden not in lowered, f"Product_A reference {forbidden!r} must not appear"


def test_outputs_publish_ids_arn_endpoint_and_issuer() -> None:
    for name in (
        "user_pool_id",
        "user_pool_arn",
        "user_pool_endpoint",
        "app_client_id",
        "issuer_url",
        "hosted_domain",
        "hosted_ui_base_url",
    ):
        assert f'output "{name}"' in OUTPUTS, f"output {name} missing"


def test_no_sensitive_or_real_literals_present() -> None:
    haystack = "\n".join([MAIN, VARIABLES, OUTPUTS, README]).lower()
    for needle in (
        "password=",
        "postgresql://",
        "aws_secret_access_key",
        "authorization:",
        "bearer ",
        "arn:aws:cognito-idp:ap-northeast-1:",
    ):
        assert needle not in haystack, f"sensitive/real literal {needle!r} must not appear"
