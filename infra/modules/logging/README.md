# module: logging (CloudWatch Logs 集約)

ECS / EKS worker / Lambda / ALB / VPC Flow のログ集約における「責務分離」を明確に
し、まだどのモジュールも作っていないロググループのみを作成する（Req 18.1, 18.2,
18.3）。

## ロググループ所有権（重複作成しない）

| ログ対象 | ロググループ | 所有モジュール |
| --- | --- | --- |
| ECS backend-api | `/ecs/<name_prefix>-backend-api` | **ecs モジュール（Task 9）** |
| EKS worker | `/<name_prefix>/eks/workers` | **eks モジュール（Task 10）** |
| Portal Lambda | `/aws/lambda/<name_prefix>-portal` | **logging モジュール（本モジュール）** |
| VPC Flow Logs | `/vpc/<name_prefix>-flowlogs` | **logging モジュール（本モジュール）** |
| ALB アクセスログ | S3 バケット（CloudWatch ではない） | alb モジュール（Task 9） |

ECS backend-api と EKS worker のロググループは既存モジュールが所有しているため、
本モジュールでは**新規作成しない**。二重作成を避けるための責務分離であり、これら
既存グループの retention は各所有モジュールの `log_retention_days` 変数で設定する。

ALB アクセスログは CloudWatch ではなく S3 に出力されるため、本モジュールでは扱わ
ない。したがって本モジュールが作成する CloudWatch ロググループは Lambda と VPC
Flow Logs 用のみ。

## retention（保持期間）

`retention_in_days`（既定 30）で一元管理する。Task 11.2 は 14〜30 日保持を要求
しているが、CloudWatch Logs は離散値のみ対応する（21 のような値は apply 時に失敗
する）。そのため本モジュールでは、要件の 14〜30 日範囲内で CloudWatch Logs が
サポートする値である **14 または 30** のみを許可する。

## Fargate 組み込みログルーターの方針

EKS Fargate のログ収集は Fluent Bit DaemonSet を使わず、k8s の
`aws-observability` ConfigMap（Task 10 の eks モジュール方針）で行う。pod
execution role の logging 権限と worker ロググループは eks モジュールが所有する。
本モジュールは Fluent Bit DaemonSet を一切作成しない。

## 変数

- `retention_in_days`（既定 30、14 または 30）
- `enable_lambda_log_group`（既定 true）/ `lambda_log_group_name`（任意上書き）
- `enable_vpc_flowlogs_log_group`（既定 true）/ `vpc_flowlogs_log_group_name`

## 出力

- `lambda_log_group_name` / `lambda_log_group_arn`
- `vpc_flowlogs_log_group_name` / `vpc_flowlogs_log_group_arn`

無効化時は null を返す。EKS worker ロググループは eks モジュール所有のため、本
モジュールでは中継出力しない（重複作成しない）。

## dev root への配線について（後続依存）

`infra/environments/dev` への配線は、Lambda（Task 15）や VPC Flow Logs の配線先
確定後に行う。alb/ecs/eks と同じ「実装したものだけ配線」方針に従い、Task 11 時点
では dev ルートへは配線しない。

## テスト

`tests/test_logging_snapshot.py` は Terraform/AWS を実行しない静的テスト。
retention の許可値が 14 または 30 であること、ECS/EKS ロググループを新規作成して
いないこと、Fluent
Bit DaemonSet が無いこと、命名/タグ、機微リテラル非混入を検証する。
