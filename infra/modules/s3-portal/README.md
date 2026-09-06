# module: s3-portal (Portal_Storage)

Product_B の静的サイト/月次レポートファイルを格納する Portal_Storage 用 S3 バケットの
**基盤のみ**を定義する。バケットは**直接 public 公開しない**。読み取りは CloudFront の
**OAC 経由のみ**許可する（Requirement 12.2, 12.3）。

- 対応要件: Req 12.2, 12.3（付随: Req 12.1 配信は cloudfront モジュール、Req 14.1 の
  `reports/*` 配置は Cronjob_Summary）

## 所有境界（重要）

- **本モジュールは S3 bucket 基盤だけを所有する。**
- CloudFront distribution は **Task 22** が所有する。
- OAC bucket policy は **Task 27 の dev root** が所有する（bucket policy は本モジュール内で
  作成しない）。
- これにより s3-portal と cloudfront の循環依存を作らない。CloudFront ARN は本モジュールへ
  入力しない（`cloudfront_distribution_arn` 変数は存在しない）。

## 構成

- `aws_s3_bucket`（後述の決定的命名、`common_tags` 付与）
- `aws_s3_bucket_ownership_controls`: `BucketOwnerEnforced`（ACL 無効化）
- `aws_s3_bucket_public_access_block`: **4 項目すべて true**
  （`block_public_acls` / `block_public_policy` / `ignore_public_acls` /
  `restrict_public_buckets`）
- `aws_s3_bucket_server_side_encryption_configuration`: SSE-S3（AES256）
- `aws_s3_bucket_versioning`: 有効

`aws_s3_bucket_policy` および OAC 用 `aws_iam_policy_document` は**本モジュールに存在しない**。
OAC bucket policy は Task 27 の dev root で作成する。

## バケット命名（決定的・一意・63 字以内）

実値をコードに埋め込まず、次から生成する。

- suffix = `${data.aws_caller_identity.current.account_id}-${var.aws_region}`
- stem source = `${var.name_prefix}-portal-storage`
- stem 最大長 = `63 - 1 - length(suffix)`
- stem を最大長で切り詰め、末尾の `-` を除去
- 最終名 = `${stem}-${suffix}`

名前の末尾には必ず完全な形で `<account-id>-<region>` を含める。63 字を超えないよう、
suffix ではなく **stem 側だけ**を決定的に切り詰める。account id は data source から取得し、
ファイルやテストに固定値として記載しない。`aws_region` は空文字を validation で拒否する。

## `reports/*` プレフィックス

月次レポートファイルは `reports_prefix`（既定 `reports/`）配下に配置する。実際の配置・
`report_metadata` 登録・`public_status_items` 反映は A→B 一方向連携の実行主体である
Cronjob_Summary（Task 16.2）が行う。本モジュールはプレフィックスの取り決め（変数＋出力）
のみを提供し、書込主体は定義しない。

## Product_A / Product_B 分離

本モジュールは Product_B 専用。Aurora/RDS/EKS/ECS/SQS への参照・依存・書込権限を
持たない。

## 変数

- `name_prefix`（必須）/ `common_tags`（必須）
- `aws_region`（必須、空文字拒否）
- `reports_prefix`（既定 `reports/`）
- `force_destroy`（既定 false）

## 出力

- `bucket_name` / `bucket_arn` / `bucket_regional_domain_name`（CloudFront S3 origin 用）
- `reports_prefix`

## dev root 配線

dev rootへ配線済みです。CloudFront distribution ARNを参照するOAC bucket policyはdev rootが作成し、本moduleへ逆参照を作らないため依存グラフは循環しません。

## テスト

`tests/test_s3_portal_snapshot.py` は Terraform/AWS を実行しない静的テスト。account id と
region を suffix に使用し stem 側を切り詰めること（suffix 自体は切り詰めない）、bucket 名が
63 字以内になる式であること、bucket policy resource が本モジュールに存在しないこと、
`cloudfront_distribution_arn` 変数が存在しないこと、public access block 全 true・SSE と
versioning 有効・必要 output・Product_A 非参照・機微/実 ARN 非混入を検証する。Task 21.1 の
Hypothesis property test は別途。

## 検証分類

- Category A（本 Task で必須）: 上記静的テスト、`terraform validate`。
- Category C（保留）: 実 plan での bucket 一意性（Req 16.4）。
