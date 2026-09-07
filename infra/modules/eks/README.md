# module: eks

Product_A の非同期ワーカー基盤となる EKS クラスタを Fargate 前提で定義します。Terraform module は AWS リソースを所有し、Kubernetes manifest は `apps/eks-workers/k8s` で管理します。

## 構成

| リソース | 役割 |
| --- | --- |
| `aws_eks_cluster` | Control plane。API/audit などのログを CloudWatch Logs へ出力します。 |
| `aws_iam_openid_connect_provider` | ServiceAccount ごとの IRSA trust の基盤です。 |
| workers Fargate profile | alarm / finding / summary workload を private subnet で実行します。 |
| kube-system Fargate profile | CoreDNS などのシステム workload を実行します。 |
| aws-observability Fargate profile | Fargate 組み込みログルーターを有効にします。 |
| Fargate pod execution role | イメージ取得と組み込みログルーターの CloudWatch Logs 出力を許可します。 |
| 3つの IRSA role | alarm worker、finding worker、summary cronjob を個別の ServiceAccount と最小権限に分離します。 |
| worker log group | Pod の stdout / stderr を集約します。 |

Kubernetes version の既定値は `1.36` です。AWS の standard support 対象は変わるため、apply 直前に利用可能かつ standard support 内であることを再確認し、対象外なら plan/apply を停止して `eks_kubernetes_version` を更新してください。extended support を前提にしません。

Public API endpoint を有効にする場合、`eks_public_access_cidrs` は必須です。`0.0.0.0/0` と `::/0` は validation で拒否されます。Operator の実 CIDR だけを Parameter Sheet から渡します。`eks_operator_principal_arn` の EKS access entry は dev root の後続配線で作成します。

## IRSA 最小権限

すべての trust policy は OIDC provider、`aud = sts.amazonaws.com`、単一の `system:serviceaccount:<namespace>:<service-account>` に限定します。

| Role / ServiceAccount | 許可範囲 |
| --- | --- |
| `eks-alarm-worker-role` / `eks-alarm-worker` | alarm queue の receive/delete/attributes/url、DB secret 1件の参照、DB secret KMS keyのDecrypt（key ARN限定、Secrets Manager経由のみ）、worker log group への書き込み |
| `eks-finding-worker-role` / `eks-finding-worker` | finding queue の receive/delete/attributes/url、DB secret 1件の参照、DB secret KMS keyのDecrypt（key ARN限定、Secrets Manager経由のみ）、worker log group への書き込み |
| `eks-cronjob-role` / `eks-cronjob` | DB secret 1件の参照、DB secret KMS keyのDecrypt（key ARN限定、Secrets Manager経由のみ）、worker log group への書き込み、Portal bucket の `reports/*` への PutObject、`report_metadata` と `public_status_items` への PutItem |

alarm role は finding queue を参照せず、finding role は alarm queue を参照しません。Cronjob role に SQS 権限、S3 read、DynamoDB UpdateItem、Aurora 以外の secret 権限は付与しません。Secret の値や接続文字列は module、output、manifest に保存せず、ARN 参照のみを渡します。

Fargate pod execution role の logging statement だけは `Resource = "*"` を使用します。ログルーターが stream を実行時生成するため事前に対象 ARN を確定できないことが理由で、許可 action は CloudWatch Logs の生成・列挙・書き込みに限定しています。

## Fargate ログ

Fluent Bit DaemonSet は作成しません。EKS Fargate の組み込みログルーターを使用します。

1. `apps/eks-workers/k8s/00-namespace.yaml` で `aws-observability` namespace と必須ラベルを作成します。
2. `apps/eks-workers/k8s/40-fargate-logging.yaml` で `aws-logging` ConfigMap を作成します。
3. ConfigMap の region と log group placeholder は deployment script が一時ファイルへレンダリングします。
4. namespace と ConfigMap を worker workload より先に適用します。

Terraform module は aws-observability Fargate profile、pod execution role の logging 権限、対象 log group を所有します。

## 主な入力と出力

入力には `private_subnet_ids`、`eks_security_group_id`、`alarm_queue_arn`、`finding_queue_arn`、`db_secret_arn`、`db_secret_kms_key_arn`、`portal_reports_bucket_arn`、2つの DynamoDB table ARN、`eks_public_access_cidrs`、`eks_operator_principal_arn` を使用します。

外部配線用 output は `cluster_name`、`cluster_arn`、`cluster_endpoint`、`cluster_oidc_issuer_url`、`oidc_provider_arn`、`fargate_profile_arn`、`fargate_pod_execution_role_arn`、`alarm_worker_role_arn`、`finding_worker_role_arn`、`cronjob_role_arn`、`worker_log_group_name` です。Secret 値は出力しません。

## 検証範囲

`tests/test_eks_static.py` は IRSA の分離、queue / secret / Portal 書き込み範囲、CIDR validation、Fargate logging manifest を AWS 接続なしで検査します。実クラスタ作成、`kubectl apply`、workload 起動、ログ転送確認は Category C として Operator 承認後に実施します。
