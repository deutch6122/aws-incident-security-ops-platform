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
    assert "cpu                      = tostring(var.ecs_task_cpu)" in task
    assert "memory                   = tostring(var.ecs_task_memory)" in task
    assert "default     = 256" in VARIABLES
    assert "default     = 512" in VARIABLES
    assert "contains([256, 512, 1024], var.ecs_task_cpu)" in VARIABLES
    assert "contains([512, 1024, 2048], var.ecs_task_memory)" in VARIABLES


def test_task_execution_and_task_roles_are_variable_references() -> None:
    task = _resource_block("aws_ecs_task_definition", "this")
    assert "execution_role_arn       = var.backend_execution_role_arn" in task
    assert "task_role_arn            = var.backend_task_role_arn" in task


def test_db_secret_arn_is_plain_environment_and_bearer_uses_secrets() -> None:
    assert 'name  = "BACKEND_DB_SECRET_ARN"' in MAIN
    assert "value = var.backend_db_secret_arn" in MAIN
    assert 'name  = "BACKEND_DB_HOST"' in MAIN
    assert "value = var.backend_db_host" in MAIN
    assert 'name  = "BACKEND_DB_PORT"' in MAIN
    assert "value = tostring(var.backend_db_port)" in MAIN
    assert 'name  = "BACKEND_DB_NAME"' in MAIN
    assert "value = var.backend_db_name" in MAIN
    assert "secrets = [" in MAIN
    assert 'name      = "BACKEND_INTERNAL_BEARER_TOKEN"' in MAIN
    assert "valueFrom = var.backend_bearer_secret_arn" in MAIN
    assert "valueFrom = var.backend_db_secret_arn" not in MAIN
    arn_validation = re.search(r'variable "backend_db_secret_arn" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert arn_validation and "arn:aws" in arn_validation.group(1)
    assert "secretsmanager:" in arn_validation.group(1)
    # No plaintext secret material anywhere in the module sources or README.
    corpus = (MAIN + VARIABLES + OUTPUTS + README).lower()
    for forbidden in (
        "password=",
        "postgresql://",
        "authorization: bearer ",
        "secret_value =",
        "master_password =",
    ):
        assert forbidden not in corpus


def test_service_allows_zero_tasks_in_private_subnets_without_public_ip() -> None:
    service = _resource_block("aws_ecs_service", "this")
    assert "desired_count   = var.ecs_desired_count" in service
    assert "subnets          = var.private_subnet_ids" in service
    assert "security_groups  = [var.ecs_security_group_id]" in service
    assert "assign_public_ip = false" in service
    assert 'launch_type     = "FARGATE"' in service
    desired = re.search(r'variable "ecs_desired_count" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert desired and "default     = 0" in desired.group(1)
    assert ">= 0" in desired.group(1)
    assert "ignore_changes = [desired_count]" not in MAIN


def test_awslogs_driver_configured() -> None:
    assert 'logDriver = "awslogs"' in MAIN
    assert 'resource "aws_cloudwatch_log_group" "this"' in MAIN


def test_migration_has_dedicated_task_roles_image_and_log_group() -> None:
    task = _resource_block("aws_ecs_task_definition", "migration")
    assert "var.migration_container_image" in MAIN
    assert "execution_role_arn       = var.migration_execution_role_arn" in task
    assert "task_role_arn            = var.migration_task_role_arn" in task
    assert 'resource "aws_cloudwatch_log_group" "migration"' in MAIN
    assert 'name              = "/ecs/${var.name_prefix}-migration"' in MAIN
    assert "BACKEND_INTERNAL_BEARER_TOKEN" not in str(
        re.search(r"migration_container_definitions\s*=\s*\[(.*?)\n  \]", MAIN, re.DOTALL).group(1)
    )


def test_migration_receives_db_arn_and_fallback_name_without_secret_payload() -> None:
    match = re.search(r"migration_container_definitions\s*=\s*\[(.*?)\n  \]", MAIN, re.DOTALL)
    assert match
    block = match.group(1)
    assert 'name  = "BACKEND_DB_SECRET_ARN"' in block
    assert "value = var.backend_db_secret_arn" in block
    assert 'name  = "BACKEND_DB_HOST"' in block
    assert "value = var.backend_db_host" in block
    assert 'name  = "BACKEND_DB_PORT"' in block
    assert "value = tostring(var.backend_db_port)" in block
    assert 'name  = "BACKEND_DB_NAME"' in block
    assert "value = var.backend_db_name" in block
    assert "secrets =" not in block


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


def test_outputs_expose_ids_and_no_secret_or_log_group() -> None:
    for output in (
        "cluster_arn",
        "cluster_name",
        "service_name",
        "task_definition_arn",
        "migration_cluster_arn",
        "migration_task_definition_arn",
    ):
        assert f'output "{output}"' in OUTPUTS
    assert 'output "log_group_name"' not in OUTPUTS
