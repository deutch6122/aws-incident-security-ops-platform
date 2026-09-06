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

variable "api_gateway_origin_domain" {
  description = "Domain name of the API Gateway custom origin serving /api/*, without a URL scheme."
  type        = string

  validation {
    condition     = length(trimspace(var.api_gateway_origin_domain)) > 0 && !can(regex("^https?://", var.api_gateway_origin_domain))
    error_message = "api_gateway_origin_domain must be a non-empty host name without http:// or https://."
  }
}

variable "web_acl_arn" {
  description = "ARN of the us-east-1 CLOUDFRONT-scope WAF Web ACL."
  type        = string

  validation {
    condition     = length(trimspace(var.web_acl_arn)) > 0
    error_message = "web_acl_arn must be set from the WAF module web_acl_arn output."
  }
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
