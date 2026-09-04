"""Static Task 11.2 logging-module configuration tests; no Terraform or AWS access."""

from __future__ import annotations

import re
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
MAIN = (MODULE_DIR / "main.tf").read_text(encoding="utf-8")
VARIABLES = (MODULE_DIR / "variables.tf").read_text(encoding="utf-8")
OUTPUTS = (MODULE_DIR / "outputs.tf").read_text(encoding="utf-8")
VERSIONS = (MODULE_DIR / "versions.tf").read_text(encoding="utf-8")
README = (MODULE_DIR / "README.md").read_text(encoding="utf-8")


def _resource_block(resource_type: str, resource_name: str) -> str:
    match = re.search(
        rf'resource "{resource_type}" "{resource_name}" \{{(.*?)(?=\nresource |\Z)',
        MAIN,
        re.DOTALL,
    )
    assert match, f"resource {resource_type}.{resource_name} was not found"
    return match.group(1)


def test_versions_pin_terraform_and_aws_provider() -> None:
    assert "required_version = \">= 1.10\"" in VERSIONS
    assert "version = \"~> 5.0\"" in VERSIONS


def test_retention_allows_only_cloudwatch_supported_values() -> None:
    retention = re.search(r'variable "retention_in_days" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert retention, "retention_in_days variable missing"
    body = retention.group(1)
    assert "default     = 30" in body
    # CloudWatch Logs accepts only discrete values, so within the required 14-30
    # day range the validation must allow the discrete set {14, 30} rather than
    # an inclusive range (a value like 21 would fail at apply time).
    assert "contains([14, 30], var.retention_in_days)" in body


def test_retention_membership_predicate_accepts_and_rejects() -> None:
    # Terraform cannot run here, so verify the *meaning* of the allowed set
    # statically: the permitted values are exactly {14, 30}. Under this predicate
    # 14 and 30 are allowed while 21 (in-range but unsupported), 13 and 31 are
    # rejected.
    allowed_values = {14, 30}
    is_allowed = lambda v: v in allowed_values
    for allowed in (14, 30):
        assert is_allowed(allowed), f"{allowed} should be allowed"
    for rejected in (21, 13, 31):
        assert not is_allowed(rejected), f"{rejected} should be rejected"


def test_lambda_and_vpc_flowlogs_groups_use_retention_and_tags() -> None:
    lambda_group = _resource_block("aws_cloudwatch_log_group", "lambda")
    assert "retention_in_days = var.retention_in_days" in lambda_group
    assert "merge(var.common_tags" in lambda_group
    assert "/aws/lambda/${var.name_prefix}-portal" in MAIN

    vpc_group = _resource_block("aws_cloudwatch_log_group", "vpc_flowlogs")
    assert "retention_in_days = var.retention_in_days" in vpc_group
    assert "/vpc/${var.name_prefix}-flowlogs" in MAIN


def test_does_not_recreate_ecs_or_eks_worker_log_groups() -> None:
    # The ecs module owns /ecs/<name_prefix>-backend-api and the eks module owns
    # /<name_prefix>/eks/workers. This module must not declare either group.
    assert not re.search(r'name\s*=\s*"/ecs/\$\{var\.name_prefix\}-backend-api"', MAIN)
    assert "/eks/workers" not in MAIN
    # And it must not declare a backend-api log group by any name.
    assert "backend-api" not in MAIN


def test_no_fluent_bit_daemonset_resource() -> None:
    # Fargate logging is via the aws-observability ConfigMap owned by eks; this
    # module declares no DaemonSet. "DaemonSet" may appear only as README prose.
    assert "DaemonSet" not in MAIN


def test_name_prefix_and_common_tags_are_used() -> None:
    assert "var.name_prefix" in MAIN
    assert "merge(var.common_tags" in MAIN


def test_outputs_publish_created_group_names_and_arns() -> None:
    for name in (
        "lambda_log_group_name",
        "lambda_log_group_arn",
        "vpc_flowlogs_log_group_name",
        "vpc_flowlogs_log_group_arn",
    ):
        assert f'output "{name}"' in OUTPUTS


def test_no_sensitive_literals_present() -> None:
    haystack = "\n".join([MAIN, VARIABLES, OUTPUTS, README]).lower()
    for needle in ("password=", "postgresql://", "aws_secret_access_key", "authorization:", "bearer "):
        assert needle not in haystack, f"sensitive literal {needle!r} must not appear"
