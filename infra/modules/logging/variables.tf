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

variable "vpc_id" {
  description = "VPC whose traffic is captured by the flow log. Required; supplied by the network module output via the dev root in Task 27."
  type        = string

  validation {
    condition     = can(regex("^vpc-[0-9a-f]+$", var.vpc_id))
    error_message = "vpc_id must be a valid vpc-<hex> identifier."
  }
}

# CloudWatch Logs only accepts specific discrete retention values. Within the
# required 14-30 day range the supported values are 14 and 30.
variable "retention_in_days" {
  description = "CloudWatch Logs retention in days for the VPC Flow Logs group this module owns. Must be 14 or 30."
  type        = number
  default     = 30

  validation {
    condition     = contains([14, 30], var.retention_in_days)
    error_message = "retention_in_days must be 14 or 30: the CloudWatch Logs-supported values within the required 14-30 day retention range."
  }
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

# NOTE ON OWNERSHIP (single owner per log group):
#   - ECS Backend log group (/ecs/<name_prefix>-backend-api) -> ecs module
#   - EKS worker log group                                   -> eks module
#   - Portal Lambda log group (/aws/lambda/<name_prefix>-portal-api) -> lambda module
#   - VPC Flow Logs log group (/vpc/<name_prefix>-flowlogs)  -> THIS module
# This module creates ONLY the VPC Flow Logs group. See README.md.
