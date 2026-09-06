variable "name_prefix" {
  description = "Prefix for WAF resources, for example ops-platform-dev."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]+(-[a-z0-9]+)*$", var.name_prefix)) && length(var.name_prefix) <= 50
    error_message = "name_prefix must use lowercase alphanumeric segments separated by single hyphens and be at most 50 characters."
  }
}

variable "common_tags" {
  description = "Common identity tags applied to every taggable resource."
  type        = map(string)
  default     = {}

  validation {
    condition = alltrue([
      for key, value in var.common_tags : length(trimspace(key)) > 0 && length(trimspace(value)) > 0
    ])
    error_message = "common_tags must have non-empty keys and values."
  }
}

variable "waf_additional_managed_rule_groups" {
  description = "Additional AWS or Marketplace managed rule groups. Priorities must be unique and must not use priority 10."
  type = list(object({
    name        = string
    vendor_name = string
    priority    = number
  }))
  default = []

  validation {
    condition = (
      length(distinct([for group in var.waf_additional_managed_rule_groups : group.priority])) == length(var.waf_additional_managed_rule_groups) &&
      alltrue([for group in var.waf_additional_managed_rule_groups : group.priority >= 0 && group.priority != 10])
    )
    error_message = "Additional managed rule group priorities must be unique non-negative values and must not use priority 10."
  }
}

variable "waf_logging_enabled" {
  description = "Enable WAF logging to an encrypted CloudWatch Logs log group."
  type        = bool
  default     = true
}

variable "waf_kms_enabled" {
  description = "Encrypt WAF CloudWatch Logs with a customer-managed KMS key when logging is enabled."
  type        = bool
  default     = true
}

variable "waf_log_retention_days" {
  description = "Retention in days for WAF logs."
  type        = number
  default     = 30

  validation {
    condition     = contains([14, 30, 60, 90, 120, 180, 365], var.waf_log_retention_days)
    error_message = "waf_log_retention_days must be one of 14, 30, 60, 90, 120, 180, or 365."
  }
}
