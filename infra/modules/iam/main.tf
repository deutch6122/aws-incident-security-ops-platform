# Product_A ECS-family IAM roles (Requirement 2). Every Resource_Level_Action is
# scoped to specific ARNs; the only Resource = "*" statements are the recorded
# Wildcard_Exceptions (see wildcard_exceptions.json / wildcard-exceptions.md),
# each constrained by an aws:RequestedRegion condition.
#
# iam↔ecs decoupling: the Backend/migration CloudWatch Logs log-group ARNs are
# assembled from the partition/account/region/name_prefix here and do NOT depend
# on any ecs module output. The migration-launcher role is created as body+trust
# ONLY; its ecs:RunTask policy is attached by the dev root in Task 27.

data "aws_partition" "current" {}
data "aws_caller_identity" "current" {}

locals {
  partition  = data.aws_partition.current.partition
  account_id = data.aws_caller_identity.current.account_id
  region     = var.aws_region

  role_names = {
    backend_execution   = "${var.name_prefix}-ecs-task-execution-role"
    backend_task        = "${var.name_prefix}-ecs-task-role"
    migration_execution = "${var.name_prefix}-migration-execution-role"
    migration_task      = "${var.name_prefix}-migration-task-role"
    migration_launcher  = "${var.name_prefix}-migration-launcher-role"
  }

  # CloudWatch Logs stream ARNs, assembled without depending on the ecs module.
  # The log groups themselves are created by Terraform before the tasks run.
  backend_log_group        = "/ecs/${var.name_prefix}-backend-api"
  migration_log_group      = "/ecs/${var.name_prefix}-migration"
  backend_log_stream_arn   = "arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:${local.backend_log_group}:log-stream:*"
  migration_log_stream_arn = "arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:${local.migration_log_group}:log-stream:*"
}

# Trust policy shared by the four ECS task roles: assumable only by ECS tasks.
data "aws_iam_policy_document" "ecs_tasks_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# ============================ Backend execution role ==========================
resource "aws_iam_role" "backend_execution" {
  name               = local.role_names.backend_execution
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_trust.json
  tags               = merge(var.common_tags, { Name = local.role_names.backend_execution, Component = "iam", Role = "backend-execution" })
}

data "aws_iam_policy_document" "backend_execution" {
  # ECR image pull, scoped to the specific repository ARNs.
  statement {
    sid    = "EcrPull"
    effect = "Allow"
    actions = [
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:BatchCheckLayerAvailability",
    ]
    resources = [var.backend_ecr_repository_arn]
  }

  # ECR auth token has no resource-level support (Wildcard_Exception), limited by region.
  statement {
    sid       = "EcrAuthToken"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [local.region]
    }
  }

  # CloudWatch Logs write, scoped to the assembled Backend log-group ARN.
  statement {
    sid       = "BackendLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [local.backend_log_stream_arn]
  }

  # Bearer secret injection via the task definition secrets block: only this
  # secret ARN, and only the execution role (not the task role).
  statement {
    sid       = "BearerSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.backend_bearer_secret_arn]
  }
}

resource "aws_iam_role_policy" "backend_execution" {
  name   = "${local.role_names.backend_execution}-policy"
  role   = aws_iam_role.backend_execution.id
  policy = data.aws_iam_policy_document.backend_execution.json
}

# ============================== Backend task role =============================
resource "aws_iam_role" "backend_task" {
  name               = local.role_names.backend_task
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_trust.json
  tags               = merge(var.common_tags, { Name = local.role_names.backend_task, Component = "iam", Role = "backend-task" })
}

data "aws_iam_policy_document" "backend_task" {
  # App fetches the DB secret at runtime: DB secret ARN only. No Bearer secret.
  statement {
    sid       = "DbSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.db_secret_arn]
  }
}

resource "aws_iam_role_policy" "backend_task" {
  name   = "${local.role_names.backend_task}-policy"
  role   = aws_iam_role.backend_task.id
  policy = data.aws_iam_policy_document.backend_task.json
}

# ========================= migration execution role ==========================
resource "aws_iam_role" "migration_execution" {
  name               = local.role_names.migration_execution
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_trust.json
  tags               = merge(var.common_tags, { Name = local.role_names.migration_execution, Component = "iam", Role = "migration-execution" })
}

data "aws_iam_policy_document" "migration_execution" {
  statement {
    sid    = "EcrPull"
    effect = "Allow"
    actions = [
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:BatchCheckLayerAvailability",
    ]
    resources = [var.migration_ecr_repository_arn]
  }

  statement {
    sid       = "EcrAuthToken"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [local.region]
    }
  }

  statement {
    sid       = "MigrationLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [local.migration_log_stream_arn]
  }
}

resource "aws_iam_role_policy" "migration_execution" {
  name   = "${local.role_names.migration_execution}-policy"
  role   = aws_iam_role.migration_execution.id
  policy = data.aws_iam_policy_document.migration_execution.json
}

# ============================ migration task role =============================
resource "aws_iam_role" "migration_task" {
  name               = local.role_names.migration_task
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_trust.json
  tags               = merge(var.common_tags, { Name = local.role_names.migration_task, Component = "iam", Role = "migration-task" })
}

data "aws_iam_policy_document" "migration_task" {
  # Runner fetches the DB secret at runtime: DB secret ARN only. No awslogs
  # (that belongs to the execution role).
  statement {
    sid       = "DbSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.db_secret_arn]
  }
}

resource "aws_iam_role_policy" "migration_task" {
  name   = "${local.role_names.migration_task}-policy"
  role   = aws_iam_role.migration_task.id
  policy = data.aws_iam_policy_document.migration_task.json
}

# ========================= migration-launcher role ===========================
# Body + trust policy ONLY. The ecs:RunTask / iam:PassRole policy is attached by
# the dev root (Task 27) using this role's name and the ecs module's migration
# cluster / task-definition ARNs, so iam does not depend on ecs (no cycle).
data "aws_iam_policy_document" "migration_launcher_trust" {
  # Only assumable by the explicitly supplied Operator principal ARNs. When none
  # are supplied (validation default), the trust policy has no principal and the
  # role is not assumable until the dev root passes the real principal ARNs.
  dynamic "statement" {
    for_each = length(var.migration_launcher_trusted_principal_arns) > 0 ? [1] : []
    content {
      effect  = "Allow"
      actions = ["sts:AssumeRole"]
      principals {
        type        = "AWS"
        identifiers = var.migration_launcher_trusted_principal_arns
      }
    }
  }
}

resource "aws_iam_role" "migration_launcher" {
  name               = local.role_names.migration_launcher
  assume_role_policy = data.aws_iam_policy_document.migration_launcher_trust.json
  tags               = merge(var.common_tags, { Name = local.role_names.migration_launcher, Component = "iam", Role = "migration-launcher" })
}
