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

variable "cluster_version" {
  description = "EKS control plane Kubernetes version, for example 1.30."
  type        = string
  default     = "1.30"

  validation {
    condition     = can(regex("^1\\.(2[6-9]|3[0-9])$", var.cluster_version))
    error_message = "cluster_version must be a supported EKS minor version such as 1.28, 1.29, or 1.30."
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

# Worker SQS queue ARNs. These are placeholders wired once the messaging module
# (Task 11) publishes real queue ARNs. The eks-worker-role is scoped to receive
# and delete on exactly these ARNs.
variable "sqs_queue_arns" {
  description = "SQS queue ARNs the worker role may receive from and delete on (messaging module output). Placeholders until Task 11 wiring."
  type        = list(string)

  validation {
    condition     = length(var.sqs_queue_arns) >= 1 && alltrue([for arn in var.sqs_queue_arns : can(regex("^arn:aws[a-z-]*:sqs:", arn))])
    error_message = "sqs_queue_arns must each be a valid SQS queue ARN."
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

variable "worker_service_account_name" {
  description = "ServiceAccount name bound to eks-worker-role via the OIDC trust policy sub condition."
  type        = string
  default     = "eks-worker"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", var.worker_service_account_name))
    error_message = "worker_service_account_name must be a valid Kubernetes ServiceAccount name."
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

variable "public_access_cidrs" {
  description = "CIDR blocks allowed to reach the public API endpoint when endpoint_public_access is true. Restrict to reviewed operator ranges."
  type        = list(string)
  default     = ["0.0.0.0/0"]

  validation {
    condition     = alltrue([for cidr in var.public_access_cidrs : can(cidrhost(cidr, 0))])
    error_message = "public_access_cidrs must each be a valid CIDR block."
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
