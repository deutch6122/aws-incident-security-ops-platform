output "cluster_name" {
  description = "Name of the EKS cluster."
  value       = aws_eks_cluster.this.name
}

output "cluster_arn" {
  description = "ARN of the EKS cluster."
  value       = aws_eks_cluster.this.arn
}

output "cluster_endpoint" {
  description = "API server endpoint of the EKS cluster."
  value       = aws_eks_cluster.this.endpoint
}

output "cluster_security_group_id" {
  description = "EKS-managed cluster security group ID. Fargate pods use this security group unless a SecurityGroupPolicy overrides it."
  value       = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}

output "cluster_oidc_issuer_url" {
  description = "OIDC issuer URL used to configure IRSA ServiceAccount trust."
  value       = aws_eks_cluster.this.identity[0].oidc[0].issuer
}

output "oidc_provider_arn" {
  description = "ARN of the IAM OIDC provider backing IRSA."
  value       = aws_iam_openid_connect_provider.this.arn
}

output "fargate_profile_arn" {
  description = "ARN of the workers Fargate profile."
  value       = aws_eks_fargate_profile.workers.arn
}

output "fargate_pod_execution_role_arn" {
  description = "ARN of the Fargate pod execution role (image pull + built-in log router logging)."
  value       = aws_iam_role.fargate_pod_execution.arn
}

output "alarm_worker_role_arn" {
  description = "ARN of the alarm worker IRSA role."
  value       = aws_iam_role.alarm_worker.arn
}

output "finding_worker_role_arn" {
  description = "ARN of the finding worker IRSA role."
  value       = aws_iam_role.finding_worker.arn
}

output "cronjob_role_arn" {
  description = "ARN of the eks-cronjob-role bound to the cronjob ServiceAccount via IRSA. Annotate the ServiceAccount with this ARN."
  value       = aws_iam_role.cronjob.arn
}

output "worker_log_group_name" {
  description = "CloudWatch Logs group name the aws-observability Fargate log router writes worker logs to."
  value       = aws_cloudwatch_log_group.workers.name
}
