# module: eks

Product_A の非同期ワーカー基盤となる EKS クラスタを **Fargate 前提**で定義する（Task 10.1）。

- 対応要件: Req 17.1（IRSA 最小権限）, 17.3（Pod 単位権限付与）, 18.1（ログ集約）

## 構成リソース

| リソース | 役割 |
| --- | --- |
| `aws_eks_cluster` | 控control plane。`enabled_cluster_log_types` で API/audit 等のログを CloudWatch Logs へ。private/public エンドポイントは変数制御。 |
| `aws_iam_openid_connect_provider` | クラスタ OIDC issuer から作成。IRSA の信頼基盤。 |
| `aws_eks_fargate_profile`（workers / kube-system / aws-observability） | Fargate 前提。`workers` にアプリ Pod、`kube-system` にコアアドオン、`aws-observability` に Fargate 組み込みログルーター用 ConfigMap を配置。すべて private subnet。 |
| Fargate pod execution role | イメージ pull と **Fargate 組み込みログルーター**の CloudWatch Logs 出力権限を持つ。 |
| IRSA `eks-worker-role` | Worker_Alarm / Worker_Finding 用。 |
| IRSA `eks-cronjob-role` | Cronjob_Summary 用。 |
| `aws_cloudwatch_log_group` | ワーカーログ集約先。k8s の `aws-logging` ConfigMap の output と一致させる。 |

## Fargate ログ収集方式（DaemonSet 不使用）

本モジュールは **Fluent Bit の DaemonSet を作らない**。EKS Fargate の **組み込みログルーター**を用いる。

- ルーターの有効化は Kubernetes 側の `aws-observability` namespace + `aws-logging` ConfigMap（`output=cloudwatch_logs`）で行う（`apps/eks-workers/k8s`）。
- 本モジュールの責務は「その受け皿となる **`aws-observability` 用 Fargate Profile**」と「**Fargate pod execution role への logging 権限**（`logs:CreateLogGroup` / `CreateLogStream` / `PutLogEvents` / `DescribeLogStreams` 等）」と「**CloudWatch Logs グループ**」の用意まで。ConfigMap 本体は k8s manifest 側で管理する。
- 将来 EC2 ノード構成へ拡張する場合に限り Fluent Bit DaemonSet を検討する。

## 責務分離（Terraform / Kubernetes）

- **この Terraform モジュール**: AWS リソースのみ（クラスタ、Fargate Profile、OIDC provider、IRSA IAM ロールと trust policy、最小権限ポリシー、pod execution role、ロググループ）。
- **Kubernetes manifest**（`apps/eks-workers/k8s`）: namespace `workers`、ServiceAccount（IRSA ロール ARN を annotation で紐付け。ARN はプレースホルダ/変数化しコミットに実値を書かない）、Deployment（alarm-event-processor, security-finding-worker）、CronJob（monthly-summary-cronjob）、`aws-observability` の `aws-logging` ConfigMap。

## IRSA 最小権限

trust policy は OIDC provider の `sub = system:serviceaccount:<worker_namespace>:<sa-name>`、`aud = sts.amazonaws.com` に限定する。

- `eks-worker-role`（`worker_service_account_name` に紐付け）
  - SQS: `ReceiveMessage` / `DeleteMessage` / `GetQueueAttributes` / `GetQueueUrl`（`sqs_queue_arns` 限定）
  - Secrets Manager: `GetSecretValue`（`db_secret_arn` 限定）
  - CloudWatch Logs: `CreateLogStream` / `PutLogEvents` / `DescribeLogStreams`（ワーカーログ群限定）
- `eks-cronjob-role`（`cronjob_service_account_name` に紐付け）
  - Secrets Manager: `GetSecretValue`（`db_secret_arn` 限定）
  - CloudWatch Logs 書込
  - **Portal(S3/DynamoDB) 書込は付与しない**。A→B 連携は Phase 3 のため、その時点で `eks-cronjob-role` に Portal_Storage 書込・Portal_DB 書込を追加する（Feedback 6 に基づき A→B 書込はこのロールに限定）。

### Resource="*" の根拠

Fargate pod execution role の logging ステートメントのみ `Resource = "*"`。ログルーターが実行時にログストリームを動的生成するため、作成前にストリーム名を特定できない。範囲はリージョン内 CloudWatch Logs に限定される。

## Secrets Manager の扱い

`db_secret_arn` は **ARN 参照のみ**。DB パスワード・接続 URL・シークレット値は本モジュール・出力・README のいずれにも現れない。IRSA の `GetSecretValue` はこの ARN に限定する。

## dev root への配線について（後続依存）

`infra/environments/dev` への本モジュール配線は、`sqs_queue_arns`（messaging モジュール = Task 11）と `db_secret_arn`（aurora モジュール = Task 6.1 の出力）が確定してから行う。ecs/alb と同じ「実装したものだけ配線」方針に従い、Task 10.1 時点では配線しない。

## 出力

`cluster_name` / `cluster_arn` / `cluster_endpoint` / `cluster_oidc_issuer_url` / `oidc_provider_arn` / `fargate_profile_arn` / `fargate_pod_execution_role_arn` / `worker_role_arn` / `cronjob_role_arn` / `worker_log_group_name`。シークレット値は一切出力しない。

## テスト

`tests/test_eks_static.py` は Terraform を実行しない静的検証（ファイル文字列・構成の存在確認）。`terraform init/validate/plan/apply` および AWS API 呼び出しは行わない。
