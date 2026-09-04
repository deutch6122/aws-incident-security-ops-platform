variable "name_prefix" {
  description = "Prefix for DynamoDB table names, for example ops-platform-dev."
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

# Attribute name used as the TTL timestamp on page_view_logs and
# maintenance_windows. Items whose value is a Unix epoch (seconds) in the past
# are eligible for automatic deletion. Kept as a variable so the Portal_API /
# A->B integration (Task 15/16) and this module agree on one attribute name.
variable "ttl_attribute_name" {
  description = "Attribute name holding the Unix-epoch (seconds) TTL timestamp on the TTL-enabled tables."
  type        = string
  default     = "expires_at"

  validation {
    condition     = can(regex("^[A-Za-z][A-Za-z0-9_]*$", var.ttl_attribute_name))
    error_message = "ttl_attribute_name must start with a letter and contain only letters, digits, or underscores."
  }
}
