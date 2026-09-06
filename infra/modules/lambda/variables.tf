variable "name_prefix" {
  description = "Prefix for Lambda resource names, for example ops-platform-dev."
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

variable "runtime" {
  description = "Lambda runtime for the Portal_API function (Python)."
  type        = string
  default     = "python3.12"

  validation {
    condition     = can(regex("^python3\\.(1[0-3])$", var.runtime))
    error_message = "runtime must be a supported Python 3.x runtime (python3.10 through python3.13)."
  }
}

variable "handler" {
  description = "Lambda handler entrypoint (module.function). The Portal_API code is implemented in Task 15."
  type        = string
  default     = "app.handler.lambda_handler"
}

variable "lambda_package_s3_bucket" {
  description = "Versioned artifact bucket holding the Portal_API deployment package."
  type        = string

  validation {
    condition     = length(trimspace(var.lambda_package_s3_bucket)) > 0
    error_message = "lambda_package_s3_bucket must be a non-empty bucket name."
  }
}

variable "lambda_package_s3_key" {
  description = "Immutable S3 key in the form lambda/<commit-sha>/portal-api.zip."
  type        = string

  validation {
    condition     = can(regex("^lambda/[0-9a-f]{7,64}/portal-api\\.zip$", var.lambda_package_s3_key))
    error_message = "lambda_package_s3_key must match lambda/<7-64 lowercase hex commit-sha>/portal-api.zip."
  }
}

variable "lambda_package_s3_object_version" {
  description = "Version ID of the immutable Lambda package object."
  type        = string

  validation {
    condition     = length(trimspace(var.lambda_package_s3_object_version)) > 0
    error_message = "lambda_package_s3_object_version must be non-empty."
  }
}

variable "lambda_source_code_hash" {
  description = "Base64-encoded SHA-256 digest of the exact package object."
  type        = string
  sensitive   = false

  validation {
    condition     = can(regex("^[A-Za-z0-9+/]{43}=$", var.lambda_source_code_hash))
    error_message = "lambda_source_code_hash must be a base64-encoded SHA-256 digest."
  }
}

variable "memory_size" {
  description = "Memory (MB) allocated to the Portal_API Lambda. Constrained to 256-512 for the MVP."
  type        = number
  default     = 256

  validation {
    condition     = var.memory_size >= 256 && var.memory_size <= 512
    error_message = "memory_size must be between 256 and 512 MB."
  }
}

variable "timeout" {
  description = "Function timeout in seconds."
  type        = number
  default     = 10

  validation {
    condition     = var.timeout >= 1 && var.timeout <= 30
    error_message = "timeout must be between 1 and 30 seconds."
  }
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention (days) for the Lambda log group."
  type        = number
  default     = 14

  validation {
    condition     = contains([14, 30], var.log_retention_days)
    error_message = "log_retention_days must be 14 or 30 (matches the logging module retention policy)."
  }
}

# --- Product_B DynamoDB table ARNs (from the dynamodb module outputs) ---------
# READ scope: public_status_items, report_metadata, maintenance_windows.
# WRITE scope: page_view_logs only. No real ARNs are committed; the dev root
# passes the dynamodb module outputs.
variable "public_status_items_table_arn" {
  description = "ARN of the public_status_items table (read-only for Portal_API)."
  type        = string

  validation {
    condition     = length(trimspace(var.public_status_items_table_arn)) > 0
    error_message = "public_status_items_table_arn must be set."
  }
}

variable "report_metadata_table_arn" {
  description = "ARN of the report_metadata table (read-only for Portal_API)."
  type        = string

  validation {
    condition     = length(trimspace(var.report_metadata_table_arn)) > 0
    error_message = "report_metadata_table_arn must be set."
  }
}

variable "maintenance_windows_table_arn" {
  description = "ARN of the maintenance_windows table (read-only for Portal_API)."
  type        = string

  validation {
    condition     = length(trimspace(var.maintenance_windows_table_arn)) > 0
    error_message = "maintenance_windows_table_arn must be set."
  }
}

variable "page_view_logs_table_arn" {
  description = "ARN of the page_view_logs table (the only table Portal_API may write)."
  type        = string

  validation {
    condition     = length(trimspace(var.page_view_logs_table_arn)) > 0
    error_message = "page_view_logs_table_arn must be set."
  }
}
