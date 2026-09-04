"""Static Task 9.3 ecs-module configuration tests; no Terraform or AWS access."""

from __future__ import annotations

import re
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
MAIN = (MODULE_DIR / "main.tf").read_text(encoding="utf-8")
VARIABLES = (MODULE_DIR / "variables.tf").read_text(encoding="utf-8")
OUTPUTS = (MODULE_DIR / "outputs.tf").read_text(encoding="utf-8")
README = (MODULE_DIR / "README.md").read_text(encoding="utf-8")


def _resource_block(resource_type: str, resource_name: str) -> str:
    match = re.search(
        rf'resource "{resource_type}" "{resource_name}" \{{(.*?)(?=\nresource |\Z)',
        MAIN,
        re.DOTALL,
    )
    assert match, f"{resource_type}.{resource_name} was not found"
    return match.group(1)


def test_task_definition_uses_fargate_cpu256_mem512() -> None:
    task = _resource_block("aws_ecs_task_definition", "this")
    assert 'requires_compatibilities = ["FARGATE"]' in task
    assert 'network_mode             = "awsvpc"' in task
    assert "cpu                      = tostring(var.cpu)" in task
    assert "memory                   = tostring(var.memory)" in task
    assert "default     = 256" in VARIABLES
    assert "default     = 512" in VARIABLES
    assert "contains([256, 512, 1024], var.cpu)" in VARIABLES
    assert "contains([512, 1024, 2048], var.memory)" in VARIABLES


def test_task_execution_and_task_roles_are_variable_references() -> None:
    task = _resource_block("aws_ecs_task_definition", "this")
    assert "execution_role_arn       = var.task_execution_role_arn" in task
    assert "task_role_arn            = var.task_role_arn" in task


def test_secrets_manager_reference_by_arn_and_no_plaintext_secret() -> None:
    # Secret is injected via the ECS secrets/valueFrom mechanism using the ARN.
    assert "secrets = [" in MAIN
    assert "valueFrom = var.db_secret_arn" in MAIN
    arn_validation = re.search(r'variable "db_secret_arn" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert arn_validation and "arn:aws" in arn_validation.group(1)
    assert "secretsmanager:" in arn_validation.group(1)
    # No plaintext secret material anywhere in the module sources or README.
    corpus = (MAIN + VARIABLES + OUTPUTS + README).lower()
    for forbidden in ("password=", "postgresql://", "bearer ", "authorization:", "secret_value", "master_password"):
        assert forbidden not in corpus


def test_service_desired_count_one_in_private_subnets_without_public_ip() -> None:
    service = _resource_block("aws_ecs_service", "this")
    assert "desired_count   = var.desired_count" in service
    assert "subnets          = var.private_subnet_ids" in service
    assert "security_groups  = [var.ecs_security_group_id]" in service
    assert "assign_public_ip = var.assign_public_ip" in service
    assert 'launch_type     = "FARGATE"' in service
    desired = re.search(r'variable "desired_count" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert desired and "default     = 1" in desired.group(1)
    public_ip = re.search(r'variable "assign_public_ip" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert public_ip and "default     = false" in public_ip.group(1)


def test_awslogs_driver_configured() -> None:
    assert 'logDriver = "awslogs"' in MAIN
    assert 'resource "aws_cloudwatch_log_group" "this"' in MAIN


def test_autoscaling_is_count_toggled_and_disabled_by_default() -> None:
    target = _resource_block("aws_appautoscaling_target", "this")
    assert "count = var.enable_autoscaling ? 1 : 0" in target
    policy = _resource_block("aws_appautoscaling_policy", "cpu")
    assert "count = var.enable_autoscaling ? 1 : 0" in policy
    flag = re.search(r'variable "enable_autoscaling" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert flag and "default     = false" in flag.group(1)


def test_name_prefix_and_common_tags_are_used() -> None:
    assert "var.name_prefix" in MAIN
    assert "merge(var.common_tags" in MAIN


def test_outputs_expose_ids_and_no_secret() -> None:
    for output in ("cluster_arn", "service_name", "task_definition_arn", "log_group_name"):
        assert f'output "{output}"' in OUTPUTS
