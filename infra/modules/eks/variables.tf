variable "name_prefix" {
  description = "Prefix for EKS resource names, for example ops-platform-dev."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]+(-[a-z0-9]+)*$", var.name_prefix)) && length(var.name_prefix) <= 40
    error_message = "name_prefix must use lowercase alphanumeric segments separated by single hyphens and be at most 40 characters."
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

variable "eks_kubernetes_version" {
  description = "EKS control-plane Kubernetes version. Reconfirm standard support immediately before apply."
  type        = string
  default     = "1.36"

  validation {
    condition     = can(regex("^1\\.[0-9]{2}$", var.eks_kubernetes_version))
    error_message = "eks_kubernetes_version must be a Kubernetes minor version such as 1.36."
  }
}

variable "private_subnet_ids" {
  description = "Private application subnet IDs for the control plane ENIs and Fargate pods. Fargate pods run only in private subnets. Accepts the network module's private_app_subnet_ids values."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2 && length(distinct(var.private_subnet_ids)) == length(var.private_subnet_ids)
    error_message = "private_subnet_ids must contain at least two distinct private application subnet IDs (multi-AZ)."
  }
}

variable "eks_security_group_id" {
  description = "Security group attached to the cluster's control plane ENIs, for example the network module's security_group_ids.eks."
  type        = string

  validation {
    condition     = can(regex("^sg-[0-9a-f]+$", var.eks_security_group_id))
    error_message = "eks_security_group_id must be a valid sg-<hex> identifier."
  }
}

# ARN reference only. The secret VALUE, DB password, and full connection URL are
# never placed in this module. The worker/cronjob IRSA roles are granted
# secretsmanager:GetSecretValue on exactly this ARN.
variable "db_secret_arn" {
  description = "Secrets Manager ARN of the database credential (for example aurora app_database_secret_arn). ARN reference only; the secret value is never stored here."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:secretsmanager:", var.db_secret_arn))
    error_message = "db_secret_arn must be a valid Secrets Manager ARN; never a secret value or connection string."
  }
}

# Each worker receives one queue ARN. Its IRSA policy is scoped to receive and
# delete messages from only that workload's queue.
variable "alarm_queue_arn" {
  description = "Alarm queue ARN consumed only by the alarm worker."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:sqs:", var.alarm_queue_arn))
    error_message = "alarm_queue_arn must be a valid SQS queue ARN."
  }
}

variable "finding_queue_arn" {
  description = "Finding queue ARN consumed only by the finding worker."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:sqs:", var.finding_queue_arn))
    error_message = "finding_queue_arn must be a valid SQS queue ARN."
  }
}

variable "worker_namespace" {
  description = "Kubernetes namespace where worker/cronjob pods run and to which the IRSA trust policy is scoped."
  type        = string
  default     = "workers"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", var.worker_namespace))
    error_message = "worker_namespace must be a valid Kubernetes namespace label."
  }
}

variable "alarm_worker_service_account_name" {
  description = "ServiceAccount bound only to the alarm worker IRSA role."
  type        = string
  default     = "eks-alarm-worker"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", var.alarm_worker_service_account_name))
    error_message = "alarm_worker_service_account_name must be a valid Kubernetes ServiceAccount name."
  }
}

variable "finding_worker_service_account_name" {
  description = "ServiceAccount bound only to the finding worker IRSA role."
  type        = string
  default     = "eks-finding-worker"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", var.finding_worker_service_account_name))
    error_message = "finding_worker_service_account_name must be a valid Kubernetes ServiceAccount name."
  }
}

variable "cronjob_service_account_name" {
  description = "ServiceAccount name bound to eks-cronjob-role via the OIDC trust policy sub condition."
  type        = string
  default     = "eks-cronjob"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", var.cronjob_service_account_name))
    error_message = "cronjob_service_account_name must be a valid Kubernetes ServiceAccount name."
  }
}

variable "endpoint_private_access" {
  description = "Whether the cluster API server endpoint is reachable from within the VPC."
  type        = bool
  default     = true
}

variable "endpoint_public_access" {
  description = "Whether the cluster API server endpoint is reachable from the public internet. Kept for dev/MVP administration; production should restrict or disable."
  type        = bool
  default     = true
}

variable "eks_public_access_cidrs" {
  description = "CIDR blocks allowed to reach the public API endpoint when endpoint_public_access is true. Restrict to reviewed operator ranges."
  type        = list(string)

  validation {
    condition = (
      length(var.eks_public_access_cidrs) > 0 &&
      alltrue([for cidr in var.eks_public_access_cidrs : can(cidrhost(cidr, 0))]) &&
      !contains(var.eks_public_access_cidrs, "0.0.0.0/0") &&
      !contains(var.eks_public_access_cidrs, "::/0")
    )
    error_message = "eks_public_access_cidrs must be a non-empty valid CIDR list and must not contain 0.0.0.0/0 or ::/0."
  }
}

variable "eks_operator_principal_arn" {
  description = "Reviewed IAM principal ARN used by the dev root access entry in Task 27."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:(role|user)/", var.eks_operator_principal_arn))
    error_message = "eks_operator_principal_arn must be an IAM role or user ARN."
  }
}

variable "portal_reports_bucket_arn" {
  description = "Portal S3 bucket ARN; cronjob may write only under reports/*."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:s3:::", var.portal_reports_bucket_arn))
    error_message = "portal_reports_bucket_arn must be a valid S3 bucket ARN."
  }
}

variable "report_metadata_table_arn" {
  description = "DynamoDB report_metadata table ARN writable by the summary cronjob."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:dynamodb:", var.report_metadata_table_arn))
    error_message = "report_metadata_table_arn must be a valid DynamoDB table ARN."
  }
}

variable "public_status_items_table_arn" {
  description = "DynamoDB public_status_items table ARN writable by the summary cronjob."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:dynamodb:", var.public_status_items_table_arn))
    error_message = "public_status_items_table_arn must be a valid DynamoDB table ARN."
  }
}

variable "enabled_cluster_log_types" {
  description = "EKS control plane log types exported to CloudWatch Logs."
  type        = list(string)
  default     = ["api", "audit", "authenticator", "controllerManager", "scheduler"]

  validation {
    condition     = length(setsubtract(toset(var.enabled_cluster_log_types), toset(["api", "audit", "authenticator", "controllerManager", "scheduler"]))) == 0
    error_message = "enabled_cluster_log_types must be a subset of api, audit, authenticator, controllerManager, scheduler."
  }
}

variable "log_retention_days" {
  description = "Retention for the worker CloudWatch Logs group that the Fargate built-in log router writes to."
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90], var.log_retention_days)
    error_message = "log_retention_days must be a supported CloudWatch Logs retention value."
  }
}

variable "worker_log_group_name" {
  description = "CloudWatch Logs group name the aws-observability Fargate log router writes worker logs to. Aligns with the k8s aws-logging ConfigMap output."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.worker_log_group_name == null || can(regex("^/[A-Za-z0-9._/-]+$", var.worker_log_group_name))
    error_message = "worker_log_group_name must be null or a valid CloudWatch Logs group path beginning with a slash."
  }
}
