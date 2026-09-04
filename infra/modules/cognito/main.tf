data "aws_region" "current" {}

locals {
  region           = var.aws_region == null ? data.aws_region.current.name : var.aws_region
  user_pool_name   = "${var.name_prefix}-user-pool"
  app_client_name  = "${var.name_prefix}-portal-client"
}

# Auth_Service for Product_B (public portal) Viewers (Requirement 9.1, 9.2).
# The User Pool issues JWTs that the Portal_API's API Gateway JWT authorizer
# (Task 14.2) validates. This module belongs to Product_B only and has no
# reference to or dependency on Product_A (Aurora/RDS/EKS/ECS/SQS/Backend API).
resource "aws_cognito_user_pool" "this" {
  name = local.user_pool_name

  # Viewers sign in with their email address.
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  username_configuration {
    case_sensitive = false
  }

  # Safe MVP password policy: minimum length plus all character classes.
  password_policy {
    minimum_length                   = var.password_minimum_length
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 7
  }

  # Recover accounts only through verified email; no phone fallback in dev.
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # Only administrators create Viewer accounts in the MVP; no open self sign-up.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  tags = merge(var.common_tags, {
    Name      = local.user_pool_name
    Component = "cognito"
    Role      = "user-pool"
  })
}

# Public App Client used by the Portal static frontend (SPA). A browser client
# cannot keep a secret, so no client secret is generated (generate_secret =
# false). Auth flows are limited to the SRP and refresh-token flows.
resource "aws_cognito_user_pool_client" "portal" {
  name         = local.app_client_name
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  prevent_user_existence_errors = "ENABLED"

  access_token_validity  = 1
  id_token_validity       = 1
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}
