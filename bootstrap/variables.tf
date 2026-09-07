# ---------------------------------------------------------------------------
# 変数定義
# ---------------------------------------------------------------------------
# 命名規則 ops-platform-dev-<resource>（project=ops-platform, env=dev）（Req 19.1）。
# ---------------------------------------------------------------------------

variable "aws_region" {
  description = "リソースを作成する AWS リージョン（Req 19.3）。"
  type        = string
  default     = "ap-northeast-1"
}

variable "project" {
  description = "プロジェクト識別子。命名規則 <project>-<env>-<resource> の project 部分（Req 19.1）。"
  type        = string
  default     = "ops-platform"
}

variable "env" {
  description = "環境識別子。dev 環境のみを対象とする（Req 24.1）。"
  type        = string
  default     = "dev"
}

# ---------------------------------------------------------------------------
# state lock 方式（Feedback 4 反映）
# ---------------------------------------------------------------------------
# 第一候補は S3 backend の `use_lockfile = true`（S3 ネイティブロック、Terraform v1.10+）。
# DynamoDB lock table は旧方式互換/代替案として「任意」で作成する。
# デフォルトでは作成しない（default=false）。
# ---------------------------------------------------------------------------
variable "enable_dynamodb_lock" {
  description = <<-EOT
    旧方式互換の DynamoDB state lock table を作成するかどうか（任意 / 代替案）。
    第一候補は S3 backend の use_lockfile=true（S3 ネイティブロック）であり、
    デフォルトでは DynamoDB lock table を作成しない。
    Terraform v1.10 未満の環境と互換をとる必要がある場合のみ true にする。
  EOT
  type        = bool
  default     = false
}

# ---------------------------------------------------------------------------
# CI/CD ソース設定（CodePipeline の Source ステージ用）
# ---------------------------------------------------------------------------
variable "source_repository_id" {
  description = "CodePipeline Source（CodeStar Connections）の接続先リポジトリ（例: <owner>/<repo>）。"
  type        = string
  default     = ""
}

variable "source_branch" {
  description = "Infra_Pipeline が追従するブランチ。main への merge/push で起動する（Req 21.2）。"
  type        = string
  default     = "main"
}

variable "codestar_connection_arn" {
  description = <<-EOT
    CodePipeline Source が使用する CodeStar Connections（GitHub 等）の ARN。
    接続の作成/承認はコンソールで一度だけ行う必要があるため、Bootstrap では
    ARN を変数で受け取る。未設定（空文字）の場合は接続を external として参照のみ想定。
  EOT
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# 追加タグ（任意）
# ---------------------------------------------------------------------------
variable "additional_tags" {
  description = "共通タグに加えて付与したい任意のタグ。"
  type        = map(string)
  default     = {}
}

variable "artifact_retention_days" {
  description = "Days to retain pipeline plans and Lambda package versions."
  type        = number
  default     = 30
}

variable "pipeline_alb_certificate_arn_parameter_name" {
  type    = string
  default = "/ops-platform/dev/alb-certificate-arn"
}

variable "pipeline_alb_ingress_cidrs_parameter_name" {
  description = "SSM parameter containing the approved JSON array of CIDRs allowed to reach the ALB."
  type        = string
  default     = "/ops-platform/dev/alb-ingress-cidrs"
}

variable "pipeline_eks_operator_principal_arn_parameter_name" {
  type    = string
  default = "/ops-platform/dev/eks-operator-principal-arn"
}

variable "pipeline_migration_launcher_principals_parameter_name" {
  type    = string
  default = "/ops-platform/dev/migration-launcher-principal-arns"
}

variable "pipeline_eks_public_access_cidrs_parameter_name" {
  type    = string
  default = "/ops-platform/dev/eks-public-access-cidrs"
}

variable "pipeline_application_image_tag_parameter_name" {
  description = "SSM parameter containing the immutable image tag used by ECS and the migration task definition."
  type        = string
  default     = "/ops-platform/dev/application-image-tag"
}

variable "pipeline_ecs_desired_count_parameter_name" {
  description = "SSM parameter containing the approved ECS desired count (0 before migration, 1 after migration)."
  type        = string
  default     = "/ops-platform/dev/ecs-desired-count"
}

variable "pipeline_cognito_callback_urls_parameter_name" {
  description = "SSM parameter containing the JSON array of approved Cognito callback URLs."
  type        = string
  default     = "/ops-platform/dev/cognito-callback-urls"
}

variable "pipeline_cognito_logout_urls_parameter_name" {
  description = "SSM parameter containing the JSON array of approved Cognito logout URLs."
  type        = string
  default     = "/ops-platform/dev/cognito-logout-urls"
}

variable "pipeline_cognito_keep_localhost_urls_parameter_name" {
  description = "SSM parameter containing whether localhost OAuth URLs remain enabled."
  type        = string
  default     = "/ops-platform/dev/cognito-keep-localhost-urls"
}

variable "pipeline_monitoring_enable_sns_subscription_parameter_name" {
  description = "SSM parameter containing whether the monitoring SNS subscription is enabled."
  type        = string
  default     = "/ops-platform/dev/monitoring-enable-sns-subscription"
}

variable "pipeline_monitoring_notification_parameter_name_parameter_name" {
  description = "SSM parameter whose value is the SSM parameter name containing the notification endpoint."
  type        = string
  default     = "/ops-platform/dev/monitoring-notification-parameter-name"
}

variable "pipeline_monitoring_notification_protocol_parameter_name" {
  description = "SSM parameter containing the SNS subscription protocol."
  type        = string
  default     = "/ops-platform/dev/monitoring-notification-protocol"
}
