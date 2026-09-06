# module: cloudfront (Portal_CDN + OAC)

Product_B の配信基盤 Portal_CDN を定義する。CloudFront distribution（**PriceClass_200**、
S3 + API Gateway の 2 オリジン、HTTPS）、S3 用 OAC、CloudFront に関連付ける WAF
を含む。WAFは`infra/modules/waf`が所有し、そのARNを入力として受ける。

- 対応要件: Req 12.1, 12.4, 13.1, 13.2, 13.3, 24.6
- 実装: Task 13.3

## 構成

- `aws_cloudfront_origin_access_control`（S3 用）: `signing_behavior=always`、
  `origin_access_control_origin_type=s3`、`signing_protocol=sigv4`
- `aws_cloudfront_distribution`: `price_class = "PriceClass_200"`（Req 24.6）、
  `web_acl_id = var.web_acl_arn` でWAF module出力を関連付け
  - **2 オリジン**:
    1. S3 origin: `origin_access_control_id` で OAC を使用（Req 12.4）
    2. API Gateway origin: `custom_origin_config`（`origin_protocol_policy=https-only`）。
       ドメインは必須入力`api_gateway_origin_domain`
  - `default_cache_behavior` → S3 origin、`viewer_protocol_policy=redirect-to-https`
  - `/api/*` の `ordered_cache_behavior` → API Gateway origin、path rewriteなし、
    `viewer_protocol_policy=redirect-to-https`、全methodを許可、AWS管理ポリシー
    `CachingDisabled` / `AllViewerExceptHostHeader`を使用
  - `viewer_certificate`: MVP は CloudFront デフォルト証明書（独自ドメイン+ACM は後続 Phase）
WAF resourceは本moduleに作成しない。`infra/modules/waf`をdev rootから
`providers = { aws = aws.us_east_1 }`で呼び、その`web_acl_arn`を本moduleへ渡す。

## HTTPS 前提（Req 12.1）

全 viewer behavior を HTTPS で配信する。デフォルト（S3）は `redirect-to-https`、
`/api/*` も `redirect-to-https`。API Gateway origin への接続は`https-only`。

## Product_A / Product_B 分離

CloudFront は Product_A へ**直接接続しない**。オリジンは Product_B の S3 バケットと
Product_B の API Gateway のみで、Aurora/RDS/EKS/ECS のオリジンは作らない。S3 バケット
ポリシー（s3-portal モジュール）は `distribution_arn` を `AWS:SourceArn` 条件で受け取り、
本 distribution の OAC 経由のみ S3 読取を許可する。

## 変数

- `name_prefix`（必須）/ `common_tags`（必須）
- `s3_origin_domain_name`（必須、s3-portal の `bucket_regional_domain_name`）
- `api_gateway_origin_domain`（必須、apigatewayの`api_domain_name`）
- `web_acl_arn`（必須、waf moduleの`web_acl_arn`）
- `price_class`（既定 `PriceClass_200`。代替 `PriceClass_100`）

## 出力

- `distribution_id` / `distribution_arn`（s3-portal の SourceArn 条件へ渡す）
- `distribution_domain_name`
- `oac_id`
- `price_class`

## dev root 配線

dev rootはs3-portalのregional domain、API Gateway endpoint、us-east-1のWAF ARNを本moduleへ配線済みです。OAC bucket policyはdistribution ARNを参照してdev rootが所有し、s3-portalとの循環を避けます。

## テスト

`tests/test_cloudfront_snapshot.py` は Terraform/AWS を実行しない静的テスト。2 オリジン・
PriceClass_200・S3 origin の OAC 使用・`viewer_protocol_policy` が HTTPS・API behaviorの
管理ポリシー・外部WAF ARNの関連付け・命名/タグ・
Product_A 非参照・機微/実ドメイン非混入を検証する。
