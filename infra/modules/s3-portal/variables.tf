variable "name_prefix" {
  description = "Prefix for Portal_Storage resource names, for example ops-platform-dev."
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

# Region used as part of the deterministic bucket-name suffix
# "<account-id>-<region>". The account id is read from a data source (never
# committed as a literal). A real region string is not sensitive.
variable "aws_region" {
  description = "AWS region used to build the deterministic bucket-name suffix <account-id>-<region>."
  type        = string

  validation {
    condition     = length(trimspace(var.aws_region)) > 0
    error_message = "aws_region must be a non-empty string."
  }
}

# Object key prefix under which Product_A places monthly report files via the
# A->B link (Cronjob_Summary, Task 16.2). Kept as a variable so this module,
# the cloudfront cache behavior, and the integration job agree on one prefix.
variable "reports_prefix" {
  description = "S3 key prefix for monthly report files placed by the A->B link (Cronjob_Summary)."
  type        = string
  default     = "reports/"

  validation {
    condition     = can(regex("^[A-Za-z0-9._/-]+/$", var.reports_prefix))
    error_message = "reports_prefix must be a slash-terminated key prefix such as reports/."
  }
}

variable "force_destroy" {
  description = "Whether to allow Terraform to delete a non-empty bucket on destroy (dev convenience)."
  type        = bool
  default     = false
}
