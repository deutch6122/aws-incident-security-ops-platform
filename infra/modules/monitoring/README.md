# module: monitoring

CloudWatch Alarm・A/B 分離 2 ダッシュボード・SNS 通知を定義する（Task 18.2 /
Requirement 18.1）。監視対象のリソース名/ディメンションは変数で受け取り、実 ARN・
実アカウントID は埋め込まない（プレースホルダ/変数のみ）。

## 構成

| リソース | 役割 |
| --- | --- |
| `aws_sns_topic.alarms` | 全アラームの通知先。各 alarm の `alarm_actions`/`ok_actions` が参照する。 |
| `aws_cloudwatch_metric_alarm.*` | 下表の各メトリクスアラーム。 |
| `aws_cloudwatch_dashboard.product_a` | Product_A ダッシュボード（ECS/ALB/Aurora/SQS）。 |
| `aws_cloudwatch_dashboard.product_b` | Product_B ダッシュボード（CloudFront/Lambda/DynamoDB/API Gateway）。 |

## CloudWatch Alarm 一覧

| Alarm | Namespace / Metric | 条件 | Product |
| --- | --- | --- | --- |
| `*-sqs-dlq-messages-visible` | AWS/SQS `ApproximateNumberOfMessagesVisible` | `> 0` | A |
| `*-ecs-cpu-high` | AWS/ECS `CPUUtilization` | `> 80%`（既定） | A |
| `*-ecs-memory-high` | AWS/ECS `MemoryUtilization` | `> 80%`（既定） | A |
| `*-ecs-running-tasks-low` | ECS/ContainerInsights `RunningTaskCount` | `< 1`（既定） | A |
| `*-alb-5xx-high` | AWS/ApplicationELB `HTTPCode_ELB_5XX_Count` | `> 5`（既定） | A |
| `*-alb-latency-high` | AWS/ApplicationELB `TargetResponseTime` | `> 2s`（既定） | A |
| `*-aurora-acu-high` | AWS/RDS `ServerlessDatabaseCapacity` | `>= 2 ACU`（既定） | A |
| `*-aurora-connections-high` | AWS/RDS `DatabaseConnections` | `> 80`（既定） | A |
| `*-lambda-errors-high` | AWS/Lambda `Errors` | `>= 1`（既定） | B |
| `*-lambda-throttles-high` | AWS/Lambda `Throttles` | `>= 1`（既定） | B |
| `*-lambda-duration-high` | AWS/Lambda `Duration` | `> 8000ms`（既定、timeout 10s） | B |

閾値・評価期間・period は全て変数化しており、dev 向けに過剰課金になりにくい既定
（`period=300s`、`evaluation_periods=1`）とした。

## SNS 通知構成

`aws_sns_topic.alarms` を 1 つ定義し、各アラームの `alarm_actions` と
`ok_actions` に当該 SNS トピック ARN を設定する。購読先（Email/Chatbot 等）は
このモジュールでは定義せず、機微な実エンドポイントを埋め込まない。DLQ>0 の
発報→SNS 通知は design.md「DLQ 運用方針」に対応する。

## Product_A / Product_B ダッシュボード分離

責務を明確に分離した 2 ダッシュボードを作成する。

- **Product_A**（`*-product-a`）: ECS CPU/Memory、ALB 5XX/Latency、Aurora
  ACU/Connections、SQS DLQ 深度 — 内部運用基盤の面。
- **Product_B**（`*-product-b`）: Lambda Errors/Throttles/Duration、CloudFront
  Requests/5xxErrorRate、API Gateway 5xx/Latency、DynamoDB 消費/スロットル —
  配信ポータルの面。

CloudFront メトリクスは us-east-1 スコープのため、当該ウィジェットの `region`
のみ `us-east-1` を宣言する（他は `var.aws_region`）。

## 監視対象識別子の受け渡し（変数）

実 ARN・実アカウントID は埋め込まず、CloudWatch ディメンション値（名前/ID）を
変数で受ける。既定値は命名規則（`ops-platform-dev-*`）のプレースホルダで、
呼び出し側が各モジュールの output から実値を配線する。

| 変数 | ディメンション |
| --- | --- |
| `dlq_queue_name` | SQS `QueueName`（messaging の `dlq_name`） |
| `ecs_cluster_name` / `ecs_service_name` | ECS `ClusterName` / `ServiceName` |
| `alb_arn_suffix` | ALB `LoadBalancer`（ARN suffix。フル ARN ではない） |
| `lambda_function_name` | Lambda `FunctionName` |
| `aurora_db_cluster_identifier` | RDS `DBClusterIdentifier` |

## 監査ログ（audit_logs）出力の担保（Task 18.3）

状態変更で `audit_logs` にちょうど 1 件記録されることは、既存の Backend API
テストで担保済みであり、本モジュールでは重複実装しない。担保する既存テスト:

- `apps/backend-api/tests/test_property_audit_log.py`
  — **Property 6**（`test_property_6_status_change_records_exactly_one_audit_log`）。
  インシデントのステータス変更後に `audit_logs` がちょうど 1 件増加し、変更前後の
  値（`before_value` / `after_value`）が記録されることを Hypothesis（100 例）で
  検証する（Validates: Requirements 3.6, 8.3）。
- `apps/backend-api/tests/test_business_api.py`
  — `PATCH /incidents/{id}/status` 後に `audit_logs` が 1 件、`before_value` /
  `after_value` が正しいことを具体例で検証する。

これらが Requirement 8.3（状態変更の audit_logs 記録）を担保する。監視構成側は
本モジュールの静的スナップショットテストで DLQ>0 等のアラーム存在を確認する。

## dev root への配線について（後続依存）

`infra/environments/dev` への本モジュール配線は、messaging/ecs/alb/aurora/lambda
の各 output（DLQ 名・クラスタ/サービス名・ALB ARN suffix・Aurora 識別子・Lambda
関数名）が確定してから行う。他モジュールと同じ「実装したものだけ配線」方針に従い、
Task 18 時点では dev ルートへは配線しない。

## テスト

`tests/test_monitoring_snapshot.py` は Terraform/AWS を実行しない静的テスト。
DLQ>0 アラーム・ECS/ALB/Lambda/Aurora の代表アラーム・A/B 分離 2 ダッシュボード
（責務分離）・SNS トピックと `alarm_actions`（SNS 参照）・命名/タグ・機微リテラル
（Secret・実 ARN・実アカウントID）非混入を検証する。
