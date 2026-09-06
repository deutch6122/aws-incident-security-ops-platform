# module: waf

CloudFront に関連付ける `CLOUDFRONT` scope の AWS WAF Web ACL を定義する。
本モジュールは標準 `aws` provider のみを使用し、dev root が `aws.us_east_1` を module
provider mapping で注入する。別リージョンの provider が渡された場合は precondition で
停止する。

## 構成

- `AWSManagedRulesCommonRuleSet` を常時有効化
- `waf_additional_managed_rule_groups` で追加managed rule groupを明示指定（既定は空）
- CloudWatch metrics / sampled requestsを有効化
- WAF loggingは既定で有効。log group名はAWS要件どおり`aws-waf-logs-`で開始
- `Authorization`と`Cookie`をログからredact
- logging有効時はCloudWatch Logs resource policyを作成
- KMS暗号化は既定で有効。CloudWatch Logs serviceと対象log groupだけに利用を制限
- log retentionは`waf_log_retention_days`で指定（既定30日）

## 出力

- `web_acl_arn` / `web_acl_id`
- `waf_log_group_name`
- `waf_logs_kms_key_arn`

dev rootがus-east-1 providerを注入し、`web_acl_arn`をCloudFront moduleへ配線済みです。実AWSでのplan/applyとlogging確認はCategory Cです。
