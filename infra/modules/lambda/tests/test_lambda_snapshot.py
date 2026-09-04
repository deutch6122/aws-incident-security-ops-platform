"""Static Task 14.3 lambda-module configuration tests; no Terraform or AWS access."""

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


def _statement_block(sid: str) -> str:
    # Isolate one IAM policy Statement object by its Sid so resource assertions
    # apply to exactly that statement.
    match = re.search(
        rf'\{{\s*Sid\s*=\s*"{sid}".*?(?=\n\s*\{{\s*Sid|\n\s*\]\s*\n\s*\}}\))',
        MAIN,
        re.DOTALL,
    )
    assert match, f"IAM statement with Sid {sid} not found"
    return match.group(0)


def test_versions_pin_terraform_and_aws_provider() -> None:
    assert 'required_version = ">= 1.10"' in VERSIONS
    assert 'version = "~> 5.0"' in VERSIONS


def test_lambda_function_exists_with_python_runtime() -> None:
    block = _resource_block("aws_lambda_function", "portal")
    assert "runtime       = var.runtime" in block or "runtime = var.runtime" in block
    match = re.search(r'variable "runtime" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert match and 'default     = "python3.12"' in match.group(1)


def test_memory_size_bounded_256_to_512() -> None:
    match = re.search(r'variable "memory_size" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert match, "memory_size variable missing"
    body = match.group(1)
    assert "validation {" in body
    assert ">= 256" in body and "<= 512" in body


def test_timeout_default_is_10() -> None:
    match = re.search(r'variable "timeout" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert match, "timeout variable missing"
    assert "default     = 10" in match.group(1) or "default = 10" in match.group(1)


def test_iam_role_named_lambda_portal_role() -> None:
    block = _resource_block("aws_iam_role", "portal")
    assert 'role_name      = "${var.name_prefix}-lambda-portal-role"' in MAIN or \
        "lambda-portal-role" in MAIN
    assert "lambda.amazonaws.com" in block


def test_dynamodb_read_scope_covers_product_b_read_tables() -> None:
    read_stmt = _statement_block("PortalDynamoRead")
    for action in ("GetItem", "BatchGetItem", "Query", "Scan"):
        assert f"dynamodb:{action}" in read_stmt, f"read action {action} missing"
    # Read scope references the three read tables via the read_table_arns local.
    assert "local.read_table_arns" in read_stmt
    for arn in (
        "var.public_status_items_table_arn",
        "var.report_metadata_table_arn",
        "var.maintenance_windows_table_arn",
    ):
        assert arn in MAIN, f"read table ARN var {arn} missing from read scope"


def test_write_scope_is_page_view_logs_only() -> None:
    write_stmt = _statement_block("PortalPageViewLogsWrite")
    # Write action(s) present and the resource is ONLY page_view_logs.
    assert "dynamodb:PutItem" in write_stmt
    assert "var.page_view_logs_table_arn" in write_stmt
    # No other table ARN may appear in the write statement.
    for other in (
        "var.public_status_items_table_arn",
        "var.report_metadata_table_arn",
        "var.maintenance_windows_table_arn",
    ):
        assert other not in write_stmt, f"write statement must not include {other}"
    # No broad write/delete/update actions leaked into the write statement.
    for forbidden_action in ("DeleteItem", "UpdateItem", "BatchWriteItem", "DeleteTable"):
        assert f"dynamodb:{forbidden_action}" not in write_stmt


def test_cloudwatch_logs_permissions_present() -> None:
    assert 'resource "aws_cloudwatch_log_group" "portal"' in MAIN
    logs_match = re.search(r'"logs" \{(.*?)policy = jsonencode', MAIN, re.DOTALL)
    for action in ("CreateLogGroup", "CreateLogStream", "PutLogEvents"):
        assert f"logs:{action}" in MAIN, f"logs action {action} missing"


def test_naming_uses_prefix_and_common_tags_applied() -> None:
    assert "var.name_prefix" in MAIN
    # function + role + log group are taggable.
    assert MAIN.count("merge(var.common_tags") == 3


def test_no_product_a_permissions_or_references() -> None:
    # lambda-portal-role must have zero access to Product_A. Guard against any
    # Aurora/RDS/ECS/EKS/Product_A-SQS/Backend API reference or IAM action.
    lowered = MAIN_CODE.lower()
    for forbidden in (
        "rds:",
        "rds-db",
        "aurora",
        "ecs:",
        "eks:",
        "sqs:",
        "aws_rds",
        "aws_ecs",
        "aws_eks",
        "aws_sqs",
        "backend-api",
        "backend_api",
        "aws_db_instance",
        "aws_rds_cluster",
    ):
        assert forbidden not in lowered, f"Product_A reference/permission {forbidden!r} must not appear"


def test_outputs_publish_function_arn_invoke_and_role() -> None:
    for name in (
        "lambda_function_name",
        "lambda_function_arn",
        "lambda_invoke_arn",
        "lambda_role_arn",
    ):
        assert f'output "{name}"' in OUTPUTS, f"output {name} missing"


def test_no_sensitive_or_real_literals_present() -> None:
    haystack = "\n".join([MAIN, VARIABLES, OUTPUTS, README]).lower()
    for needle in (
        "password=",
        "postgresql://",
        "aws_secret_access_key",
        "authorization: bearer",
        "bearer ey",
        "arn:aws:dynamodb:ap-northeast-1:",
        "arn:aws:lambda:ap-northeast-1:",
    ):
        assert needle not in haystack, f"sensitive/real literal {needle!r} must not appear"
