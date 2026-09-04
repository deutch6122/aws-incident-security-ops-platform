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

# ARN of the CloudFront distribution allowed to read this bucket via OAC. The
# bucket policy restricts s3:GetObject to the cloudfront.amazonaws.com service
# principal AND the aws:SourceArn of exactly this distribution, so no other
# CloudFront distribution (and no direct public request) can read objects.
# Real ARNs are never committed; the dev root passes module.cloudfront output
# (Task 13.3) and the default is an empty placeholder for validation only.
variable "cloudfront_distribution_arn" {
  description = "ARN of the CloudFront distribution permitted to read the bucket via OAC. Placeholder empty string until wired to the cloudfront module."
  type        = string
  default     = ""
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
