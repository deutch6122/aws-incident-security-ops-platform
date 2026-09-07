"""Static iam-module configuration tests (Task 4); no Terraform or AWS access."""

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
WILDCARD_JSON = (MODULE_DIR / "wildcard_exceptions.json").read_text(encoding="utf-8")


def _strip_comments(text: str) -> str:
    return "\n".join(re.sub(r"#.*$", "", line) for line in text.splitlines())


MAIN_CODE = _strip_comments(MAIN)


def _between(text: str, start: str, end: str) -> str:
    """Return a top-level section bounded by two exact Terraform declarations."""
    assert start in text, f"start marker missing: {start}"
    assert end in text, f"end marker missing: {end}"
    return text.split(start, 1)[1].split(end, 1)[0]

ROLE_RESOURCES = (
    "backend_execution",
    "backend_task",
    "migration_execution",
    "migration_task",
    "migration_launcher",
)

ROLE_NAMES = {
    "backend_execution": "${var.name_prefix}-ecs-task-execution-role",
    "backend_task": "${var.name_prefix}-ecs-task-role",
    "migration_execution": "${var.name_prefix}-migration-execution-role",
    "migration_task": "${var.name_prefix}-migration-task-role",
    "migration_launcher": "${var.name_prefix}-migration-launcher-role",
}


def test_versions_pin_terraform_and_aws_provider() -> None:
    assert 'required_version = ">= 1.10"' in VERSIONS
    assert 'version = "~> 5.0"' in VERSIONS


def test_five_roles_defined() -> None:
    for name in ROLE_RESOURCES:
        assert f'resource "aws_iam_role" "{name}"' in MAIN, f"role {name} missing"
    assert MAIN.count('resource "aws_iam_role" "') == 5


def test_deterministic_role_names_present() -> None:
    for value in ROLE_NAMES.values():
        assert value in MAIN, f"deterministic role name {value} missing"


def test_no_wildcard_resource_outside_registry() -> None:
    # ECR authorization is the only action allowed to use Resource = "*".
    # Assert every 'resources = ["*"]' statement is paired with an aws:RequestedRegion
    # condition, and that no other statement uses "*".
    star_statements = re.findall(r'resources\s*=\s*\["\*"\]', MAIN_CODE)
    # There are exactly 2: EcrAuthToken for Backend and migration.
    assert len(star_statements) == 2, f"unexpected number of wildcard resources: {len(star_statements)}"
    # Each wildcard statement must reference RequestedRegion nearby (region-scoped).
    assert MAIN_CODE.count("aws:RequestedRegion") == 2
    assert MAIN_CODE.count('actions   = ["ecr:GetAuthorizationToken"]') == 2
    assert "logs:CreateLogGroup" not in MAIN_CODE


def test_registry_records_only_wildcard_actions() -> None:
    data = json.loads(WILDCARD_JSON)
    actions = {e["action"] for e in data["exceptions"]}
    assert actions == {"ecr:GetAuthorizationToken"}
    for entry in data["exceptions"]:
        assert "aws:RequestedRegion" in entry["conditions"]


def test_resource_level_actions_use_specific_arns() -> None:
    # GetSecretValue must never target "*".
    assert 'actions   = ["secretsmanager:GetSecretValue"]' in MAIN
    # Bearer secret only on the backend execution role.
    assert "var.backend_bearer_secret_arn" in MAIN
    # DB secret referenced (backend task + migration task).
    assert MAIN.count("var.db_secret_arn") >= 2
    # ECR pull is split by workload rather than granting both roles every repo.
    assert "var.ecr_repository_arns" not in MAIN
    assert "var.backend_ecr_repository_arn" in MAIN
    assert "var.migration_ecr_repository_arn" in MAIN


def test_db_consumers_decrypt_only_the_db_secret_kms_key_through_secrets_manager() -> None:
    assert 'variable "db_secret_kms_key_arn"' in VARIABLES
    assert "kms:" in VARIABLES and ":key/" in VARIABLES
    assert MAIN.count('actions   = ["kms:Decrypt"]') == 2
    assert MAIN.count("resources = [var.db_secret_kms_key_arn]") == 2
    assert MAIN.count('variable = "kms:ViaService"') == 2
    assert MAIN.count('values   = ["secretsmanager.${local.region}.amazonaws.com"]') == 2

    backend = _between(
        MAIN_CODE,
        'data "aws_iam_policy_document" "backend_task" {',
        'resource "aws_iam_role_policy" "backend_task" {',
    )
    migration = _between(
        MAIN_CODE,
        'data "aws_iam_policy_document" "migration_task" {',
        'resource "aws_iam_role_policy" "migration_task" {',
    )
    for policy in (backend, migration):
        assert 'actions   = ["kms:Decrypt"]' in policy
        assert "resources = [var.db_secret_kms_key_arn]" in policy
        assert 'variable = "kms:ViaService"' in policy


def test_ecr_pull_is_scoped_to_each_workloads_repository() -> None:
    backend = _between(
        MAIN_CODE,
        'data "aws_iam_policy_document" "backend_execution" {',
        'resource "aws_iam_role_policy" "backend_execution" {',
    )
    migration = _between(
        MAIN_CODE,
        'data "aws_iam_policy_document" "migration_execution" {',
        'resource "aws_iam_role_policy" "migration_execution" {',
    )

    assert "var.backend_ecr_repository_arn" in backend
    assert "var.migration_ecr_repository_arn" not in backend
    assert "var.migration_ecr_repository_arn" in migration
    assert "var.backend_ecr_repository_arn" not in migration
    for action in (
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:BatchCheckLayerAvailability",
    ):
        assert action in backend
        assert action in migration


def test_log_permissions_match_owned_log_groups() -> None:
    assert 'backend_log_group        = "/ecs/${var.name_prefix}-backend-api"' in MAIN
    assert 'migration_log_group      = "/ecs/${var.name_prefix}-migration"' in MAIN
    assert '"/ecs/${var.name_prefix}-backend"' not in MAIN
    assert MAIN.count('actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]') == 2
    assert "logs:CreateLogGroup" not in MAIN
    assert ":log-stream:*" in MAIN


def test_ecr_inputs_and_launcher_principals_are_validated() -> None:
    assert 'variable "backend_ecr_repository_arn"' in VARIABLES
    assert 'variable "migration_ecr_repository_arn"' in VARIABLES
    assert 'variable "ecr_repository_arns"' not in VARIABLES
    assert "length(distinct(var.migration_launcher_trusted_principal_arns))" in VARIABLES
    assert "(role|user)" in VARIABLES
    assert '!strcontains(arn, "*")' in VARIABLES


def test_backend_task_role_has_no_bearer_access() -> None:
    block = re.search(r'data "aws_iam_policy_document" "backend_task" \{(.*?)\n\}\n', MAIN, re.DOTALL)
    assert block
    assert "backend_bearer_secret_arn" not in block.group(1), "backend task role must not access the Bearer secret"


def test_migration_task_role_has_no_logs_permissions() -> None:
    block = re.search(r'data "aws_iam_policy_document" "migration_task" \{(.*?)\n\}\n', MAIN, re.DOTALL)
    assert block
    assert "logs:" not in block.group(1), "migration task role must not have awslogs permissions"


def test_log_group_arns_use_partition_variable_not_hardcoded_aws() -> None:
    assert "data.aws_partition.current.partition" in MAIN
    assert "local.partition" in MAIN
    # No hard-coded arn:aws:logs literal (partition must be interpolated).
    assert not re.search(r"arn:aws:logs:", MAIN), "log group ARNs must not hard-code the aws partition"


def test_does_not_depend_on_ecs_module_outputs() -> None:
    # The iam module must not read ecs module outputs or an injected cluster/task-def ARN.
    lowered = MAIN_CODE.lower()
    for forbidden in ("module.ecs", "cluster_arn", "task_definition_arn", "ecs:runtask"):
        assert forbidden not in lowered, f"iam must not depend on ecs ({forbidden!r})"


def test_migration_launcher_is_body_and_trust_only() -> None:
    # No inline policy / role_policy attaches ecs:RunTask to the launcher here.
    assert 'aws_iam_role_policy" "migration_launcher"' not in MAIN
    assert 'resource "aws_iam_role" "migration_launcher"' in MAIN


def test_trust_policy_is_ecs_tasks_for_task_roles() -> None:
    trust = re.search(r'data "aws_iam_policy_document" "ecs_tasks_trust" \{(.*?)\n\}\n', MAIN, re.DOTALL)
    assert trust
    assert "ecs-tasks.amazonaws.com" in trust.group(1)
    assert '"sts:AssumeRole"' in trust.group(1)


def test_outputs_publish_names_arns_and_passrole_allowlist() -> None:
    for role in ("backend_execution", "backend_task", "migration_execution", "migration_task", "migration_launcher"):
        assert f'output "{role}_role_name"' in OUTPUTS, f"{role}_role_name output missing"
        assert f'output "{role}_role_arn"' in OUTPUTS, f"{role}_role_arn output missing"
    assert 'output "passrole_target_role_arns"' in OUTPUTS
    allow = re.search(r'output "passrole_target_role_arns" \{(.*?)\n\}', OUTPUTS, re.DOTALL).group(1)
    # Exactly the four PassRole targets; the launcher is NOT included.
    assert "backend_execution.arn" in allow
    assert "backend_task.arn" in allow
    assert "migration_execution.arn" in allow
    assert "migration_task.arn" in allow
    assert "migration_launcher" not in allow


def test_no_sensitive_or_real_literals_present() -> None:
    haystack = "\n".join([MAIN, VARIABLES, OUTPUTS, README, WILDCARD_JSON]).lower()
    # Plain sensitive markers (the word "bearer" legitimately appears in prose,
    # so only guard against an actual credential-bearing header value).
    for needle in ("password=", "aws_secret_access_key", "authorization: bearer "):
        assert needle not in haystack, f"sensitive literal {needle!r} must not appear"
    # No literal 12-digit account id.
    assert not re.search(r"\b\d{12}\b", haystack), "no literal 12-digit account id may appear"
