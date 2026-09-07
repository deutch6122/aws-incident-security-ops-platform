variable "project" {
  description = "Project component of the <project>-<env>-<resource> naming convention."
  type        = string
  default     = "ops-platform"

  validation {
    condition     = var.project == "ops-platform"
    error_message = "This dev root only supports project=ops-platform."
  }
}

variable "env" {
  description = "Environment component of resource names; this root is dev-only."
  type        = string
  default     = "dev"

  validation {
    condition     = var.env == "dev"
    error_message = "Only the dev environment is supported by this Terraform root."
  }
}

variable "aws_region" {
  description = "AWS Region for the dev platform."
  type        = string
  default     = "ap-northeast-1"

  validation {
    condition     = var.aws_region == "ap-northeast-1"
    error_message = "The dev platform must use ap-northeast-1."
  }
}

variable "additional_tags" {
  description = "Optional non-sensitive tags. Required platform tags cannot be overridden."
  type        = map(string)
  default     = {}

  validation {
    condition = alltrue([
      for key, value in var.additional_tags :
      length(trimspace(key)) > 0 && length(trimspace(value)) > 0 &&
      !contains(["Project", "Environment", "Platform", "ManagedBy"], key)
    ])
    error_message = "Additional tags must have non-empty keys/values and must not override required platform tags."
  }
}

variable "resource_name_suffixes" {
  description = <<-EOT
    Optional logical-name to resource-suffix map. Each suffix is converted to
    <project>-<env>-<suffix> in local.resource_names. Suffixes use lowercase
    letters, digits, and single hyphens only; complete names are at most 63 characters.
  EOT
  type        = map(string)
  default     = {}

  validation {
    condition = alltrue([
      for suffix in values(var.resource_name_suffixes) :
      can(regex("^[a-z0-9]+(-[a-z0-9]+)*$", suffix)) &&
      length("${var.project}-${var.env}-${suffix}") <= 63
    ])
    error_message = "Resource suffixes must be non-empty lowercase alphanumeric segments separated by single hyphens, with a complete name no longer than 63 characters."
  }
}

variable "network_vpc_cidr" {
  description = "Dev VPC CIDR passed to the network module."
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.network_vpc_cidr))
    error_message = "network_vpc_cidr must be a valid IPv4 CIDR block."
  }
}

variable "network_availability_zones" {
  description = "The two dev AZs supplied to the network module."
  type        = list(string)
  default     = ["ap-northeast-1a", "ap-northeast-1c"]

  validation {
    condition     = length(var.network_availability_zones) == 2 && length(distinct(var.network_availability_zones)) == 2 && alltrue([for az in var.network_availability_zones : can(regex("^ap-northeast-1[a-z]$", az))])
    error_message = "network_availability_zones must contain exactly two distinct ap-northeast-1 Availability Zones."
  }
}

variable "network_public_subnet_cidrs" {
  description = "Public subnet CIDRs, one per network_availability_zones entry."
  type        = list(string)
  default     = ["10.0.0.0/24", "10.0.1.0/24"]

  validation {
    condition     = length(var.network_public_subnet_cidrs) == 2 && alltrue([for cidr in var.network_public_subnet_cidrs : can(cidrnetmask(cidr))])
    error_message = "network_public_subnet_cidrs must contain two valid CIDR blocks."
  }
}

variable "network_private_app_subnet_cidrs" {
  description = "Private application subnet CIDRs, one per network_availability_zones entry."
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]

  validation {
    condition     = length(var.network_private_app_subnet_cidrs) == 2 && alltrue([for cidr in var.network_private_app_subnet_cidrs : can(cidrnetmask(cidr))])
    error_message = "network_private_app_subnet_cidrs must contain two valid CIDR blocks."
  }
}

variable "network_isolated_db_subnet_cidrs" {
  description = "Isolated database subnet CIDRs, one per network_availability_zones entry."
  type        = list(string)
  default     = ["10.0.20.0/24", "10.0.21.0/24"]

  validation {
    condition     = length(var.network_isolated_db_subnet_cidrs) == 2 && alltrue([for cidr in var.network_isolated_db_subnet_cidrs : can(cidrnetmask(cidr))])
    error_message = "network_isolated_db_subnet_cidrs must contain two valid CIDR blocks."
  }
}

variable "network_enable_nat_gateway" {
  description = "Create the cost-oriented single-AZ NAT Gateway for private application egress."
  type        = bool
  default     = true
}

variable "network_allowed_alb_ingress_cidrs" {
  description = "Trusted HTTPS CIDRs for the future ALB; must never include 0.0.0.0/0."
  type        = list(string)
  default     = ["203.0.113.0/24"]

  validation {
    condition     = length(var.network_allowed_alb_ingress_cidrs) > 0 && alltrue([for cidr in var.network_allowed_alb_ingress_cidrs : can(cidrnetmask(cidr)) && cidr != "0.0.0.0/0"])
    error_message = "network_allowed_alb_ingress_cidrs must contain non-public IPv4 CIDRs; 0.0.0.0/0 is disallowed."
  }
}

variable "network_app_port" {
  description = "Backend API port allowed only from the ALB security group."
  type        = number
  default     = 8080

  validation {
    condition     = contains([8000, 8080], var.network_app_port)
    error_message = "network_app_port must be 8000 or 8080."
  }
}

variable "network_external_https_egress_cidrs" {
  description = "Explicit HTTPS egress CIDRs for ECS/EKS; can be empty after endpoint coverage review."
  type        = list(string)
  default     = ["0.0.0.0/0"]

  validation {
    condition     = alltrue([for cidr in var.network_external_https_egress_cidrs : can(cidrnetmask(cidr))])
    error_message = "network_external_https_egress_cidrs must contain valid IPv4 CIDRs."
  }
}

variable "network_enable_vpc_endpoints" {
  description = "Enable optional S3/ECR/Secrets Manager/Logs/SQS endpoints to reduce NAT dependency."
  type        = bool
  default     = false
}

variable "network_interface_vpc_endpoint_services" {
  description = "PrivateLink endpoint services enabled when network_enable_vpc_endpoints is true."
  type        = set(string)
  default     = ["ecr.api", "ecr.dkr", "secretsmanager", "logs", "sqs"]
}

variable "ecr_image_tag_mutability" {
  description = "ECR image tag mutability; immutable is the safe dev default."
  type        = string
  default     = "IMMUTABLE"

  validation {
    condition     = contains(["IMMUTABLE", "MUTABLE"], var.ecr_image_tag_mutability)
    error_message = "ecr_image_tag_mutability must be IMMUTABLE or MUTABLE."
  }
}

variable "ecr_untagged_image_expiration_days" {
  description = "ECR lifecycle retention period for untagged images."
  type        = number
  default     = 7

  validation {
    condition     = var.ecr_untagged_image_expiration_days >= 1
    error_message = "ecr_untagged_image_expiration_days must be positive."
  }
}

variable "ecr_tagged_image_retention_count" {
  description = "ECR lifecycle maximum retained tagged release images."
  type        = number
  default     = 10

  validation {
    condition     = var.ecr_tagged_image_retention_count >= 1
    error_message = "ecr_tagged_image_retention_count must be positive."
  }
}

variable "ecr_retained_tag_prefixes" {
  description = "Versioned image-tag prefixes protected by the tagged ECR lifecycle rule."
  type        = list(string)
  default     = ["v", "release", "sha"]
}

# These are an explicit contract with the bootstrap-owned Infra_Pipeline.
# Terraform backend blocks cannot reference variables, so backend.tf uses the
# matching key as static configuration while these values make drift visible.
variable "pipeline_tf_workdir" {
  description = "Repository-relative Terraform root used by the bootstrap CodeBuild buildspecs."
  type        = string
  default     = "infra/environments/dev"

  validation {
    condition     = var.pipeline_tf_workdir == "infra/environments/dev"
    error_message = "The dev pipeline work directory must be infra/environments/dev."
  }
}

variable "pipeline_backend_key" {
  description = "S3 state key for the dev root, mirrored by backend.tf after Bootstrap."
  type        = string
  default     = "environments/dev/terraform.tfstate"

  validation {
    condition     = var.pipeline_backend_key == "environments/dev/terraform.tfstate"
    error_message = "The dev backend key must be environments/dev/terraform.tfstate."
  }
}

# Task 6.1 Aurora Serverless v2 inputs. Passwords are intentionally absent:
# RDS generates and manages the master credential in Secrets Manager.
variable "aurora_database_name" {
  description = "Initial non-sensitive Aurora PostgreSQL database name; schema and migrations are outside Task 6.1."
  type        = string
  default     = "opsplatform"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{0,62}$", var.aurora_database_name))
    error_message = "aurora_database_name must start with a lowercase letter and contain only lowercase letters or digits, up to 63 characters."
  }
}

variable "aurora_engine_version" {
  description = "Optional Aurora PostgreSQL version. null lets RDS select the current default version supported in ap-northeast-1; pin only after checking regional Serverless v2 support."
  type        = string
  default     = null

  validation {
    condition     = var.aurora_engine_version == null || can(regex("^1[4-6]\\.[0-9]+(\\.[0-9]+)?$", var.aurora_engine_version))
    error_message = "aurora_engine_version must be null or an Aurora PostgreSQL 14.x, 15.x, or 16.x version supported for Serverless v2 in ap-northeast-1."
  }
}

variable "aurora_master_username" {
  description = "Non-sensitive RDS master username. Its credential value is AWS-managed in Secrets Manager."
  type        = string
  default     = "ops_admin"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{0,15}$", var.aurora_master_username))
    error_message = "aurora_master_username must start with a lowercase letter and contain only lowercase letters, digits, or underscores (1-16 characters)."
  }
}

variable "aurora_master_user_secret_kms_key_id" {
  description = "Optional customer-managed KMS key ARN for the RDS-managed master secret; null uses the AWS-managed key."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.aurora_master_user_secret_kms_key_id == null || can(regex("^arn:aws(-[a-z]+)?:kms:", var.aurora_master_user_secret_kms_key_id))
    error_message = "aurora_master_user_secret_kms_key_id must be null or a KMS key ARN."
  }
}

variable "aurora_min_capacity" {
  description = "Minimum Aurora Serverless v2 ACUs; 0.5 is the dev MVP cost-oriented default."
  type        = number
  default     = 0.5

  validation {
    condition     = var.aurora_min_capacity >= 0.5
    error_message = "aurora_min_capacity must be at least 0.5 ACU."
  }
}

variable "aurora_max_capacity" {
  description = "Maximum Aurora Serverless v2 ACUs; 2 is the dev MVP cost-oriented default."
  type        = number
  default     = 2

  validation {
    condition     = var.aurora_max_capacity >= var.aurora_min_capacity && var.aurora_max_capacity <= 128
    error_message = "aurora_max_capacity must be at least aurora_min_capacity and no more than 128 ACUs."
  }
}

variable "aurora_backup_retention_period" {
  description = "Automated Aurora backup retention in days; the dev default is one day."
  type        = number
  default     = 1

  validation {
    condition     = var.aurora_backup_retention_period >= 1 && var.aurora_backup_retention_period <= 35
    error_message = "aurora_backup_retention_period must be between 1 and 35 days."
  }
}

variable "aurora_enabled_cloudwatch_logs_exports" {
  description = "Aurora PostgreSQL logs exported to CloudWatch; log storage has a cost impact."
  type        = set(string)
  default     = ["postgresql"]

  validation {
    condition     = length(setsubtract(var.aurora_enabled_cloudwatch_logs_exports, toset(["postgresql"]))) == 0
    error_message = "aurora_enabled_cloudwatch_logs_exports may contain only postgresql."
  }
}

variable "aurora_performance_insights_enabled" {
  description = "Enable Aurora Performance Insights only after reviewing dev cost and production retention requirements."
  type        = bool
  default     = false
}

variable "aurora_deletion_protection" {
  description = "Deletion protection is false for the dev MVP; production should enable it."
  type        = bool
  default     = false
}

variable "aurora_skip_final_snapshot" {
  description = "Whether destroy skips the final snapshot. False is the safer dev default and must be reviewed before apply or destroy."
  type        = bool
  default     = false
}

variable "aurora_final_snapshot_identifier" {
  description = "Optional final snapshot name. Null derives a name from the dev prefix; set a unique reviewed value for repeated lifecycle operations."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.aurora_final_snapshot_identifier == null || can(regex("^[a-z][a-z0-9-]{0,62}$", var.aurora_final_snapshot_identifier))
    error_message = "aurora_final_snapshot_identifier must be null or a lowercase RDS snapshot identifier beginning with a letter and at most 63 characters."
  }
}

# --------------------------------------------------------------------------- #
# Backend internal bearer token secret (Task 3). The random value is generated
# and stored only in Secrets Manager. The real value is never emitted to an
# output, log, plaintext environment variable, tfvars, or README. Only the ARN
# is wired into the IAM and ECS modules.
# --------------------------------------------------------------------------- #
variable "backend_bearer_secret_recovery_window_days" {
  description = "Secrets Manager recovery window (days) for the Backend internal bearer token secret. 0 forces immediate deletion (dev convenience); 7-30 is recommended for recoverability."
  type        = number
  default     = 7

  validation {
    condition     = var.backend_bearer_secret_recovery_window_days == 0 || (var.backend_bearer_secret_recovery_window_days >= 7 && var.backend_bearer_secret_recovery_window_days <= 30)
    error_message = "backend_bearer_secret_recovery_window_days must be 0 (immediate deletion) or between 7 and 30 days."
  }
}

# --------------------------------------------------------------------------- #
# Full-stack integration inputs (Task 27). Sensitive values are deliberately
# absent: these are non-secret identifiers, reviewed network ranges, package
# references, and operational feature switches.
# --------------------------------------------------------------------------- #
variable "application_image_tag" {
  description = "Immutable tag used for the Backend and migration task definitions during the approved deployment phase."
  type        = string
  default     = "bootstrap-placeholder"

  validation {
    condition     = can(regex("^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$", var.application_image_tag))
    error_message = "application_image_tag must be a valid Docker image tag."
  }
}

variable "ecs_desired_count" {
  description = "Backend ECS desired count. Keep at 0 for the first infrastructure apply; set to 1 only after images and migrations are ready."
  type        = number
  default     = 0

  validation {
    condition     = contains([0, 1], var.ecs_desired_count)
    error_message = "ecs_desired_count must be 0 for first apply or 1 after the migration gate."
  }
}

variable "alb_certificate_arn" {
  description = "ACM certificate ARN in ap-northeast-1 for the ALB HTTPS listener."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:acm:ap-northeast-1:[0-9]{12}:certificate/", var.alb_certificate_arn))
    error_message = "alb_certificate_arn must be an ap-northeast-1 ACM certificate ARN."
  }
}

variable "alb_access_logs_prefix" {
  description = "Non-empty S3 key prefix for ALB access logs."
  type        = string
  default     = "alb"

  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9/_-]*$", var.alb_access_logs_prefix))
    error_message = "alb_access_logs_prefix must be a non-empty safe S3 key prefix."
  }
}

variable "alb_access_logs_expiration_days" {
  description = "Retention in days for ALB access-log objects."
  type        = number
  default     = 90

  validation {
    condition     = var.alb_access_logs_expiration_days >= 1
    error_message = "alb_access_logs_expiration_days must be at least 1."
  }
}

variable "alb_access_logs_force_destroy" {
  description = "Allow Terraform to delete the ALB log bucket with objects. Keep false unless an approved dev teardown requires it."
  type        = bool
  default     = false
}

variable "portal_bucket_force_destroy" {
  description = "Allow Terraform to delete Portal_Storage with objects. Keep false unless an approved dev teardown requires it."
  type        = bool
  default     = false
}

variable "eks_kubernetes_version" {
  description = "EKS Kubernetes minor version; reconfirm Standard Support immediately before apply."
  type        = string
  default     = "1.36"

  validation {
    condition     = can(regex("^1\\.[0-9]{2}$", var.eks_kubernetes_version))
    error_message = "eks_kubernetes_version must be a Kubernetes minor version such as 1.36."
  }
}

variable "eks_public_access_cidrs" {
  description = "Reviewed operator CIDRs allowed to reach the public EKS API endpoint."
  type        = list(string)
  default     = ["203.0.113.0/24"]

  validation {
    condition = (
      length(var.eks_public_access_cidrs) > 0 &&
      alltrue([for cidr in var.eks_public_access_cidrs : can(cidrhost(cidr, 0))]) &&
      !contains(var.eks_public_access_cidrs, "0.0.0.0/0") &&
      !contains(var.eks_public_access_cidrs, "::/0")
    )
    error_message = "eks_public_access_cidrs must contain reviewed CIDRs and cannot contain a world-open range."
  }
}

variable "eks_operator_principal_arn" {
  description = "Reviewed IAM role or user ARN granted the EKS cluster access policy."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:(role|user)/", var.eks_operator_principal_arn))
    error_message = "eks_operator_principal_arn must be an IAM role or user ARN."
  }
}

variable "migration_launcher_trusted_principal_arns" {
  description = "Reviewed IAM principals allowed to assume the migration launcher role."
  type        = list(string)

  validation {
    condition = length(var.migration_launcher_trusted_principal_arns) > 0 && alltrue([
      for arn in var.migration_launcher_trusted_principal_arns : can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:(role|user)/", arn))
    ])
    error_message = "migration_launcher_trusted_principal_arns must contain at least one IAM role or user ARN."
  }
}

variable "lambda_package_s3_bucket" {
  description = "Versioned bootstrap artifact bucket containing the Portal Lambda package."
  type        = string
}

variable "lambda_package_s3_key" {
  description = "Immutable Portal Lambda object key: lambda/<commit-sha>/portal-api.zip."
  type        = string

  validation {
    condition     = can(regex("^lambda/[0-9a-f]{7,64}/portal-api\\.zip$", var.lambda_package_s3_key))
    error_message = "lambda_package_s3_key must match lambda/<7-64 lowercase hex commit-sha>/portal-api.zip."
  }
}

variable "lambda_package_s3_object_version" {
  description = "Version ID of the approved Portal Lambda package object."
  type        = string
}

variable "lambda_source_code_hash" {
  description = "Base64 SHA-256 digest of the approved Portal Lambda package."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9+/]{43}=$", var.lambda_source_code_hash))
    error_message = "lambda_source_code_hash must be a base64-encoded SHA-256 digest."
  }
}

variable "cognito_callback_urls" {
  description = "OAuth callback URLs. Replace localhost with the final CloudFront HTTPS callback after the first apply."
  type        = list(string)
  default     = ["http://localhost:5173/callback"]
}

variable "cognito_logout_urls" {
  description = "OAuth logout URLs. Replace localhost with the final CloudFront HTTPS URL after the first apply."
  type        = list(string)
  default     = ["http://localhost:5173/"]
}

variable "cognito_keep_localhost_urls" {
  description = "Retain localhost URLs after final HTTPS URLs are configured."
  type        = bool
  default     = false
}

variable "cloudfront_price_class" {
  description = "CloudFront geographic price class."
  type        = string
  default     = "PriceClass_200"

  validation {
    condition     = contains(["PriceClass_100", "PriceClass_200", "PriceClass_All"], var.cloudfront_price_class)
    error_message = "cloudfront_price_class must be PriceClass_100, PriceClass_200, or PriceClass_All."
  }
}

variable "waf_additional_managed_rule_groups" {
  description = "Optional additional managed WAF rule groups beyond the common rule set."
  type = list(object({
    name        = string
    vendor_name = string
    priority    = number
  }))
  default = []
}

variable "waf_logging_enabled" {
  description = "Enable WAF logs in us-east-1."
  type        = bool
  default     = true
}

variable "waf_kms_enabled" {
  description = "Use a customer-managed KMS key for WAF logs when logging is enabled."
  type        = bool
  default     = true
}

variable "waf_log_retention_days" {
  description = "WAF CloudWatch Logs retention period."
  type        = number
  default     = 30
}

variable "monitoring_enable_sns_subscription" {
  description = "Create a monitoring SNS subscription using an endpoint fetched from SSM."
  type        = bool
  default     = false
}

variable "monitoring_notification_endpoint" {
  description = "SSM parameter name containing the notification endpoint; never the endpoint value itself."
  type        = string
  default     = null
  nullable    = true
}

variable "monitoring_notification_protocol" {
  description = "SNS notification protocol."
  type        = string
  default     = "email"

  validation {
    condition     = contains(["email", "email-json", "https"], var.monitoring_notification_protocol)
    error_message = "monitoring_notification_protocol must be email, email-json, or https."
  }
}
