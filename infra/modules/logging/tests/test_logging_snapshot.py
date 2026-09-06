"""Static logging-module configuration tests (Task 26, VPC Flow Logs); no Terraform or AWS access."""

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
        rf'resource "{resource_type}" "{resource_name}" \{{(.*?)(?=\nresource |\ndata |\Z)',
        MAIN,
        re.DOTALL,
    )
    assert match, f"resource {resource_type}.{resource_name} was not found"
    return match.group(1)


def test_versions_pin_terraform_and_aws_provider() -> None:
    assert 'required_version = ">= 1.10"' in VERSIONS
    assert 'version = "~> 5.0"' in VERSIONS


def test_flow_log_exists_with_all_traffic_and_cloudwatch_destination() -> None:
    flow = _resource_block("aws_flow_log", "this")
    assert "vpc_id                   = var.vpc_id" in flow
    assert 'traffic_type             = "ALL"' in flow
    assert 'log_destination_type     = "cloud-watch-logs"' in flow
    assert "log_destination          = aws_cloudwatch_log_group.vpc_flowlogs.arn" in flow
    assert "iam_role_arn             = aws_iam_role.flowlogs.arn" in flow


def test_flow_log_service_trust_is_vpc_flow_logs_only() -> None:
    trust = re.search(r'data "aws_iam_policy_document" "flowlogs_trust" \{(.*?)\n\}\n', MAIN, re.DOTALL)
    assert trust
    body = trust.group(1)
    assert "vpc-flow-logs.amazonaws.com" in body
    assert '"sts:AssumeRole"' in body
    assert "aws:SourceAccount" in body
    assert "data.aws_caller_identity.current.account_id" in body
    assert "aws:SourceArn" in body
    assert "data.aws_partition.current.partition" in body
    assert "data.aws_region.current.name" in body
    assert ":vpc-flow-log/*" in body
    # No other service principal in the trust policy.
    assert "ecs-tasks" not in body and "lambda" not in body


def test_write_permission_scoped_to_dedicated_log_group() -> None:
    policy = re.search(r'data "aws_iam_policy_document" "flowlogs" \{(.*?)\n\}\n', MAIN, re.DOTALL)
    assert policy
    body = policy.group(1)
    assert "logs:CreateLogGroup" in body
    assert "logs:CreateLogStream" in body
    assert "logs:PutLogEvents" in body
    assert "logs:DescribeLogStreams" in body
    assert "logs:DescribeLogGroups" in body
    assert "aws_cloudwatch_log_group.vpc_flowlogs.arn" in body
    assert ":log-stream:*" in body
    # Only DescribeLogGroups uses a wildcard, and it is region-scoped.
    assert body.count('resources = ["*"]') == 1
    assert "aws:RequestedRegion" in body


def test_flow_log_waits_for_inline_policy_attachment() -> None:
    flow = _resource_block("aws_flow_log", "this")
    assert "depends_on = [aws_iam_role_policy.flowlogs]" in flow


def test_no_admin_or_broad_service_permissions() -> None:
    lowered = MAIN_CODE.lower()
    assert '"*:*"' not in lowered
    assert "administratoraccess" not in lowered
    # No blanket "logs:*" or resource "*" on the write statement.
    assert "logs:*" not in MAIN_CODE


def test_vpc_flowlogs_log_group_uses_retention_tags_and_name() -> None:
    group = _resource_block("aws_cloudwatch_log_group", "vpc_flowlogs")
    assert "retention_in_days = var.retention_in_days" in group
    assert "merge(var.common_tags" in group
    assert "/vpc/${var.name_prefix}-flowlogs" in MAIN


def test_retention_allows_only_cloudwatch_supported_values() -> None:
    retention = re.search(r'variable "retention_in_days" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert retention
    body = retention.group(1)
    assert "default     = 30" in body
    assert "contains([14, 30], var.retention_in_days)" in body


def test_vpc_id_is_required_input() -> None:
    block = re.search(r'variable "vpc_id" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert block
    assert "default" not in block.group(1), "vpc_id must be required (no default)"
    assert "vpc-[0-9a-f]+" in block.group(1)


def test_partition_region_account_not_hardcoded() -> None:
    # The write policy must not hard-code arn:aws:logs literals; it references the
    # log group resource ARN instead.
    assert not re.search(r"arn:aws:logs:", MAIN), "must not hard-code arn:aws:logs"
    assert "data.aws_region.current.name" in MAIN


def test_logging_module_does_not_create_other_modules_log_groups() -> None:
    # Only ONE aws_cloudwatch_log_group (vpc_flowlogs). No lambda/ecs/eks group.
    assert MAIN.count('resource "aws_cloudwatch_log_group"') == 1
    assert 'resource "aws_cloudwatch_log_group" "vpc_flowlogs"' in MAIN
    assert 'resource "aws_cloudwatch_log_group" "lambda"' not in MAIN
    assert "/aws/lambda/" not in MAIN
    assert "backend-api" not in MAIN
    assert "/eks/workers" not in MAIN
    # Retired Lambda-group interface must be gone.
    assert "enable_lambda_log_group" not in VARIABLES
    assert 'output "lambda_log_group_name"' not in OUTPUTS


def test_outputs_publish_flowlog_identifiers() -> None:
    for name in ("flow_log_id", "vpc_flowlogs_log_group_name",
                 "vpc_flowlogs_log_group_arn", "vpc_flowlogs_role_arn"):
        assert f'output "{name}"' in OUTPUTS, f"output {name} missing"


def test_name_prefix_and_common_tags_are_used() -> None:
    assert "var.name_prefix" in MAIN
    assert "merge(var.common_tags" in MAIN


def test_no_sensitive_or_real_literals_present() -> None:
    haystack = "\n".join([MAIN, VARIABLES, OUTPUTS, README]).lower()
    for needle in ("password=", "postgresql://", "aws_secret_access_key", "authorization: bearer "):
        assert needle not in haystack, f"sensitive literal {needle!r} must not appear"
    assert not re.search(r"\b\d{12}\b", haystack), "no literal 12-digit account id may appear"
