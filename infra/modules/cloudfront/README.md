# module: cloudfront (Portal_CDN + OAC + WAF)

Product_B の配信基盤 Portal_CDN を定義する。CloudFront distribution（**PriceClass_200**、
S3 + API Gateway の 2 オリジン、HTTPS）、S3 用 OAC、CloudFront に関連付ける WAF
（AWS Managed Rules 1 つ以上 ＋ Rate-based rule）を含む。

- 対応要件: Req 12.1, 12.4, 13.1, 13.2, 13.3, 24.6
- 実装: Task 13.3

## 構成

- `aws_cloudfront_origin_access_control`（S3 用）: `signing_behavior=always`、
  `origin_access_control_origin_type=s3`、`signing_protocol=sigv4`
- `aws_cloudfront_distribution`: `price_class = "PriceClass_200"`（Req 24.6）、
  `web_acl_id` に WAF を関連付け（Req 13.1）
  - **2 オリジン**:
    1. S3 origin: `origin_access_control_id` で OAC を使用（Req 12.4）
    2. API Gateway origin: `custom_origin_config`（`origin_protocol_policy=https-only`）。
       ドメインは `api_gateway_origin_domain`（Task 14 で確定、既定は空プレースホルダ）
  - `default_cache_behavior` → S3 origin、`viewer_protocol_policy=redirect-to-https`
  - `/api/*` の `ordered_cache_behavior` → API Gateway origin、`viewer_protocol_policy=https-only`、
    TTL=0（動的・非キャッシュ）、`Authorization` ヘッダ転送
  - `viewer_certificate`: MVP は CloudFront デフォルト証明書（独自ドメイン+ACM は後続 Phase）
- `aws_wafv2_web_acl`（`scope = CLOUDFRONT`）:
  - **Managed Rules**: `AWSManagedRulesCommonRuleSet`（Req 13.2）
  - **Rate-based rule**: 送信元 IP 単位で `waf_rate_limit`（既定 2000/5 分）超過をブロック（Req 13.3）

## WAF provider（scope=CLOUDFRONT）に関する注意

`scope = CLOUDFRONT` の WAFv2 Web ACL は **us-east-1** で作成する必要がある。dev root で
本モジュールを呼び出す際に us-east-1 の provider alias を渡す想定
（例: `providers = { aws = aws.us_east_1 }`）。本モジュールは合成可能性のため内部で
alias を強制しない。配線時に呼び出し側で us-east-1 provider を渡すこと。

## HTTPS 前提（Req 12.1）

全 viewer behavior を HTTPS で配信する。デフォルト（S3）は `redirect-to-https`、
`/api/*` は `https-only`。API Gateway origin への接続も `https-only`。

## Product_A / Product_B 分離

CloudFront は Product_A へ**直接接続しない**。オリジンは Product_B の S3 バケットと
Product_B の API Gateway のみで、Aurora/RDS/EKS/ECS のオリジンは作らない。S3 バケット
ポリシー（s3-portal モジュール）は `distribution_arn` を `AWS:SourceArn` 条件で受け取り、
本 distribution の OAC 経由のみ S3 読取を許可する。

## 変数

- `name_prefix`（必須）/ `common_tags`（必須）
- `s3_origin_domain_name`（必須、s3-portal の `bucket_regional_domain_name`）
- `api_gateway_origin_domain`（既定 `""` プレースホルダ、Task 14 で解決）
- `price_class`（既定 `PriceClass_200`。代替 `PriceClass_100`）
- `waf_rate_limit`（既定 2000）

## 出力

- `distribution_id` / `distribution_arn`（s3-portal の SourceArn 条件へ渡す）
- `distribution_domain_name`
- `oac_id`
- `web_acl_arn`
- `price_class`

## dev root への配線について（後続依存）

`infra/environments/dev` への配線は、API Gateway（Task 14）と s3-portal（Task 13.2、
S3 origin ドメイン）、us-east-1 provider alias 確定後に行う。既存モジュールと同じ
「実装したものだけ配線」方針に従い、Task 13 時点では dev ルートへは配線しない。

## テスト

`tests/test_cloudfront_snapshot.py` は Terraform/AWS を実行しない静的テスト。2 オリジン・
PriceClass_200・S3 origin の OAC 使用・`viewer_protocol_policy` が HTTPS・WAF の Managed
Rules ＋ Rate-based rule 各 1 つ以上・distribution への WAF 関連付け・命名/タグ・
Product_A 非参照・機微/実ドメイン非混入を検証する。
