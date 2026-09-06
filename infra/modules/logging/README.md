# module: logging（VPC Flow Logs 所有）

VPC Flow Logs を CloudWatch Logs へ集約するための専用ログ基盤を所有する（Req 21）。
ログ所有境界を厳守し、他モジュールが所有するロググループは本モジュールで作成しない。

## ロググループ所有権（単一所有・重複作成しない）

| ログ対象 | ロググループ | 所有モジュール |
| --- | --- | --- |
| ECS backend-api | `/ecs/<name_prefix>-backend-api` | **ecs モジュール** |
| EKS worker | `/<name_prefix>/eks/workers` | **eks モジュール** |
| Portal Lambda | `/aws/lambda/<name_prefix>-portal-api` | **lambda モジュール** |
| VPC Flow Logs | `/vpc/<name_prefix>-flowlogs` | **logging モジュール（本モジュール）** |
| ALB アクセスログ | S3 バケット（CloudWatch ではない） | dev root（Task 27） |

本モジュールが作成する CloudWatch ロググループは **VPC Flow Logs 用のみ**。Portal
Lambda ロググループは lambda モジュール（`aws_cloudwatch_log_group.portal`）が所有
するため、本モジュールでは作成しない（旧 `enable_lambda_log_group` / `lambda_log_group_name`
と Lambda ロググループ resource は本 Task で撤去済み）。ECS / EKS のロググループも
各所有モジュールが持つ。

## VPC Flow Logs 構成

- **ロググループ**: `aws_cloudwatch_log_group.vpc_flowlogs`（`/vpc/<name_prefix>-flowlogs`、
  `retention_in_days` 変数、common tags）。
- **IAM role**: `aws_iam_role.flowlogs`。trust principal は `vpc-flow-logs.amazonaws.com`
  のみで、`aws:SourceAccount` と `aws:SourceArn` により当該account/regionのFlow Logへ
  限定する。CloudWatch Logsの作成・書込・stream参照権限は専用ロググループARN
  （およびそのlog stream）へ限定し、リソース指定非対応の`DescribeLogGroups`だけを
  `aws:RequestedRegion`条件付きWildcard Exceptionとする。
  partition / region / account をハードコードせず、ロググループ resource の ARN と
  `data.aws_region` / `aws:RequestedRegion` から解決する。広い管理者権限や不要な
  サービス権限は付与しない。
- **flow log**: `aws_flow_log.this`。`vpc_id` を必須入力で受け取り、`traffic_type = "ALL"`、
  destination type は CloudWatch Logs、destination ARN は専用ロググループ、role ARN を
  設定。ロググループ・IAM roleへの参照に加え、inline policy付与完了後にFlow Logを
  作成する`depends_on`を明示する。

## retention（保持期間）

`retention_in_days`（既定 30）。CloudWatch Logs は離散値のみ対応するため、要件の
14〜30 日範囲内でサポートされる **14 または 30** のみを許可する。

## 入力

- `name_prefix` / `common_tags`
- `vpc_id`（必須。network モジュール出力を dev root 経由で Task 27 に供給）
- `retention_in_days`（既定 30、14 または 30）
- `vpc_flowlogs_log_group_name`（任意上書き）

## 出力

- `flow_log_id`
- `vpc_flowlogs_log_group_name` / `vpc_flowlogs_log_group_arn`
- `vpc_flowlogs_role_arn`

## dev root 配線

dev rootはnetwork moduleの`vpc_id`を本moduleへ配線済みです。実log streamの発生確認はCategory Cです。

## テスト

`tests/test_logging_snapshot.py` は Terraform/AWS を実行しない静的テスト。`aws_flow_log`
の存在・`traffic_type = ALL`・CloudWatch Logs destination・VPC Flow Logs service trust・
専用ロググループへの書込権限・retention 変数・`vpc_id` 入力・必要 output・Lambda/ECS/EKS
ロググループを本モジュールが作成していないこと・ハードコード account ID / 実 ARN /
機微リテラル非混入を検証する。

## 検証分類

- Category A（本 Task で必須）: 上記静的テスト、`terraform validate`。
- Category C: 実 VPC での flow log 配信確認。
