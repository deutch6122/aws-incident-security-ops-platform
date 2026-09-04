variable "name_prefix" {
  description = "Prefix for ALB resource names, for example ops-platform-dev."
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

variable "vpc_id" {
  description = "VPC ID that hosts the ALB, its security group, and the target group."
  type        = string

  validation {
    condition     = can(regex("^vpc-[0-9a-f]+$", var.vpc_id))
    error_message = "vpc_id must be a valid vpc-<hex> identifier."
  }
}

variable "public_subnet_ids" {
  description = "At least two public subnet IDs (one per AZ) for the internet-facing ALB. Accepts the network module's public_subnet_ids map values."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_ids) >= 2 && length(distinct(var.public_subnet_ids)) == length(var.public_subnet_ids)
    error_message = "public_subnet_ids must contain at least two distinct subnet IDs."
  }
}

variable "allowed_ingress_cidrs" {
  description = "Trusted IPv4 CIDRs allowed to reach the ALB over both HTTP (80) and HTTPS (443). Never the public Internet, even for the demo public ALB."
  type        = list(string)
  default     = ["203.0.113.0/24"]

  validation {
    condition     = length(var.allowed_ingress_cidrs) > 0 && alltrue([for cidr in var.allowed_ingress_cidrs : can(cidrnetmask(cidr)) && cidr != "0.0.0.0/0"])
    error_message = "allowed_ingress_cidrs must contain valid non-public IPv4 CIDRs; 0.0.0.0/0 is not allowed."
  }
}

variable "create_security_group" {
  description = "When true (default) the ALB module creates and attaches its own HTTPS-only security group. When false it attaches the supplied alb_security_group_id instead."
  type        = bool
  default     = true
}

variable "alb_security_group_id" {
  description = "Existing security group to attach when create_security_group is false, for example the network module's security_group_ids.alb. Ignored when create_security_group is true."
  type        = string
  default     = null

  validation {
    condition     = var.alb_security_group_id == null || can(regex("^sg-[0-9a-f]+$", var.alb_security_group_id))
    error_message = "alb_security_group_id must be null or a valid sg-<hex> identifier."
  }
}

variable "ecs_security_group_id" {
  description = "ECS task security group that ALB egress is restricted to when create_security_group is true. When null, no ALB egress rule is created (the module never opens egress to 0.0.0.0/0)."
  type        = string
  default     = null

  validation {
    condition     = var.ecs_security_group_id == null || can(regex("^sg-[0-9a-f]+$", var.ecs_security_group_id))
    error_message = "ecs_security_group_id must be null or a valid sg-<hex> identifier."
  }
}

variable "internal" {
  description = "Whether the ALB is internal. The dev/MVP topology uses a demo public ALB (false) whose HTTPS ingress is still restricted to allowed_ingress_cidrs."
  type        = bool
  default     = false
}

variable "app_port" {
  description = "Backend API target port on the ECS tasks."
  type        = number
  default     = 8080

  validation {
    condition     = contains([8000, 8080], var.app_port)
    error_message = "app_port must be the explicitly supported application port 8000 or 8080."
  }
}

variable "certificate_arn" {
  description = "ACM certificate ARN for the HTTPS (443) listener. May be null in dev when a certificate has not yet been issued; the listener is then not created and the ALB must not be exposed until a certificate is provided."
  type        = string
  default     = null

  validation {
    condition     = var.certificate_arn == null || can(regex("^arn:aws[a-z-]*:acm:", var.certificate_arn))
    error_message = "certificate_arn must be null or a valid ACM certificate ARN."
  }
}

variable "ssl_policy" {
  description = "TLS security policy for the HTTPS listener."
  type        = string
  default     = "ELBSecurityPolicy-TLS13-1-2-2021-06"
}

variable "health_check_path" {
  description = "Target group HTTP health-check path served by the backend API."
  type        = string
  default     = "/health"
}

variable "access_logs_bucket" {
  description = "Name of an existing S3 bucket that receives ALB access logs. Required because access logging is always enabled by this module. The bucket lifecycle is owned outside this module."
  type        = string

  validation {
    condition     = length(trimspace(var.access_logs_bucket)) > 0
    error_message = "access_logs_bucket must be a non-empty existing S3 bucket name; ALB access logging is always enabled."
  }
}

variable "access_logs_prefix" {
  description = "Key prefix for ALB access-log objects within access_logs_bucket."
  type        = string
  default     = "alb"
}
