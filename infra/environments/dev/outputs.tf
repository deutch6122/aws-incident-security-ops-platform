output "name_prefix" {
  description = "Canonical prefix for dev resource names."
  value       = local.name_prefix
}

output "common_tags" {
  description = "Non-sensitive required and additional tags used by the AWS provider."
  value       = local.common_tags
}

output "aws_region" {
  description = "AWS Region configured for this dev root."
  value       = var.aws_region
}

output "resource_names" {
  description = "Validated resource names generated from resource_name_suffixes."
  value       = local.resource_names
}

output "network" {
  description = "Non-sensitive network identifiers for later platform modules."
  value = {
    vpc_id                 = module.network.vpc_id
    public_subnet_ids      = module.network.public_subnet_ids
    private_app_subnet_ids = module.network.private_app_subnet_ids
    isolated_db_subnet_ids = module.network.isolated_db_subnet_ids
    security_group_ids     = module.network.security_group_ids
    nat_gateway_id         = module.network.nat_gateway_id
  }
}

output "ecr_repository_urls" {
  description = "ECR repository URLs keyed by deployable component."
  value       = module.ecr.repository_urls
}

output "pipeline_contract" {
  description = "Static dev inputs that must remain aligned with bootstrap CodeBuild/backend configuration."
  value = {
    tf_workdir  = var.pipeline_tf_workdir
    backend_key = var.pipeline_backend_key
  }
}

output "aurora" {
  description = "Non-secret Aurora connection metadata for operations and verification."
  value = {
    cluster_arn      = module.aurora.cluster_arn
    cluster_id       = module.aurora.cluster_id
    cluster_endpoint = module.aurora.cluster_endpoint
    writer_endpoint  = module.aurora.writer_endpoint
    port             = module.aurora.port
    database_name    = module.aurora.database_name
  }
}

output "ecs_deployment" {
  description = "Non-sensitive values required by ECS application and migration deployment steps."
  value = {
    cluster_name                = module.ecs.cluster_name
    service_name                = module.ecs.service_name
    migration_cluster_arn       = module.ecs.migration_cluster_arn
    migration_task_definition   = module.ecs.migration_task_definition_arn
    migration_launcher_role_arn = module.iam.migration_launcher_role_arn
    private_subnet_ids          = values(module.network.private_app_subnet_ids)
    migration_security_group_id = module.network.security_group_ids.migration
  }
}

output "eks_deployment" {
  description = "Non-sensitive EKS identifiers and workload role ARNs used to render and deploy manifests."
  value = {
    cluster_name            = module.eks.cluster_name
    worker_log_group_name   = module.eks.worker_log_group_name
    alarm_worker_role_arn   = module.eks.alarm_worker_role_arn
    finding_worker_role_arn = module.eks.finding_worker_role_arn
    cronjob_role_arn        = module.eks.cronjob_role_arn
  }
}

output "messaging" {
  description = "Queue identifiers required by sample-data and operational verification."
  value = {
    alarm_queue_url   = module.messaging.alarm_queue_url
    alarm_dlq_url     = module.messaging.alarm_dlq_url
    finding_queue_url = module.messaging.finding_queue_url
    finding_dlq_url   = module.messaging.finding_dlq_url
  }
}

output "portal_deployment" {
  description = "Non-sensitive Product_B identifiers used for frontend config, deployment, and sample data."
  value = {
    s3_bucket_name                 = module.s3_portal.bucket_name
    cloudfront_distribution_id     = module.cloudfront.distribution_id
    cloudfront_distribution_domain = module.cloudfront.distribution_domain_name
    api_endpoint                   = module.apigateway.api_endpoint
    cognito_user_pool_id           = module.cognito.user_pool_id
    cognito_app_client_id          = module.cognito.app_client_id
    cognito_issuer_url             = module.cognito.issuer_url
    cognito_hosted_domain          = module.cognito.hosted_domain
    public_status_table_name       = module.dynamodb.public_status_items_table_name
    report_metadata_table_name     = module.dynamodb.report_metadata_table_name
  }
}

output "monitoring" {
  description = "Non-sensitive monitoring destinations and dashboards."
  value = {
    sns_topic_arn       = module.monitoring.sns_topic_arn
    product_a_dashboard = module.monitoring.product_a_dashboard_name
    product_b_dashboard = module.monitoring.product_b_dashboard_name
  }
}
