# ---------------------------------------------------------------------------
# 共通 locals（命名規則 helper / 共通タグ）
# ---------------------------------------------------------------------------
# 命名規則: ops-platform-dev-<resource>（^ops-platform-dev-.+）（Req 19.1, Property 11）。
# name_prefix を用いて各リソース名を `${local.name_prefix}-<resource>` で生成する。
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

locals {
  # 命名 prefix。例: ops-platform-dev
  name_prefix = "${var.project}-${var.env}"

  # 共通タグ（全リソースへ default_tags 経由で付与）（Req 19.2）。
  common_tags = merge(
    {
      Project   = var.project
      Env       = var.env
      Platform  = "aws-incident-security-ops-platform"
      ManagedBy = "terraform"
      Stack     = "bootstrap"
    },
    var.additional_tags,
  )

  account_id = data.aws_caller_identity.current.account_id

  # state 用 S3 バケット名（グローバル一意化のため account_id を付与）。
  # 例: ops-platform-dev-tfstate-123456789012
  state_bucket_name = "${local.name_prefix}-tfstate-${local.account_id}"

  # artifact 用 S3 バケット名。
  # 例: ops-platform-dev-cicd-artifacts-123456789012
  artifact_bucket_name = "${local.name_prefix}-cicd-artifacts-${local.account_id}"
}
