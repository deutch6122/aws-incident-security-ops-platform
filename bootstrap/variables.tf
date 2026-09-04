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
