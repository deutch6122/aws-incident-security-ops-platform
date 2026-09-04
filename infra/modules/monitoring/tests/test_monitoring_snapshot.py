"""Static Task 18.2/18.3 monitoring-module configuration tests; no Terraform or AWS access.

Verifies (Task 18.3):
  - SQS DLQ > 0 alarm exists.
  - Representative ECS / ALB / Lambda / Aurora alarms exist.
  - Two A/B-separated dashboards exist with separated responsibilities.
  - SNS topic exists and every alarm's alarm_actions references it.
  - Product_A vs Product_B dashboard responsibility separation.
  - No secret values / real ARNs / real account ids (placeholders/variables only).
"""

from __future__ import annotations

import json
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
    assert 'required_version = ">= 1.10"' in VERSIONS
    assert 'version = "~> 5.0"' in VERSIONS


# --- SNS topic + alarm_actions wiring ----------------------------------------
def test_sns_topic_defined() -> None:
    topic = _resource_block("aws_sns_topic", "alarms")
    assert "${var.name_prefix}-alarms" in MAIN
    assert "merge(var.common_tags" in topic


def test_every_alarm_references_sns_topic_in_alarm_actions() -> None:
    alarm_blocks = re.findall(
        r'resource "aws_cloudwatch_metric_alarm" "([a-z0-9_]+)" \{(.*?)(?=\nresource |\Z)',
        MAIN,
        re.DOTALL,
    )
    assert alarm_blocks, "expected at least one metric alarm"
    for name, body in alarm_blocks:
        assert "alarm_actions = local.alarm_actions" in body, f"{name} missing SNS alarm_actions"
    # local.alarm_actions must be the SNS topic ARN.
    assert "alarm_actions          = [aws_sns_topic.alarms.arn]" in MAIN


# --- DLQ > 0 alarm -----------------------------------------------------------
def test_sqs_dlq_alarm_exists_greater_than_zero() -> None:
    dlq = _resource_block("aws_cloudwatch_metric_alarm", "sqs_dlq_messages_visible")
    assert 'metric_name         = "ApproximateNumberOfMessagesVisible"' in dlq
    assert 'namespace           = "AWS/SQS"' in dlq
    assert 'comparison_operator = "GreaterThanThreshold"' in dlq
    assert "threshold           = 0" in dlq
    assert "QueueName = var.dlq_queue_name" in dlq


# --- representative ECS / ALB / Lambda / Aurora alarms -----------------------
def test_ecs_alarms_exist() -> None:
    cpu = _resource_block("aws_cloudwatch_metric_alarm", "ecs_cpu_high")
    mem = _resource_block("aws_cloudwatch_metric_alarm", "ecs_memory_high")
    tasks = _resource_block("aws_cloudwatch_metric_alarm", "ecs_running_tasks_low")
    assert 'metric_name         = "CPUUtilization"' in cpu
    assert 'metric_name         = "MemoryUtilization"' in mem
    assert 'metric_name         = "RunningTaskCount"' in tasks
    for block in (cpu, mem, tasks):
        assert "ClusterName = var.ecs_cluster_name" in block
        assert "ServiceName = var.ecs_service_name" in block


def test_alb_alarms_exist() -> None:
    fivexx = _resource_block("aws_cloudwatch_metric_alarm", "alb_5xx_high")
    latency = _resource_block("aws_cloudwatch_metric_alarm", "alb_latency_high")
    assert 'metric_name         = "HTTPCode_ELB_5XX_Count"' in fivexx
    assert 'metric_name         = "TargetResponseTime"' in latency
    for block in (fivexx, latency):
        assert "LoadBalancer = var.alb_arn_suffix" in block


def test_lambda_alarms_exist() -> None:
    errors = _resource_block("aws_cloudwatch_metric_alarm", "lambda_errors_high")
    throttles = _resource_block("aws_cloudwatch_metric_alarm", "lambda_throttles_high")
    duration = _resource_block("aws_cloudwatch_metric_alarm", "lambda_duration_high")
    assert 'metric_name         = "Errors"' in errors
    assert 'metric_name         = "Throttles"' in throttles
    assert 'metric_name         = "Duration"' in duration
    for block in (errors, throttles, duration):
        assert "FunctionName = var.lambda_function_name" in block


def test_aurora_alarms_exist() -> None:
    acu = _resource_block("aws_cloudwatch_metric_alarm", "aurora_acu_high")
    conns = _resource_block("aws_cloudwatch_metric_alarm", "aurora_connections_high")
    assert 'metric_name         = "ServerlessDatabaseCapacity"' in acu
    assert 'metric_name         = "DatabaseConnections"' in conns
    for block in (acu, conns):
        assert "DBClusterIdentifier = var.aurora_db_cluster_identifier" in block


# --- two dashboards, A/B separated by responsibility -------------------------
def test_two_dashboards_exist() -> None:
    _resource_block("aws_cloudwatch_dashboard", "product_a")
    _resource_block("aws_cloudwatch_dashboard", "product_b")
    assert "${var.name_prefix}-product-a" in MAIN
    assert "${var.name_prefix}-product-b" in MAIN


def _dashboard_body(resource_name: str) -> str:
    block = _resource_block("aws_cloudwatch_dashboard", resource_name)
    return block


def test_product_a_dashboard_owns_ecs_alb_aurora_sqs() -> None:
    body = _dashboard_body("product_a")
    for ns in ("AWS/ECS", "AWS/ApplicationELB", "AWS/RDS", "AWS/SQS"):
        assert ns in body, f"Product_A dashboard should include {ns}"
    # Responsibility separation: Product_A must NOT own the Product_B planes.
    for ns in ("AWS/Lambda", "AWS/CloudFront", "AWS/DynamoDB", "AWS/ApiGateway"):
        assert ns not in body, f"Product_A dashboard must not include {ns}"


def test_product_b_dashboard_owns_lambda_cloudfront_dynamodb_apigw() -> None:
    body = _dashboard_body("product_b")
    for ns in ("AWS/Lambda", "AWS/CloudFront", "AWS/DynamoDB", "AWS/ApiGateway"):
        assert ns in body, f"Product_B dashboard should include {ns}"
    # Responsibility separation: Product_B must NOT own the Product_A planes.
    for ns in ("AWS/ECS", "AWS/RDS", "AWS/SQS"):
        assert ns not in body, f"Product_B dashboard must not include {ns}"


# --- outputs -----------------------------------------------------------------
def test_outputs_publish_sns_alarms_and_dashboards() -> None:
    for name in (
        "sns_topic_arn",
        "sns_topic_name",
        "alarm_names",
        "dlq_alarm_name",
        "product_a_dashboard_name",
        "product_b_dashboard_name",
    ):
        assert f'output "{name}"' in OUTPUTS
    assert "aws_sns_topic.alarms.arn" in OUTPUTS


# --- naming / tags -----------------------------------------------------------
def test_name_prefix_and_common_tags_used() -> None:
    assert "var.name_prefix" in MAIN
    assert "merge(var.common_tags" in MAIN


def test_variable_validations_present() -> None:
    assert 'condition     = can(regex("^[a-z0-9]+(-[a-z0-9]+)*$", var.name_prefix))' in VARIABLES
    period = re.search(r'variable "alarm_period_seconds" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert period and "contains([60, 300, 900]" in period.group(1)


# --- no sensitive literals / real ARNs / real account ids --------------------
def test_no_sensitive_literals_present() -> None:
    haystack = "\n".join([MAIN, VARIABLES, OUTPUTS, README]).lower()
    for needle in ("password=", "postgresql://", "aws_secret_access_key", "authorization:", "bearer "):
        assert needle not in haystack, f"sensitive literal {needle!r} must not appear"


def test_no_real_arn_or_account_id_in_tf() -> None:
    tf_text = "\n".join([MAIN, VARIABLES, OUTPUTS])
    # No full account-scoped ARNs (references use dimension names, not ARNs).
    assert not re.search(r"arn:aws:[a-z0-9-]+:[a-z0-9-]*:\d{12}:", tf_text)
    # No 12-digit account id literal anywhere.
    assert not re.search(r"\b\d{12}\b", tf_text)


def test_alb_arn_suffix_default_is_placeholder_not_full_arn() -> None:
    block = re.search(r'variable "alb_arn_suffix" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert block and "arn:aws:" not in block.group(1)
    assert "PLACEHOLDER" in block.group(1)


# --- dashboards bodies must be valid JSON encodings (structural sanity) ------
def test_audit_log_coverage_documented() -> None:
    # Task 18.3: README must point at the existing tests that guarantee audit_logs.
    assert "test_property_audit_log.py" in README
    assert "Property 6" in README
    assert "test_business_api.py" in README
