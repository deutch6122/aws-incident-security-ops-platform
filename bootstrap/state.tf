# ---------------------------------------------------------------------------
# remote state 用 S3 バケット + （任意）DynamoDB state lock table
# ---------------------------------------------------------------------------
# 対応要件: Req 20.3, 20.4, 21.1
#
# state lock 方式（Feedback 4 反映 / docs/architecture/terraform-backend-design.md）:
#   第一候補: S3 backend の `use_lockfile = true`（S3 ネイティブロック、Terraform v1.10+）。
#             → backend 設定側のオプションであり、ここで作成する S3 バケットのみで成立する。
#             → 例は infra/environments/dev/backend.tf.example（use_lockfile = true）参照。
#   代替案  : DynamoDB lock table（旧方式互換）。var.enable_dynamodb_lock=true のときのみ作成。
#             デフォルト（false）では作成しない。
# ---------------------------------------------------------------------------

# --- remote state 用 S3 バケット ----------------------------------------------
resource "aws_s3_bucket" "tfstate" {
  bucket = local.state_bucket_name

  tags = {
    Name = "${local.name_prefix}-tfstate"
    Role = "terraform-remote-state"
  }
}

# バージョニング有効（誤削除/巻き戻し対応）（Req 20.4）。
resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

# サーバーサイド暗号化（SSE）。デフォルトは AES256（SSE-S3）。
# 必要に応じて aws:kms + kms_master_key_id へ切り替え可能（コメント参照）（Req 20.4）。
resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
      # aws:kms を使う場合の例:
      # sse_algorithm     = "aws:kms"
      # kms_master_key_id = aws_kms_key.tfstate.arn
    }
    bucket_key_enabled = true
  }
}

# public access block 全項目 true（Req 20.4）。
resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --- （任意 / 代替案）DynamoDB state lock table -------------------------------
# 第一候補は S3 backend の use_lockfile=true。本テーブルは旧方式互換の代替案であり、
# var.enable_dynamodb_lock=true のときのみ作成する（default=false → 作成しない）。
resource "aws_dynamodb_table" "tfstate_lock" {
  count = var.enable_dynamodb_lock ? 1 : 0

  name         = "${local.name_prefix}-tfstate-lock"
  billing_mode = "PAY_PER_REQUEST" # dev/MVP のコスト最適化（Req 24.5 に整合）
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = {
    Name = "${local.name_prefix}-tfstate-lock"
    Role = "terraform-state-lock-legacy"
  }
}
