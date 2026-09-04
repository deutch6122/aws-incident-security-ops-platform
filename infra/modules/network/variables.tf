variable "name_prefix" {
  description = "Prefix for network resource names, for example ops-platform-dev."
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

variable "vpc_cidr" {
  description = "IPv4 CIDR range for the VPC."
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "vpc_cidr must be a valid IPv4 CIDR block."
  }
}

variable "availability_zones" {
  description = "Exactly two Availability Zones in the configured AWS region."
  type        = list(string)
  default     = ["ap-northeast-1a", "ap-northeast-1c"]

  validation {
    condition     = length(var.availability_zones) == 2 && length(distinct(var.availability_zones)) == 2 && alltrue([for az in var.availability_zones : can(regex("^ap-northeast-1[a-z]$", az))])
    error_message = "availability_zones must contain exactly two distinct ap-northeast-1 Availability Zones."
  }
}

variable "public_subnet_cidrs" {
  description = "One public subnet CIDR per Availability Zone."
  type        = list(string)
  default     = ["10.0.0.0/24", "10.0.1.0/24"]

  validation {
    condition     = length(var.public_subnet_cidrs) == 2 && length(distinct(var.public_subnet_cidrs)) == 2 && alltrue([for cidr in var.public_subnet_cidrs : can(cidrnetmask(cidr))])
    error_message = "public_subnet_cidrs must contain two distinct valid CIDR blocks."
  }
}

variable "private_app_subnet_cidrs" {
  description = "One private application subnet CIDR per Availability Zone."
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]

  validation {
    condition     = length(var.private_app_subnet_cidrs) == 2 && length(distinct(var.private_app_subnet_cidrs)) == 2 && alltrue([for cidr in var.private_app_subnet_cidrs : can(cidrnetmask(cidr))])
    error_message = "private_app_subnet_cidrs must contain two distinct valid CIDR blocks."
  }
}

variable "isolated_db_subnet_cidrs" {
  description = "One isolated database subnet CIDR per Availability Zone."
  type        = list(string)
  default     = ["10.0.20.0/24", "10.0.21.0/24"]

  validation {
    condition     = length(var.isolated_db_subnet_cidrs) == 2 && length(distinct(var.isolated_db_subnet_cidrs)) == 2 && alltrue([for cidr in var.isolated_db_subnet_cidrs : can(cidrnetmask(cidr))])
    error_message = "isolated_db_subnet_cidrs must contain two distinct valid CIDR blocks."
  }
}

variable "enable_nat_gateway" {
  description = "Whether to create the MVP single-AZ NAT Gateway and its private-app default route."
  type        = bool
  default     = true
}

variable "allowed_alb_ingress_cidrs" {
  description = "Trusted IPv4 CIDRs allowed to reach the future ALB over HTTPS. Never defaults to the public Internet."
  type        = list(string)
  default     = ["203.0.113.0/24"]

  validation {
    condition     = length(var.allowed_alb_ingress_cidrs) > 0 && alltrue([for cidr in var.allowed_alb_ingress_cidrs : can(cidrnetmask(cidr)) && cidr != "0.0.0.0/0"])
    error_message = "allowed_alb_ingress_cidrs must contain valid non-public IPv4 CIDRs; 0.0.0.0/0 is not allowed."
  }
}

variable "app_port" {
  description = "Backend API listener port exposed from the ECS tasks."
  type        = number
  default     = 8080

  validation {
    condition     = contains([8000, 8080], var.app_port)
    error_message = "app_port must be the explicitly supported application port 8000 or 8080."
  }
}

variable "external_https_egress_cidrs" {
  description = "CIDRs allowed for explicit ECS/EKS outbound HTTPS. Set to [] only when all required AWS services are reached through endpoints."
  type        = list(string)
  default     = ["0.0.0.0/0"]

  validation {
    condition     = alltrue([for cidr in var.external_https_egress_cidrs : can(cidrnetmask(cidr))])
    error_message = "external_https_egress_cidrs must contain valid IPv4 CIDR blocks."
  }
}

variable "enable_vpc_endpoints" {
  description = "Whether to add optional S3 and interface VPC endpoints to reduce NAT dependency."
  type        = bool
  default     = false
}

variable "interface_vpc_endpoint_services" {
  description = "AWS PrivateLink services to create when enable_vpc_endpoints is true."
  type        = set(string)
  default     = ["ecr.api", "ecr.dkr", "secretsmanager", "logs", "sqs"]

  validation {
    condition = length(setsubtract(
      var.interface_vpc_endpoint_services,
      toset(["ecr.api", "ecr.dkr", "secretsmanager", "logs", "sqs"]),
    )) == 0
    error_message = "interface_vpc_endpoint_services may contain only ecr.api, ecr.dkr, secretsmanager, logs, or sqs."
  }
}
