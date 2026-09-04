variable "name_prefix" {
  description = "Prefix for ECR repository names, for example ops-platform-dev."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]+(-[a-z0-9]+)*$", var.name_prefix)) && length(var.name_prefix) <= 200
    error_message = "name_prefix must use lowercase alphanumeric segments separated by single hyphens and be at most 200 characters."
  }
}

variable "common_tags" {
  description = "Common identity tags applied to each ECR repository."
  type        = map(string)

  validation {
    condition = alltrue([
      for key, value in var.common_tags : length(trimspace(key)) > 0 && length(trimspace(value)) > 0
    ])
    error_message = "common_tags must have non-empty keys and values."
  }
}

variable "repository_components" {
  description = "Exactly the four container components owned by the MVP."
  type        = set(string)
  default = [
    "backend-api",
    "alarm-event-processor",
    "security-finding-worker",
    "monthly-summary-cronjob",
  ]

  validation {
    condition = length(var.repository_components) == 4 && alltrue([
      for component in ["backend-api", "alarm-event-processor", "security-finding-worker", "monthly-summary-cronjob"] : contains(var.repository_components, component)
    ])
    error_message = "repository_components must contain exactly backend-api, alarm-event-processor, security-finding-worker, and monthly-summary-cronjob."
  }

  validation {
    condition = alltrue([
      for component in var.repository_components : can(regex("^[a-z0-9]+(?:[._-][a-z0-9]+)*$", component)) && length("${var.name_prefix}-${component}") <= 256
    ])
    error_message = "Each complete ECR repository name must be lowercase and satisfy the ECR 256-character repository naming limit."
  }
}

variable "image_tag_mutability" {
  description = "ECR image tag mutability. IMMUTABLE is the safe MVP default."
  type        = string
  default     = "IMMUTABLE"

  validation {
    condition     = contains(["IMMUTABLE", "MUTABLE"], var.image_tag_mutability)
    error_message = "image_tag_mutability must be IMMUTABLE or MUTABLE."
  }
}

variable "untagged_image_expiration_days" {
  description = "Days to retain untagged images before lifecycle cleanup."
  type        = number
  default     = 7

  validation {
    condition     = var.untagged_image_expiration_days >= 1 && var.untagged_image_expiration_days <= 365
    error_message = "untagged_image_expiration_days must be between 1 and 365."
  }
}

variable "tagged_image_retention_count" {
  description = "Maximum number of tagged release images to retain for each repository."
  type        = number
  default     = 10

  validation {
    condition     = var.tagged_image_retention_count >= 1 && var.tagged_image_retention_count <= 1000
    error_message = "tagged_image_retention_count must be between 1 and 1000."
  }
}

variable "retained_tag_prefixes" {
  description = "Tag prefixes covered by the tagged-image lifecycle retention rule."
  type        = list(string)
  default     = ["v", "release", "sha"]

  validation {
    condition     = length(var.retained_tag_prefixes) > 0 && alltrue([for prefix in var.retained_tag_prefixes : can(regex("^[A-Za-z0-9][A-Za-z0-9._-]*$", prefix))])
    error_message = "retained_tag_prefixes must contain non-empty Docker tag prefixes."
  }
}
