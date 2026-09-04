variable "name_prefix" {
  description = "Prefix for logging resource names, for example ops-platform-dev."
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

# Task 11.2 requires 14-30 day retention, but CloudWatch Logs only accepts
# specific discrete values (a value like 21 would fail at apply time). Within
# the required 14-30 day range the CloudWatch Logs-supported values are 14 and
# 30, so this validation allows only those two.
variable "retention_in_days" {
  description = "CloudWatch Logs retention in days for the log groups this module owns. Must be 14 or 30 (the CloudWatch Logs-supported values within the required 14-30 day range)."
  type        = number
  default     = 30

  validation {
    condition     = contains([14, 30], var.retention_in_days)
    error_message = "retention_in_days must be 14 or 30: the CloudWatch Logs-supported values within the required 14-30 day retention range."
  }
}

# The Portal API Lambda log group is created here because no other module owns
# it yet (the Lambda module is Task 15). Toggle off if the lambda module later
# takes ownership.
variable "enable_lambda_log_group" {
  description = "Whether to create the Portal Lambda CloudWatch Logs group (/aws/lambda/<name_prefix>-portal)."
  type        = bool
  default     = true
}

variable "lambda_log_group_name" {
  description = "Override name for the Portal Lambda log group. Defaults to /aws/lambda/<name_prefix>-portal."
  type        = string
  default     = null

  validation {
    condition     = var.lambda_log_group_name == null || can(regex("^/[A-Za-z0-9._/-]+$", var.lambda_log_group_name))
    error_message = "lambda_log_group_name must be null or a valid CloudWatch Logs group path beginning with a slash."
  }
}

variable "enable_vpc_flowlogs_log_group" {
  description = "Whether to create the VPC Flow Logs CloudWatch Logs group (/vpc/<name_prefix>-flowlogs)."
  type        = bool
  default     = true
}

variable "vpc_flowlogs_log_group_name" {
  description = "Override name for the VPC Flow Logs log group. Defaults to /vpc/<name_prefix>-flowlogs."
  type        = string
  default     = null

  validation {
    condition     = var.vpc_flowlogs_log_group_name == null || can(regex("^/[A-Za-z0-9._/-]+$", var.vpc_flowlogs_log_group_name))
    error_message = "vpc_flowlogs_log_group_name must be null or a valid CloudWatch Logs group path beginning with a slash."
  }
}

# NOTE ON OWNERSHIP: the ECS backend-api log group (/ecs/<name_prefix>-backend-api)
# is owned by the ecs module (Task 9) and the EKS worker log group
# (/<name_prefix>/eks/workers) is owned by the eks module (Task 10). This module
# never creates those groups. Their retention is set through each owning
# module's own log_retention_days variable. See README.md for the ownership
# table.
