variable "name_prefix" {
  description = "Prefix for ECS resource names, for example ops-platform-dev."
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

variable "private_subnet_ids" {
  description = "Private application subnet IDs (one per AZ) for the Fargate service. Accepts the network module's private_app_subnet_ids map values."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 1 && length(distinct(var.private_subnet_ids)) == length(var.private_subnet_ids)
    error_message = "private_subnet_ids must contain at least one distinct private application subnet ID."
  }
}

variable "ecs_security_group_id" {
  description = "Security group attached to the Fargate tasks, for example the network module's security_group_ids.ecs."
  type        = string

  validation {
    condition     = can(regex("^sg-[0-9a-f]+$", var.ecs_security_group_id))
    error_message = "ecs_security_group_id must be a valid sg-<hex> identifier."
  }
}

variable "target_group_arn" {
  description = "Target group ARN from the alb module; the service registers task IPs here."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:elasticloadbalancing:", var.target_group_arn))
    error_message = "target_group_arn must be a valid ELBv2 target group ARN."
  }
}

variable "task_execution_role_arn" {
  description = "ARN of the ECS task execution role (image pull, log write, secret fetch). Owned by the iam module and passed in."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:iam::", var.task_execution_role_arn))
    error_message = "task_execution_role_arn must be a valid IAM role ARN."
  }
}

variable "task_role_arn" {
  description = "ARN of the ECS task role granting the application its runtime AWS permissions. Owned by the iam module and passed in."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:iam::", var.task_role_arn))
    error_message = "task_role_arn must be a valid IAM role ARN."
  }
}

variable "container_image" {
  description = "Full ECR image URI (repository:tag or repository@digest) for the backend API container."
  type        = string

  validation {
    condition     = length(trimspace(var.container_image)) > 0
    error_message = "container_image must be a non-empty ECR image URI."
  }
}

variable "app_port" {
  description = "Container port exposed by the backend API and registered with the target group."
  type        = number
  default     = 8080

  validation {
    condition     = contains([8000, 8080], var.app_port)
    error_message = "app_port must be the explicitly supported application port 8000 or 8080."
  }
}

# The db_secret_arn is the Secrets Manager ARN (for example the aurora module's
# app_database_secret_arn). It is an ARN reference only. The secret VALUE, DB
# password, and full connection URL are never placed in this module.
variable "db_secret_arn" {
  description = "Secrets Manager ARN of the database credential (for example aurora app_database_secret_arn). ARN reference only; the secret value is never stored here."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:secretsmanager:", var.db_secret_arn))
    error_message = "db_secret_arn must be a valid Secrets Manager ARN; never a secret value or connection string."
  }
}

variable "db_secret_env_name" {
  description = "Environment variable name the container reads the injected secret into."
  type        = string
  default     = "DB_SECRET"
}

variable "desired_count" {
  description = "Number of running tasks. The MVP runs a single task."
  type        = number
  default     = 1

  validation {
    condition     = var.desired_count >= 1
    error_message = "desired_count must be at least 1."
  }
}

variable "cpu" {
  description = "Fargate task CPU units. The MVP task definition uses 256."
  type        = number
  default     = 256

  validation {
    condition     = contains([256, 512, 1024], var.cpu)
    error_message = "cpu must be one of the supported Fargate values 256, 512, or 1024; the MVP uses 256."
  }
}

variable "memory" {
  description = "Fargate task memory (MiB). The MVP task definition uses 512."
  type        = number
  default     = 512

  validation {
    condition     = contains([512, 1024, 2048], var.memory)
    error_message = "memory must be one of the supported Fargate values 512, 1024, or 2048; the MVP uses 512."
  }
}

variable "log_retention_days" {
  description = "Retention for the container CloudWatch Logs group."
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90], var.log_retention_days)
    error_message = "log_retention_days must be a supported CloudWatch Logs retention value."
  }
}

variable "aws_region" {
  description = "AWS region for the awslogs driver. When null the module reads the provider region."
  type        = string
  default     = null
}

variable "assign_public_ip" {
  description = "Whether Fargate tasks receive a public IP. Always false for private-subnet MVP tasks."
  type        = bool
  default     = false
}

# Autoscaling is designed in but disabled for the MVP. When enable_autoscaling
# is false (default) no scalable target or policy is created and desired_count
# holds the task count at 1.
variable "enable_autoscaling" {
  description = "Design-only autoscaling switch. Default false (MVP minimal/disabled): no scalable target or policy is created."
  type        = bool
  default     = false
}

variable "autoscaling_min_capacity" {
  description = "Minimum task count when enable_autoscaling is true."
  type        = number
  default     = 1
}

variable "autoscaling_max_capacity" {
  description = "Maximum task count when enable_autoscaling is true."
  type        = number
  default     = 2
}

variable "autoscaling_cpu_target" {
  description = "Target average CPU utilization percent when enable_autoscaling is true."
  type        = number
  default     = 70
}
