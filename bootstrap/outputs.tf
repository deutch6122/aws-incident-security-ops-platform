# ---------------------------------------------------------------------------
# outputs
# ---------------------------------------------------------------------------

# --- state 関連 --------------------------------------------------------------
output "state_bucket_name" {
  description = "remote state 用 S3 バケット名（infra/environments/dev の backend.bucket に指定）。"
  value       = aws_s3_bucket.tfstate.bucket
}

output "state_bucket_arn" {
  description = "remote state 用 S3 バケット ARN。"
  value       = aws_s3_bucket.tfstate.arn
}

output "dynamodb_lock_table_name" {
  description = <<-EOT
    （任意 / 代替案）DynamoDB state lock table 名。
    var.enable_dynamodb_lock=false（デフォルト）の場合は null。
    第一候補は S3 backend の use_lockfile=true のため通常は不要。
  EOT
  value       = var.enable_dynamodb_lock ? aws_dynamodb_table.tfstate_lock[0].name : null
}

# --- CI/CD 関連 --------------------------------------------------------------
output "artifact_bucket_name" {
  description = "CI/CD artifact 用 S3 バケット名。"
  value       = aws_s3_bucket.artifacts.bucket
}

output "codebuild_project_name" {
  description = "Terraform 実行用 CodeBuild プロジェクト名。"
  value       = aws_codebuild_project.terraform.name
}

output "codepipeline_name" {
  description = "Infra_Pipeline（CodePipeline）名。"
  value       = aws_codepipeline.infra.name
}

output "terraform_exec_role_arn" {
  description = "terraform-exec IAM Role ARN（CodeBuild が assume して Terraform を実行）。"
  value       = aws_iam_role.terraform_exec.arn
}
