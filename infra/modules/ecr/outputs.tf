output "repository_names" {
  description = "ECR repository names keyed by application component."
  value       = { for component, repository in aws_ecr_repository.this : component => repository.name }
}

output "repository_arns" {
  description = "ECR repository ARNs keyed by application component."
  value       = { for component, repository in aws_ecr_repository.this : component => repository.arn }
}

output "repository_urls" {
  description = "ECR repository URLs keyed by application component."
  value       = { for component, repository in aws_ecr_repository.this : component => repository.repository_url }
}
