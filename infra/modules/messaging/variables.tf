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

variable "queue_name_suffix" {
  description = "Suffix appended after name_prefix for the main queue and DLQ names."
  type        = string
  default     = "events"

  validation {
    condition     = can(regex("^[a-z0-9]+(-[a-z0-9]+)*$", var.queue_name_suffix)) && length(var.queue_name_suffix) <= 40
    error_message = "queue_name_suffix must use lowercase alphanumeric segments separated by single hyphens and be at most 40 characters."
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

variable "max_receive_count" {
  description = "Number of receive attempts before a message is moved to the DLQ (redrive maxReceiveCount)."
  type        = number
  default     = 5

  validation {
    condition     = var.max_receive_count >= 1 && var.max_receive_count <= 1000
    error_message = "max_receive_count must be between 1 and 1000."
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
  description = "Long-poll wait time on the main queue (0-20)."
  type        = number
  default     = 20

  validation {
    condition     = var.receive_wait_time_seconds >= 0 && var.receive_wait_time_seconds <= 20
    error_message = "receive_wait_time_seconds must be between 0 and 20."
  }
}

variable "sqs_managed_sse" {
  description = "Enable SSE-SQS (SQS-managed server-side encryption) on the main queue and DLQ. No customer key material is referenced."
  type        = bool
  default     = true
}

variable "eventbridge_event_pattern" {
  description = "EventBridge rule event pattern used to route sample events to the queue. Defaults to a source-based pattern for the platform sample events."
  type        = any
  default = {
    source = ["ops-platform.sample"]
  }

  validation {
    condition     = length(keys(var.eventbridge_event_pattern)) > 0
    error_message = "eventbridge_event_pattern must contain at least one matching key (for example source or detail-type)."
  }
}
