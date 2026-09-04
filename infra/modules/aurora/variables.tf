variable "name_prefix" {
  description = "Prefix for Aurora resource names, for example ops-platform-dev."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]+(-[a-z0-9]+)*$", var.name_prefix)) && length(var.name_prefix) <= 45
    error_message = "name_prefix must use lowercase alphanumeric segments separated by single hyphens and be at most 45 characters."
  }
}

variable "common_tags" {
  description = "Common identity tags applied to every taggable Aurora resource."
  type        = map(string)

  validation {
    condition = alltrue([
      for key, value in var.common_tags : length(trimspace(key)) > 0 && length(trimspace(value)) > 0
    ])
    error_message = "common_tags must have non-empty keys and values."
  }
}

variable "database_subnet_ids" {
  description = "IDs of isolated database subnets supplied by the network module; Aurora requires subnets in at least two AZs."
  type        = list(string)

  validation {
    condition     = length(var.database_subnet_ids) >= 2 && length(distinct(var.database_subnet_ids)) == length(var.database_subnet_ids) && alltrue([for subnet_id in var.database_subnet_ids : length(trimspace(subnet_id)) > 0])
    error_message = "database_subnet_ids must contain at least two distinct non-empty isolated database subnet IDs."
  }
}

variable "db_security_group_id" {
  description = "The database security group ID from the network module. It is the only security group attached to the cluster."
  type        = string

  validation {
    condition     = length(trimspace(var.db_security_group_id)) > 0
    error_message = "db_security_group_id must be a non-empty security group ID."
  }
}

variable "database_name" {
  description = "Initial non-sensitive PostgreSQL database name. Schema and migrations are intentionally outside Task 6.1."
  type        = string
  default     = "opsplatform"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{0,62}$", var.database_name))
    error_message = "database_name must start with a lowercase letter and contain only lowercase letters or digits, up to 63 characters."
  }
}

variable "engine_version" {
  description = "Aurora PostgreSQL engine version. The dev default is a PostgreSQL 16 minor version; select a supported Aurora PostgreSQL Serverless v2 version in the target Region before apply. This module accepts Aurora PostgreSQL major versions 14 through 16."
  type        = string
  default     = "16.6"

  validation {
    condition     = can(regex("^1[4-6]\\.[0-9]+(\\.[0-9]+)?$", var.engine_version))
    error_message = "engine_version must be an Aurora PostgreSQL 14.x, 15.x, or 16.x version supported for Serverless v2 in the deployment Region."
  }
}

variable "master_username" {
  description = "Non-sensitive Aurora master username. The password is generated and managed by RDS in Secrets Manager."
  type        = string
  default     = "ops_admin"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{0,15}$", var.master_username))
    error_message = "master_username must start with a lowercase letter and contain only lowercase letters, digits, or underscores (1-16 characters)."
  }
}

variable "master_user_secret_kms_key_id" {
  description = "Optional customer-managed KMS key ARN for the RDS-managed master secret. Null uses the AWS managed Secrets Manager key."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.master_user_secret_kms_key_id == null || can(regex("^arn:aws(-[a-z]+)?:kms:", var.master_user_secret_kms_key_id))
    error_message = "master_user_secret_kms_key_id must be null or a KMS key ARN."
  }
}

variable "min_capacity" {
  description = "Minimum Aurora Serverless v2 capacity in ACUs. The dev/MVP default is 0.5 ACU."
  type        = number
  default     = 0.5

  validation {
    condition     = var.min_capacity >= 0.5
    error_message = "min_capacity must be at least 0.5 ACU."
  }
}

variable "max_capacity" {
  description = "Maximum Aurora Serverless v2 capacity in ACUs. The dev/MVP default is 2 ACUs."
  type        = number
  default     = 2

  validation {
    condition     = var.max_capacity >= var.min_capacity && var.max_capacity <= 128
    error_message = "max_capacity must be at least min_capacity and no more than 128 ACUs."
  }
}

variable "backup_retention_period" {
  description = "Automated backup retention in days. One day is the dev default; production should use a reviewed retention period."
  type        = number
  default     = 1

  validation {
    condition     = var.backup_retention_period >= 1 && var.backup_retention_period <= 35
    error_message = "backup_retention_period must be between 1 and 35 days."
  }
}

variable "enabled_cloudwatch_logs_exports" {
  description = "Aurora PostgreSQL log exports. PostgreSQL logs are enabled by default for dev observability and may create CloudWatch Logs cost."
  type        = set(string)
  default     = ["postgresql"]

  validation {
    condition     = length(setsubtract(var.enabled_cloudwatch_logs_exports, toset(["postgresql"]))) == 0
    error_message = "Aurora PostgreSQL supports only the postgresql CloudWatch log export in this module."
  }
}

variable "performance_insights_enabled" {
  description = "Enable Performance Insights. Disabled by default for dev cost control; enable after production retention and cost review."
  type        = bool
  default     = false
}

variable "deletion_protection" {
  description = "Prevent cluster deletion. Disabled by default only for the dev MVP; production should enable it."
  type        = bool
  default     = false
}

variable "skip_final_snapshot" {
  description = "Whether Terraform destroy skips the final cluster snapshot. Defaults to false to preserve a final snapshot; review this deliberately before apply or destroy."
  type        = bool
  default     = false
}

variable "final_snapshot_identifier" {
  description = "Optional final snapshot identifier when skip_final_snapshot is false. Null derives a name from name_prefix; provide a unique reviewed value for repeated lifecycle operations."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.final_snapshot_identifier == null || can(regex("^[a-z][a-z0-9-]{0,62}$", var.final_snapshot_identifier))
    error_message = "final_snapshot_identifier must be null or a lowercase RDS snapshot identifier beginning with a letter and at most 63 characters."
  }
}
