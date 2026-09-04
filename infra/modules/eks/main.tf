data "aws_partition" "current" {}
data "aws_caller_identity" "current" {}

locals {
  cluster_name = "${var.name_prefix}-eks"

  # The Fargate built-in log router (aws-observability namespace + aws-logging
  # ConfigMap) writes worker logs to this CloudWatch Logs group. There is NO
  # Fluent Bit DaemonSet in this design; the k8s manifest configures the router
  # and this module owns the log group and the pod-execution-role logging grant.
  worker_log_group_name = coalesce(var.worker_log_group_name, "/${var.name_prefix}/eks/workers")

  # OIDC subject conditions restrict each IRSA role to a single ServiceAccount in
  # the worker namespace. aud is the standard STS audience.
  oidc_provider_bare_url = replace(aws_eks_cluster.this.identity[0].oidc[0].issuer, "https://", "")
  worker_sa_subject      = "system:serviceaccount:${var.worker_namespace}:${var.worker_service_account_name}"
  cronjob_sa_subject     = "system:serviceaccount:${var.worker_namespace}:${var.cronjob_service_account_name}"
}

# ---------------------------------------------------------------------------
# Control plane
# ---------------------------------------------------------------------------
resource "aws_eks_cluster" "this" {
  name     = local.cluster_name
  version  = var.cluster_version
  role_arn = aws_iam_role.cluster.arn

  vpc_config {
    subnet_ids              = var.private_subnet_ids
    security_group_ids      = [var.eks_security_group_id]
    endpoint_private_access = var.endpoint_private_access
    endpoint_public_access  = var.endpoint_public_access
    public_access_cidrs     = var.endpoint_public_access ? var.public_access_cidrs : null
  }

  enabled_cluster_log_types = var.enabled_cluster_log_types

  tags = merge(var.common_tags, {
    Name      = local.cluster_name
    Component = "eks"
    Role      = "control-plane"
  })

  depends_on = [
    aws_iam_role_policy_attachment.cluster_eks_cluster_policy,
  ]
}

resource "aws_iam_role" "cluster" {
  name = "${var.name_prefix}-eks-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-eks-cluster-role"
    Component = "eks"
    Role      = "control-plane-role"
  })
}

resource "aws_iam_role_policy_attachment" "cluster_eks_cluster_policy" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonEKSClusterPolicy"
}

# ---------------------------------------------------------------------------
# OIDC provider (IRSA foundation)
# ---------------------------------------------------------------------------
data "tls_certificate" "oidc" {
  url = aws_eks_cluster.this.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "this" {
  url             = aws_eks_cluster.this.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.oidc.certificates[0].sha1_fingerprint]

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-eks-oidc"
    Component = "eks"
    Role      = "oidc-provider"
  })
}

# ---------------------------------------------------------------------------
# Fargate pod execution role
#   Fargate pods pull images and stream logs through this role. It receives the
#   AWS-managed Fargate execution policy plus the CloudWatch Logs permissions
#   the built-in log router needs. Log resource is "*" because the router may
#   create/describe several log streams under the group and stream names are not
#   known before runtime.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "fargate_pod_execution" {
  name = "${var.name_prefix}-eks-fargate-exec-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "eks-fargate-pods.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-eks-fargate-exec-role"
    Component = "eks"
    Role      = "fargate-pod-execution"
  })
}

resource "aws_iam_role_policy_attachment" "fargate_pod_execution" {
  role       = aws_iam_role.fargate_pod_execution.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonEKSFargatePodExecutionRolePolicy"
}

# Logging permissions for the Fargate built-in log router (aws-observability
# aws-logging ConfigMap, output=cloudwatch_logs). No Fluent Bit DaemonSet.
resource "aws_iam_role_policy" "fargate_logging" {
  name = "${var.name_prefix}-eks-fargate-logging"
  role = aws_iam_role.fargate_pod_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:DescribeLogStreams",
        "logs:DescribeLogGroups",
        "logs:PutLogEvents",
        "logs:PutRetentionPolicy",
      ]
      # Log stream names are generated by the router at runtime, so this cannot
      # be narrowed to specific streams before creation. Scope is the region.
      Resource = "*"
    }]
  })
}

resource "aws_cloudwatch_log_group" "workers" {
  name              = local.worker_log_group_name
  retention_in_days = var.log_retention_days

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-eks-workers-logs"
    Component = "eks"
    Role      = "worker-logs"
  })
}

# ---------------------------------------------------------------------------
# Fargate profiles
#   workers: application pods (alarm/finding/cronjob)
#   kube-system: CoreDNS and core add-ons must run on Fargate
#   aws-observability: hosts the aws-logging ConfigMap for the built-in router
# ---------------------------------------------------------------------------
resource "aws_eks_fargate_profile" "workers" {
  cluster_name           = aws_eks_cluster.this.name
  fargate_profile_name   = "${var.name_prefix}-fp-workers"
  pod_execution_role_arn = aws_iam_role.fargate_pod_execution.arn
  subnet_ids             = var.private_subnet_ids

  selector {
    namespace = var.worker_namespace
  }

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-fp-workers"
    Component = "eks"
    Role      = "fargate-profile"
  })
}

resource "aws_eks_fargate_profile" "kube_system" {
  cluster_name           = aws_eks_cluster.this.name
  fargate_profile_name   = "${var.name_prefix}-fp-kube-system"
  pod_execution_role_arn = aws_iam_role.fargate_pod_execution.arn
  subnet_ids             = var.private_subnet_ids

  selector {
    namespace = "kube-system"
  }

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-fp-kube-system"
    Component = "eks"
    Role      = "fargate-profile"
  })
}

resource "aws_eks_fargate_profile" "aws_observability" {
  cluster_name           = aws_eks_cluster.this.name
  fargate_profile_name   = "${var.name_prefix}-fp-aws-observability"
  pod_execution_role_arn = aws_iam_role.fargate_pod_execution.arn
  subnet_ids             = var.private_subnet_ids

  selector {
    namespace = "aws-observability"
  }

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-fp-aws-observability"
    Component = "eks"
    Role      = "fargate-profile"
  })
}

# ---------------------------------------------------------------------------
# IRSA: eks-worker-role (Worker_Alarm / Worker_Finding)
#   Least privilege: SQS receive/delete on the worker queues, Secrets Manager
#   GetSecretValue on db_secret_arn only, CloudWatch Logs write.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "worker" {
  name = "${var.name_prefix}-eks-worker-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.this.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_provider_bare_url}:sub" = local.worker_sa_subject
          "${local.oidc_provider_bare_url}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-eks-worker-role"
    Component = "eks"
    Role      = "irsa-worker"
  })
}

resource "aws_iam_role_policy" "worker" {
  name = "${var.name_prefix}-eks-worker-policy"
  role = aws_iam_role.worker.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SqsReceiveDelete"
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:GetQueueUrl",
        ]
        Resource = var.sqs_queue_arns
      },
      {
        Sid      = "SecretsManagerReadDbCredential"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [var.db_secret_arn]
      },
      {
        Sid    = "CloudWatchLogsWrite"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams",
        ]
        Resource = ["${aws_cloudwatch_log_group.workers.arn}:*"]
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# IRSA: eks-cronjob-role (Cronjob_Summary)
#   Least privilege: Secrets Manager GetSecretValue on db_secret_arn only,
#   CloudWatch Logs write. Portal (S3/DynamoDB) write permissions belong to the
#   A->B linkage (Phase 3) and are intentionally NOT granted here. See README.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "cronjob" {
  name = "${var.name_prefix}-eks-cronjob-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.this.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_provider_bare_url}:sub" = local.cronjob_sa_subject
          "${local.oidc_provider_bare_url}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-eks-cronjob-role"
    Component = "eks"
    Role      = "irsa-cronjob"
  })
}

resource "aws_iam_role_policy" "cronjob" {
  name = "${var.name_prefix}-eks-cronjob-policy"
  role = aws_iam_role.cronjob.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "SecretsManagerReadDbCredential"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [var.db_secret_arn]
      },
      {
        Sid    = "CloudWatchLogsWrite"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams",
        ]
        Resource = ["${aws_cloudwatch_log_group.workers.arn}:*"]
      },
    ]
  })
}
