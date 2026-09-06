variable "name_prefix" {
  description = "Prefix for messaging resource names, for example ops-platform-dev."
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

variable "visibility_timeout_seconds" {
  description = "Main queue visibility timeout. Must exceed the worker per-message handling time so redelivery does not race a still-running handler."
  type        = number
  default     = 30

  validation {
    condition     = var.visibility_timeout_seconds >= 0 && var.visibility_timeout_seconds <= 43200
    error_message = "visibility_timeout_seconds must be between 0 and 43200 (12 hours)."
  }
}

variable "message_retention_seconds" {
  description = "Main queue message retention period. Default 345600 seconds (4 days)."
  type        = number
  default     = 345600

  validation {
    condition     = var.message_retention_seconds >= 60 && var.message_retention_seconds <= 1209600
    error_message = "message_retention_seconds must be between 60 and 1209600 (14 days)."
  }
}

variable "sqs_max_receive_count" {
  description = "Number of receive attempts before a message is moved to its DLQ (redrive maxReceiveCount). Applied identically to both the alarm and finding systems."
  type        = number
  default     = 5

  validation {
    condition     = var.sqs_max_receive_count >= 1 && var.sqs_max_receive_count <= 1000
    error_message = "sqs_max_receive_count must be between 1 and 1000."
  }
}

variable "dlq_message_retention_seconds" {
  description = "DLQ message retention period. Default 1209600 seconds (14 days) to leave time to inspect poison messages."
  type        = number
  default     = 1209600

  validation {
    condition     = var.dlq_message_retention_seconds >= 60 && var.dlq_message_retention_seconds <= 1209600
    error_message = "dlq_message_retention_seconds must be between 60 and 1209600 (14 days)."
  }
}

variable "receive_wait_time_seconds" {
  description = "Long-poll wait time on the main queues (0-20)."
  type        = number
  default     = 20

  validation {
    condition     = var.receive_wait_time_seconds >= 0 && var.receive_wait_time_seconds <= 20
    error_message = "receive_wait_time_seconds must be between 0 and 20."
  }
}

variable "sqs_managed_sse" {
  description = "Enable SSE-SQS (SQS-managed server-side encryption) on every queue and DLQ. No customer key material is referenced."
  type        = bool
  default     = true
}

variable "event_source" {
  description = "EventBridge event pattern source value. Matches the seed script source so injected sample events are routed."
  type        = string
  default     = "ops-platform.sample"

  validation {
    condition     = length(trimspace(var.event_source)) > 0
    error_message = "event_source must be a non-empty string."
  }
}

variable "alarm_event_detail_types" {
  description = "EventBridge detail-type values that route to the alarm system queue. Defaults to AlarmEvent."
  type        = list(string)
  default     = ["AlarmEvent"]

  validation {
    condition     = length(var.alarm_event_detail_types) > 0 && alltrue([for dt in var.alarm_event_detail_types : length(trimspace(dt)) > 0])
    error_message = "alarm_event_detail_types must contain at least one non-empty detail-type."
  }
}

variable "finding_event_detail_types" {
  description = "EventBridge detail-type values that route to the finding system queue. Defaults to SecurityFinding."
  type        = list(string)
  default     = ["SecurityFinding"]

  validation {
    condition     = length(var.finding_event_detail_types) > 0 && alltrue([for dt in var.finding_event_detail_types : length(trimspace(dt)) > 0])
    error_message = "finding_event_detail_types must contain at least one non-empty detail-type."
  }
}
