"""Static messaging-module configuration tests (Task 8, 2 systems); no Terraform or AWS access."""

from __future__ import annotations

import re
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
MAIN = (MODULE_DIR / "main.tf").read_text(encoding="utf-8")
VARIABLES = (MODULE_DIR / "variables.tf").read_text(encoding="utf-8")
OUTPUTS = (MODULE_DIR / "outputs.tf").read_text(encoding="utf-8")
VERSIONS = (MODULE_DIR / "versions.tf").read_text(encoding="utf-8")
README = (MODULE_DIR / "README.md").read_text(encoding="utf-8")


def _block(resource_type: str, resource_name: str, kind: str = "resource") -> str:
    match = re.search(
        rf'{kind} "{resource_type}" "{resource_name}" \{{(.*?)(?=\n{kind} |\ndata |\nresource |\Z)',
        MAIN,
        re.DOTALL,
    )
    assert match, f"{kind} {resource_type}.{resource_name} was not found"
    return match.group(1)


def test_versions_pin_terraform_and_aws_provider() -> None:
    assert 'required_version = ">= 1.10"' in VERSIONS
    assert 'version = "~> 5.0"' in VERSIONS


def test_two_systems_map_drives_for_each() -> None:
    # A single local.systems map with exactly the alarm and finding systems.
    systems = re.search(r"systems = \{(.*?)\n  \}", MAIN, re.DOTALL)
    assert systems, "local.systems map missing"
    body = systems.group(1)
    assert "alarm = {" in body
    assert "finding = {" in body
    # Every resource is driven by for_each = local.systems (no duplication).
    for res in (
        'resource "aws_sqs_queue" "main"',
        'resource "aws_sqs_queue" "dlq"',
        'resource "aws_sqs_queue_redrive_allow_policy" "dlq"',
        'resource "aws_cloudwatch_event_rule" "this"',
        'resource "aws_cloudwatch_event_target" "this"',
        'resource "aws_sqs_queue_policy" "this"',
        'data "aws_iam_policy_document" "queue_policy"',
    ):
        assert res in MAIN, f"{res} missing"
    assert MAIN.count("for_each = local.systems") == 7


def test_rule_queue_dlq_are_two_each_via_for_each() -> None:
    # Exactly one main queue, one DLQ, one rule resource block, each expanded to
    # two instances by for_each over the two-entry systems map.
    assert MAIN.count('resource "aws_sqs_queue" "main"') == 1
    assert MAIN.count('resource "aws_sqs_queue" "dlq"') == 1
    assert MAIN.count('resource "aws_cloudwatch_event_rule" "this"') == 1
    systems = re.search(r"systems = \{(.*?)\n  \}", MAIN, re.DOTALL).group(1)
    assert systems.count(" = {") == 2, "systems map must have exactly two entries"


def test_alarm_and_finding_detail_types_differ() -> None:
    alarm = re.search(r'variable "alarm_event_detail_types" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    finding = re.search(r'variable "finding_event_detail_types" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert alarm and finding
    assert '["AlarmEvent"]' in alarm.group(1)
    assert '["SecurityFinding"]' in finding.group(1)
    assert "AlarmEvent" not in finding.group(1)
    assert "SecurityFinding" not in alarm.group(1)


def test_detail_types_reject_empty() -> None:
    for name in ("alarm_event_detail_types", "finding_event_detail_types"):
        block = re.search(rf'variable "{name}" \{{(.*?)\n\}}', VARIABLES, re.DOTALL).group(1)
        assert "length(" in block and "> 0" in block, f"{name} must reject empty set"
        assert "trimspace(dt)" in block, f"{name} must reject empty strings"


def test_event_source_matches_seed_script() -> None:
    src = re.search(r'variable "event_source" \{(.*?)\n\}', VARIABLES, re.DOTALL).group(1)
    assert 'default     = "ops-platform.sample"' in src
    rule = _block("aws_cloudwatch_event_rule", "this")
    assert "source        = [var.event_source]" in rule
    assert '"detail-type" = each.value.detail_types' in rule


def test_each_target_references_only_its_own_queue() -> None:
    target = _block("aws_cloudwatch_event_target", "this")
    assert "rule      = aws_cloudwatch_event_rule.this[each.key].name" in target
    assert "arn       = aws_sqs_queue.main[each.key].arn" in target


def test_main_queue_is_standard_with_redrive_to_own_dlq() -> None:
    main_queue = _block("aws_sqs_queue", "main")
    assert "fifo_queue" not in main_queue
    assert "redrive_policy" in main_queue
    assert "maxReceiveCount" in main_queue
    assert "var.sqs_max_receive_count" in main_queue
    assert "aws_sqs_queue.dlq[each.key].arn" in main_queue


def test_no_fifo_anywhere() -> None:
    assert "fifo_queue" not in MAIN
    assert ".fifo" not in MAIN
    assert "content_based_deduplication" not in MAIN


def test_all_queues_and_dlqs_enable_sqs_managed_sse() -> None:
    dlq = _block("aws_sqs_queue", "dlq")
    main_queue = _block("aws_sqs_queue", "main")
    assert "sqs_managed_sse_enabled   = var.sqs_managed_sse" in dlq
    assert "sqs_managed_sse_enabled    = var.sqs_managed_sse" in main_queue
    sse_var = re.search(r'variable "sqs_managed_sse" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert sse_var and "default     = true" in sse_var.group(1)


def test_each_dlq_redrive_allow_limits_to_own_main_queue() -> None:
    allow = _block("aws_sqs_queue_redrive_allow_policy", "dlq")
    assert "byQueue" in allow
    assert "aws_sqs_queue.main[each.key].arn" in allow


def test_each_queue_policy_allows_only_eventbridge_and_own_rule() -> None:
    policy_doc = _block("aws_iam_policy_document", "queue_policy", kind="data")
    assert "events.amazonaws.com" in policy_doc
    assert "sqs:SendMessage" in policy_doc
    assert "aws:SourceArn" in policy_doc
    assert "aws_cloudwatch_event_rule.this[each.key].arn" in policy_doc
    assert "aws_sqs_queue.main[each.key].arn" in policy_doc
    queue_policy = _block("aws_sqs_queue_policy", "this")
    assert "data.aws_iam_policy_document.queue_policy[each.key].json" in queue_policy


def test_sqs_max_receive_count_default_is_five() -> None:
    mr = re.search(r'variable "sqs_max_receive_count" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert mr and "default     = 5" in mr.group(1)
    # The retired single-system input name must be gone.
    assert 'variable "max_receive_count"' not in VARIABLES


def test_retired_single_system_interfaces_removed() -> None:
    assert 'variable "queue_name_suffix"' not in VARIABLES
    assert 'variable "eventbridge_event_pattern"' not in VARIABLES
    assert 'variable "max_receive_count"' not in VARIABLES
    for retired in ('output "queue_arn"', 'output "queue_url"', 'output "queue_name"',
                    'output "dlq_arn"', 'output "dlq_url"', 'output "dlq_name"',
                    'output "event_rule_arn"'):
        assert retired not in OUTPUTS, f"retired single-system output {retired!r} must be gone"


def test_outputs_publish_per_system_identifiers() -> None:
    for system in ("alarm", "finding"):
        for kind in ("queue_name", "queue_url", "queue_arn", "dlq_name", "dlq_url",
                     "dlq_arn", "event_rule_arn"):
            assert f'output "{system}_{kind}"' in OUTPUTS, f"output {system}_{kind} missing"


def test_name_prefix_and_common_tags_are_used() -> None:
    assert "var.name_prefix" in MAIN
    assert "merge(var.common_tags" in MAIN


def test_no_sensitive_literals_present() -> None:
    haystack = "\n".join([MAIN, VARIABLES, OUTPUTS, README]).lower()
    for needle in ("password=", "postgresql://", "aws_secret_access_key", "authorization:", "bearer "):
        assert needle not in haystack, f"sensitive literal {needle!r} must not appear"
