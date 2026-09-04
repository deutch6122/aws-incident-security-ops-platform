variable "name_prefix" {
  description = "Prefix for API Gateway resource names, for example ops-platform-dev."
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

# OIDC issuer URL of the Cognito User Pool (from the cognito module's issuer_url
# output). The JWT authorizer validates tokens against this issuer. No real
# issuer is committed; the dev root passes the cognito module output.
variable "jwt_issuer_url" {
  description = "OIDC issuer URL of the Cognito User Pool, from the cognito module issuer_url output."
  type        = string

  validation {
    condition     = can(regex("^https://", var.jwt_issuer_url))
    error_message = "jwt_issuer_url must be an https URL (the Cognito issuer)."
  }
}

# Allowed audiences for the JWT authorizer. Typically the Cognito App Client id
# list (from the cognito module app_client_id output). No real id is committed.
variable "jwt_audiences" {
  description = "Allowed JWT audiences (typically the Cognito App Client ids)."
  type        = list(string)

  validation {
    condition     = length(var.jwt_audiences) > 0
    error_message = "jwt_audiences must contain at least one audience (App Client id)."
  }
}

# Invoke ARN of the Portal_API Lambda (from the lambda module lambda_invoke_arn
# output). Used by the AWS_PROXY integration. No real ARN is committed; the dev
# root passes the lambda module output.
variable "lambda_invoke_arn" {
  description = "Invoke ARN of the Portal_API Lambda, from the lambda module lambda_invoke_arn output."
  type        = string

  validation {
    condition     = length(trimspace(var.lambda_invoke_arn)) > 0
    error_message = "lambda_invoke_arn must be set to the Portal_API Lambda invoke ARN."
  }
}

# Function name of the Portal_API Lambda (from the lambda module
# lambda_function_name output). Used by the aws_lambda_permission that lets API
# Gateway invoke the Lambda. This is distinct from lambda_invoke_arn, which is
# used by the AWS_PROXY integration. No real name is committed; the dev root
# passes the lambda module output.
variable "lambda_function_name" {
  description = "aws_lambda_permission 用の Lambda 関数名（lambda module の lambda_function_name 出力を配線）。"
  type        = string

  validation {
    condition     = length(trimspace(var.lambda_function_name)) > 0
    error_message = "lambda_function_name must be set to the Portal_API Lambda function name."
  }
}

variable "stage_name" {
  description = "HTTP API stage name."
  type        = string
  default     = "api"
}
