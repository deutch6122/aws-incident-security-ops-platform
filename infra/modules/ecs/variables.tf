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

variable "backend_execution_role_arn" {
  description = "ARN of the ECS task execution role (image pull, log write, secret fetch). Owned by the iam module and passed in."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:iam::", var.backend_execution_role_arn))
    error_message = "backend_execution_role_arn must be a valid IAM role ARN."
  }
}

variable "backend_task_role_arn" {
  description = "ARN of the ECS task role granting the application its runtime AWS permissions. Owned by the iam module and passed in."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:iam::", var.backend_task_role_arn))
    error_message = "backend_task_role_arn must be a valid IAM role ARN."
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

variable "migration_container_image" {
  description = "Full ECR image URI for the dedicated db-migration container."
  type        = string

  validation {
    condition     = length(trimspace(var.migration_container_image)) > 0
    error_message = "migration_container_image must be a non-empty ECR image URI."
  }
}

variable "migration_execution_role_arn" {
  description = "ARN of the dedicated migration task execution role."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:iam::", var.migration_execution_role_arn))
    error_message = "migration_execution_role_arn must be a valid IAM role ARN."
  }
}

variable "migration_task_role_arn" {
  description = "ARN of the dedicated migration task role that may read only the DB secret."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:iam::", var.migration_task_role_arn))
    error_message = "migration_task_role_arn must be a valid IAM role ARN."
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

variable "backend_db_secret_arn" {
  description = "Secrets Manager ARN of the database credential (for example aurora app_database_secret_arn). ARN reference only; the secret value is never stored here."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:secretsmanager:", var.backend_db_secret_arn))
    error_message = "backend_db_secret_arn must be a valid Secrets Manager ARN; never a secret value or connection string."
  }
}

variable "backend_db_name" {
  description = "Fallback database name used when the RDS-managed secret omits dbname."
  type        = string

  validation {
    condition     = length(trimspace(var.backend_db_name)) > 0
    error_message = "backend_db_name must be non-empty."
  }
}

variable "backend_bearer_secret_arn" {
  description = "Secrets Manager ARN whose value ECS injects as BACKEND_INTERNAL_BEARER_TOKEN."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:secretsmanager:", var.backend_bearer_secret_arn))
    error_message = "backend_bearer_secret_arn must be a valid Secrets Manager ARN."
  }
}

variable "ecs_desired_count" {
  description = "Number of running Backend tasks. Use 0 for the initial infrastructure phase and 1 after migration."
  type        = number
  default     = 0

  validation {
    condition     = var.ecs_desired_count >= 0 && floor(var.ecs_desired_count) == var.ecs_desired_count
    error_message = "ecs_desired_count must be a non-negative integer."
  }
}

variable "ecs_task_cpu" {
  description = "Fargate task CPU units. The MVP task definition uses 256."
  type        = number
  default     = 256

  validation {
    condition     = contains([256, 512, 1024], var.ecs_task_cpu)
    error_message = "ecs_task_cpu must be one of the supported Fargate values 256, 512, or 1024; the MVP uses 256."
  }
}

variable "ecs_task_memory" {
  description = "Fargate task memory (MiB). The MVP task definition uses 512."
  type        = number
  default     = 512

  validation {
    condition     = contains([512, 1024, 2048], var.ecs_task_memory)
    error_message = "ecs_task_memory must be one of the supported Fargate values 512, 1024, or 2048; the MVP uses 512."
  }
}

variable "migration_task_cpu" {
  description = "Fargate CPU units for the one-off migration task."
  type        = number
  default     = 256

  validation {
    condition     = contains([256, 512, 1024], var.migration_task_cpu)
    error_message = "migration_task_cpu must be 256, 512, or 1024."
  }
}

variable "migration_task_memory" {
  description = "Fargate memory in MiB for the one-off migration task."
  type        = number
  default     = 512

  validation {
    condition     = contains([512, 1024, 2048], var.migration_task_memory)
    error_message = "migration_task_memory must be 512, 1024, or 2048."
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

# Autoscaling is designed in but disabled for the MVP. When enable_autoscaling
# is false (default) no scalable target or policy is created and
# ecs_desired_count remains controlled by Terraform.
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
