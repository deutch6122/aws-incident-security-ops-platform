"""Static Task 11.1 messaging-module configuration tests; no Terraform or AWS access."""

from __future__ import annotations

import re
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
MAIN = (MODULE_DIR / "main.tf").read_text(encoding="utf-8")
VARIABLES = (MODULE_DIR / "variables.tf").read_text(encoding="utf-8")
OUTPUTS = (MODULE_DIR / "outputs.tf").read_text(encoding="utf-8")
VERSIONS = (MODULE_DIR / "versions.tf").read_text(encoding="utf-8")
README = (MODULE_DIR / "README.md").read_text(encoding="utf-8")


def _resource_block(resource_type: str, resource_name: str, kind: str = "resource") -> str:
    match = re.search(
        rf'{kind} "{resource_type}" "{resource_name}" \{{(.*?)(?=\n{kind} |\Z)',
        MAIN,
        re.DOTALL,
    )
    assert match, f"{kind} {resource_type}.{resource_name} was not found"
    return match.group(1)


def test_versions_pin_terraform_and_aws_provider() -> None:
    assert "required_version = \">= 1.10\"" in VERSIONS
    assert "version = \"~> 5.0\"" in VERSIONS


def test_main_queue_is_standard_with_redrive_to_dlq() -> None:
    main_queue = _resource_block("aws_sqs_queue", "main")
    # Standard queue: no FIFO marker.
    assert "fifo_queue" not in main_queue
    assert "redrive_policy" in main_queue
    assert "maxReceiveCount" in main_queue
    assert "var.max_receive_count" in main_queue
    assert "aws_sqs_queue.dlq.arn" in main_queue


def test_dlq_and_main_queue_enable_sqs_managed_sse() -> None:
    dlq = _resource_block("aws_sqs_queue", "dlq")
    main_queue = _resource_block("aws_sqs_queue", "main")
    assert "sqs_managed_sse_enabled   = var.sqs_managed_sse" in dlq
    assert "sqs_managed_sse_enabled    = var.sqs_managed_sse" in main_queue
    sse_var = re.search(r'variable "sqs_managed_sse" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert sse_var and "default     = true" in sse_var.group(1)


def test_dlq_redrive_allow_policy_limits_to_main_queue() -> None:
    allow = _resource_block("aws_sqs_queue_redrive_allow_policy", "dlq")
    assert "byQueue" in allow
    assert "aws_sqs_queue.main.arn" in allow


def test_eventbridge_rule_and_sqs_target_exist() -> None:
    rule = _resource_block("aws_cloudwatch_event_rule", "this")
    assert "event_pattern = jsonencode(var.eventbridge_event_pattern)" in rule
    target = _resource_block("aws_cloudwatch_event_target", "this")
    assert "rule      = aws_cloudwatch_event_rule.this.name" in target
    assert "arn       = aws_sqs_queue.main.arn" in target


def test_queue_policy_restricts_to_eventbridge_service_and_source_arn() -> None:
    policy_doc = _resource_block("aws_iam_policy_document", "queue_policy", kind="data")
    assert "events.amazonaws.com" in policy_doc
    assert "sqs:SendMessage" in policy_doc
    assert "aws:SourceArn" in policy_doc
    assert "aws_cloudwatch_event_rule.this.arn" in policy_doc
    queue_policy = _resource_block("aws_sqs_queue_policy", "this")
    assert "data.aws_iam_policy_document.queue_policy.json" in queue_policy


def test_variable_validations_present() -> None:
    assert 'condition     = can(regex("^[a-z0-9]+(-[a-z0-9]+)*$", var.name_prefix))' in VARIABLES
    vt = re.search(r'variable "visibility_timeout_seconds" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert vt and "43200" in vt.group(1)
    mr = re.search(r'variable "max_receive_count" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert mr and "1000" in mr.group(1)


def test_outputs_publish_queue_and_dlq_identifiers() -> None:
    for name in ("queue_arn", "queue_url", "queue_name", "dlq_arn", "dlq_url", "dlq_name", "event_rule_arn"):
        assert f'output "{name}"' in OUTPUTS
    assert "aws_sqs_queue.main.arn" in OUTPUTS
    assert "aws_sqs_queue.dlq.arn" in OUTPUTS


def test_name_prefix_and_common_tags_are_used() -> None:
    assert "var.name_prefix" in MAIN
    assert "merge(var.common_tags" in MAIN


def test_no_sensitive_literals_present() -> None:
    haystack = "\n".join([MAIN, VARIABLES, OUTPUTS, README]).lower()
    for needle in ("password=", "postgresql://", "aws_secret_access_key", "authorization:", "bearer "):
        assert needle not in haystack, f"sensitive literal {needle!r} must not appear"
