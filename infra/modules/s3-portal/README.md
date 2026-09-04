# module: s3-portal (Portal_Storage)

Product_B の静的サイト/月次レポートファイルを格納する Portal_Storage 用 S3 バケットを
定義する。バケットは**直接 public 公開しない**。読み取りは CloudFront の **OAC 経由のみ**
許可する（Requirement 12.2, 12.3）。

- 対応要件: Req 12.2, 12.3（付随: Req 12.1 配信は cloudfront モジュール、Req 14.1 の
  `reports/*` 配置は Cronjob_Summary）
- 実装: Task 13.2

## 構成

- `aws_s3_bucket`（`<name_prefix>-portal-storage`、`common_tags` 付与）
- `aws_s3_bucket_ownership_controls`: `BucketOwnerEnforced`（ACL 無効化）
- `aws_s3_bucket_public_access_block`: **4 項目すべて true**
  （`block_public_acls` / `block_public_policy` / `ignore_public_acls` /
  `restrict_public_buckets`）
- `aws_s3_bucket_server_side_encryption_configuration`: SSE-S3（AES256）
- `aws_s3_bucket_versioning`: 有効
- `aws_s3_bucket_policy` + `aws_iam_policy_document`: **OAC 専用ポリシー**

## OAC 専用バケットポリシー

`s3:GetObject` を **`cloudfront.amazonaws.com` サービスプリンシパル**に対してのみ許可し、
さらに **`AWS:SourceArn` 条件**で対象 CloudFront distribution（`cloudfront_distribution_arn`）
からの要求に限定する。OAC 以外の要求（直接 public アクセスを含む）はこの Allow に一致
しないため拒否される（Requirement 12.3）。public な `*` プリンシパルは存在せず、ACL は
`BucketOwnerEnforced` で無効化しているため ACL 経由の公開も不可（private 相当）。

実 ARN はコミットしない。`cloudfront_distribution_arn` は dev root で cloudfront モジュール
出力（Task 13.3）を渡し、既定は検証用の空プレースホルダ。

## `reports/*` プレフィックス

月次レポートファイルは `reports_prefix`（既定 `reports/`）配下に配置する。実際の配置・
`report_metadata` 登録・`public_status_items` 反映は A→B 一方向連携の実行主体である
Cronjob_Summary（Task 16.2）が行う。本モジュールはプレフィックスの取り決め（変数＋出力）
のみを提供し、書込主体は定義しない。

## Product_A / Product_B 分離

本モジュールは Product_B 専用。Aurora/RDS/EKS/ECS/SQS への参照・依存・書込権限を
持たない。バケットへの `reports/*` 書込は Product_A の Cronjob_Summary（Task 16.2）が
IAM ロール経由で行う予定で、本モジュールでは定義しない。

## 変数

- `name_prefix`（必須）/ `common_tags`（必須）
- `cloudfront_distribution_arn`（既定 `""` プレースホルダ）
- `reports_prefix`（既定 `reports/`）
- `force_destroy`（既定 false）

## 出力

- `bucket_name` / `bucket_arn` / `bucket_regional_domain_name`（CloudFront S3 origin 用）
- `reports_prefix`

## dev root への配線について（後続依存）

`infra/environments/dev` への配線は cloudfront（Task 13.3、`cloudfront_distribution_arn`
の解決）と A→B 連携（Task 16.2）確定後に行う。既存モジュールと同じ「実装したものだけ
配線」方針に従い、Task 13 時点では dev ルートへは配線しない。

## テスト

`tests/test_s3_portal_snapshot.py` は Terraform/AWS を実行しない静的テスト。public
access block 全 true・OAC 専用ポリシー（`cloudfront.amazonaws.com` ＋ `AWS:SourceArn`
条件、public `*` なし）・`reports/*` 記載・命名/タグ・Product_A 非参照・機微/実 ARN
非混入を検証する。
