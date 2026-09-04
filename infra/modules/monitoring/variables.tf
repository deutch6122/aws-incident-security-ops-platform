variable "name_prefix" {
  description = "Prefix for monitoring resource names, for example ops-platform-dev."
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

variable "aws_region" {
  description = "Region used inside dashboard widget definitions (metrics are region-scoped). Default ap-northeast-1."
  type        = string
  default     = "ap-northeast-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", var.aws_region))
    error_message = "aws_region must look like an AWS region, for example ap-northeast-1."
  }
}

# --------------------------------------------------------------------------- #
# Monitored resource identifiers. These are CloudWatch dimension VALUES (names
# / ids), NOT ARNs and NOT account ids. Callers wire real names in from other
# modules' outputs; the defaults are naming-convention placeholders so the
# module plans standalone without embedding any real resource identity.
# --------------------------------------------------------------------------- #
variable "dlq_queue_name" {
  description = "SQS DLQ name (QueueName dimension) alarmed on ApproximateNumberOfMessagesVisible > 0."
  type        = string
  default     = "ops-platform-dev-events-dlq"
}

variable "ecs_cluster_name" {
  description = "ECS cluster name (ClusterName dimension) for the Backend_API service alarms."
  type        = string
  default     = "ops-platform-dev-cluster"
}

variable "ecs_service_name" {
  description = "ECS service name (ServiceName dimension) for CPU/Memory/RunningTaskCount alarms."
  type        = string
  default     = "ops-platform-dev-backend-api"
}

variable "alb_arn_suffix" {
  description = "ALB ARN suffix (LoadBalancer dimension value, e.g. app/name/hash). Not a full ARN."
  type        = string
  default     = "app/ops-platform-dev-alb/PLACEHOLDER"
}

variable "lambda_function_name" {
  description = "Portal_API Lambda function name (FunctionName dimension) for Errors/Throttles/Duration alarms."
  type        = string
  default     = "ops-platform-dev-portal-api"
}

variable "aurora_db_cluster_identifier" {
  description = "Aurora cluster identifier (DBClusterIdentifier dimension) for ACU / connection alarms."
  type        = string
  default     = "ops-platform-dev-aurora"
}

# --------------------------------------------------------------------------- #
# Alarm thresholds / evaluation. dev-friendly defaults kept conservative so the
# module does not create noisy or expensive monitoring. All are variable-driven.
# --------------------------------------------------------------------------- #
variable "alarm_evaluation_periods" {
  description = "Number of evaluation periods for each alarm."
  type        = number
  default     = 1

  validation {
    condition     = var.alarm_evaluation_periods >= 1 && var.alarm_evaluation_periods <= 10
    error_message = "alarm_evaluation_periods must be between 1 and 10."
  }
}

variable "alarm_period_seconds" {
  description = "Metric period in seconds for each alarm. 300 (5 min) keeps dev CloudWatch cost low."
  type        = number
  default     = 300

  validation {
    condition     = contains([60, 300, 900], var.alarm_period_seconds)
    error_message = "alarm_period_seconds must be one of 60, 300, 900."
  }
}

variable "ecs_cpu_high_threshold_percent" {
  description = "ECS CPUUtilization alarm threshold (percent)."
  type        = number
  default     = 80
}

variable "ecs_memory_high_threshold_percent" {
  description = "ECS MemoryUtilization alarm threshold (percent)."
  type        = number
  default     = 80
}

variable "ecs_min_running_tasks" {
  description = "Minimum RunningTaskCount before the low-task alarm fires (desired_count=1 in MVP)."
  type        = number
  default     = 1
}

variable "alb_5xx_threshold_count" {
  description = "ALB HTTPCode_ELB_5XX_Count alarm threshold (count per period)."
  type        = number
  default     = 5
}

variable "alb_latency_threshold_seconds" {
  description = "ALB TargetResponseTime alarm threshold (seconds)."
  type        = number
  default     = 2
}

variable "lambda_errors_threshold_count" {
  description = "Lambda Errors alarm threshold (count per period)."
  type        = number
  default     = 1
}

variable "lambda_throttles_threshold_count" {
  description = "Lambda Throttles alarm threshold (count per period)."
  type        = number
  default     = 1
}

variable "lambda_duration_threshold_ms" {
  description = "Lambda Duration alarm threshold (milliseconds). Portal_API timeout is 10s."
  type        = number
  default     = 8000
}

variable "aurora_acu_threshold" {
  description = "Aurora ServerlessDatabaseCapacity (ACU) alarm threshold. Max ACU is 2 in MVP."
  type        = number
  default     = 2
}

variable "aurora_connections_threshold" {
  description = "Aurora DatabaseConnections alarm threshold (count)."
  type        = number
  default     = 80
}
