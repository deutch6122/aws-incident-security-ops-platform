variable "name_prefix" {
  description = "Prefix for CloudFront/WAF resource names, for example ops-platform-dev."
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

# Regional domain name of the Portal_Storage S3 bucket (from the s3-portal
# module's bucket_regional_domain_name output). Used as the S3 origin domain.
variable "s3_origin_domain_name" {
  description = "Regional domain name of the Portal_Storage S3 bucket, used as the S3 (OAC) origin."
  type        = string

  validation {
    condition     = length(trimspace(var.s3_origin_domain_name)) > 0
    error_message = "s3_origin_domain_name must be set to the Portal_Storage bucket regional domain name."
  }
}

# API Gateway origin domain for the /api/* behavior. Task 14 finalises the API
# Gateway; until then the dev root passes the apigateway module output. The
# default is an empty placeholder for validation only - no real domain is
# committed.
variable "api_gateway_origin_domain" {
  description = "Domain name of the API Gateway custom origin serving /api/*. Placeholder empty string until wired to the apigateway module (Task 14)."
  type        = string
  default     = ""
}

variable "price_class" {
  description = "CloudFront price class. Defaults to PriceClass_200 (Requirement 24.6). PriceClass_100 is the cheaper alternative."
  type        = string
  default     = "PriceClass_200"

  validation {
    condition     = contains(["PriceClass_100", "PriceClass_200", "PriceClass_All"], var.price_class)
    error_message = "price_class must be PriceClass_100, PriceClass_200, or PriceClass_All."
  }
}

variable "waf_rate_limit" {
  description = "Requests per 5-minute window per source IP before the WAF rate-based rule blocks (Requirement 13.3)."
  type        = number
  default     = 2000

  validation {
    condition     = var.waf_rate_limit >= 100 && var.waf_rate_limit <= 2000000000
    error_message = "waf_rate_limit must be between 100 and 2000000000 (AWS WAFv2 limits)."
  }
}
