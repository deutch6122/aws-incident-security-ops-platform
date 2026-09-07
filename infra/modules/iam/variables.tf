variable "name_prefix" {
  description = "Prefix for IAM role names, for example ops-platform-dev. Shared with bootstrap so the four PassRole target role names match exactly."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]+(-[a-z0-9]+)*$", var.name_prefix)) && length(var.name_prefix) <= 50
    error_message = "name_prefix must use lowercase alphanumeric segments separated by single hyphens and be at most 50 characters."
  }
}

variable "common_tags" {
  description = "Common identity tags applied to every taggable resource in this module."
  type        = map(string)

  validation {
    condition = alltrue([
      for key, value in var.common_tags : length(trimspace(key)) > 0 && length(trimspace(value)) > 0
    ])
    error_message = "common_tags must have non-empty keys and values."
  }
}

variable "aws_region" {
  description = "Region used to build the CloudWatch Logs log-group ARNs and the aws:RequestedRegion condition on wildcard-exception statements. Product_A resources live in ap-northeast-1."
  type        = string
  default     = "ap-northeast-1"

  validation {
    condition     = length(trimspace(var.aws_region)) > 0
    error_message = "aws_region must be a non-empty string."
  }
}

variable "backend_ecr_repository_arn" {
  description = "ARN of the backend-api ECR repository. Only the Backend execution role may pull from it."
  type        = string

  validation {
    condition     = can(regex("^arn:(aws|aws-us-gov|aws-cn):ecr:[a-z0-9-]+:[0-9]{12}:repository/[A-Za-z0-9._/-]+$", var.backend_ecr_repository_arn))
    error_message = "backend_ecr_repository_arn must be a valid ECR repository ARN."
  }
}

variable "migration_ecr_repository_arn" {
  description = "ARN of the db-migration ECR repository. Only the migration execution role may pull from it."
  type        = string

  validation {
    condition     = can(regex("^arn:(aws|aws-us-gov|aws-cn):ecr:[a-z0-9-]+:[0-9]{12}:repository/[A-Za-z0-9._/-]+$", var.migration_ecr_repository_arn))
    error_message = "migration_ecr_repository_arn must be a valid ECR repository ARN."
  }
}

variable "backend_bearer_secret_arn" {
  description = "ARN of the Backend internal Bearer Secret (owned by the dev root). Only the Backend execution role may GetSecretValue on it, to inject it via the task definition secrets block."
  type        = string

  validation {
    condition     = length(trimspace(var.backend_bearer_secret_arn)) > 0
    error_message = "backend_bearer_secret_arn must be a non-empty ARN."
  }
}

variable "db_secret_arn" {
  description = "ARN of the Aurora database credentials secret. The Backend task role and the migration task role may GetSecretValue on it; the Bearer secret is not in scope for them."
  type        = string

  validation {
    condition     = length(trimspace(var.db_secret_arn)) > 0
    error_message = "db_secret_arn must be a non-empty ARN."
  }
}

variable "db_secret_kms_key_arn" {
  description = "ARN of the customer-managed KMS key encrypting the Aurora database secret. DB consumers may decrypt only through Secrets Manager."
  type        = string

  validation {
    condition     = can(regex("^arn:(aws|aws-us-gov|aws-cn):kms:[a-z0-9-]+:[0-9]{12}:key/[A-Za-z0-9-]+$", var.db_secret_kms_key_arn))
    error_message = "db_secret_kms_key_arn must be a valid customer-managed KMS key ARN."
  }
}

variable "migration_launcher_trusted_principal_arns" {
  description = "IAM principal ARNs (Operator principals) permitted to AssumeRole the migration-launcher role. Real ARNs are supplied via the Parameter Sheet; the default is empty so the module validates without committing a real principal."
  type        = list(string)
  default     = []

  validation {
    condition = (
      length(distinct(var.migration_launcher_trusted_principal_arns)) == length(var.migration_launcher_trusted_principal_arns) &&
      alltrue([
        for arn in var.migration_launcher_trusted_principal_arns :
        can(regex("^arn:(aws|aws-us-gov|aws-cn):iam::[0-9]{12}:(role|user)/[A-Za-z0-9+=,.@_/-]+$", arn)) &&
        !strcontains(arn, "*")
      ])
    )
    error_message = "migration_launcher_trusted_principal_arns must contain unique IAM role or user ARNs without wildcards."
  }
}
