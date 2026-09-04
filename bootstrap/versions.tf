# ---------------------------------------------------------------------------
# Terraform / provider バージョン制約
# ---------------------------------------------------------------------------
# state lock 方式（Feedback 4 反映）:
#   S3 backend の `use_lockfile = true`（S3 ネイティブロック）を第一候補とするため、
#   Terraform v1.10 以降を前提とする。DynamoDB lock table は旧方式互換/代替案
#   （var.enable_dynamodb_lock、default=false）で任意作成とする。
#   詳細は docs/architecture/terraform-backend-design.md 参照。
# 対応要件: Req 20.3, 20.4, 21.1
# ---------------------------------------------------------------------------

terraform {
  # `use_lockfile = true`（S3 ネイティブロック）は Terraform v1.10 以降が前提。
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # -------------------------------------------------------------------------
  # Bootstrap 自身の state について:
  #   本 Bootstrap_Stack は「remote state 用 S3 / CI/CD 土台 / terraform-exec-role」
  #   を作成するスタックであり、鶏卵問題を避けるため初回はローカル state で apply する
  #   （remote backend をここでは設定しない）。
  #   作成後に必要であれば、生成された state バケットへ `terraform init -migrate-state`
  #   で移行できる。移行時の backend 例は下記コメントおよび
  #   infra/environments/dev/backend.tf.example（`use_lockfile = true`）を参照。
  #
  # backend "s3" {
  #   bucket       = "ops-platform-dev-tfstate-<account_id>"
  #   key          = "bootstrap/terraform.tfstate"
  #   region       = "ap-northeast-1"
  #   encrypt      = true
  #   use_lockfile = true # 第一候補: S3 ネイティブロック（Terraform v1.10+）
  # }
  # -------------------------------------------------------------------------
}
