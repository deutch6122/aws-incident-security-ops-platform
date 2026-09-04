variable "name_prefix" {
  description = "Prefix for Cognito resource names, for example ops-platform-dev."
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

# Minimum password length enforced by the User Pool password policy. Cognito
# allows 6-99; the MVP baseline is 8 with all character classes required.
variable "password_minimum_length" {
  description = "Minimum length for Viewer passwords (Cognito allows 6-99)."
  type        = number
  default     = 8

  validation {
    condition     = var.password_minimum_length >= 8 && var.password_minimum_length <= 99
    error_message = "password_minimum_length must be between 8 and 99."
  }
}

# AWS region used only to construct the OIDC issuer URL locally. When null the
# module reads the provider region (same pattern as the ecs/network modules).
# No real account id or user pool id is ever embedded here.
variable "aws_region" {
  description = "AWS region used to build the issuer URL. When null the module reads the provider region."
  type        = string
  default     = null
}
