# module: iam（Product_A ECS 系 5 ロール）

Product_A の ECS 系 **5 ロール**を最小権限で所有する（Req 2）。EKS の IRSA ロール
（alarm/finding worker・cronjob）や lambda-portal-role は本 module では作成しない
（それぞれ eks / lambda module 所有）。

## 所有ロールと権限

| ロール | 決定的名称 | 主要権限（Resource は個別 ARN 限定） |
| --- | --- | --- |
| Backend execution | `${name_prefix}-ecs-task-execution-role` | ECR pull（repo ARN 限定）, Backend log group 書込, Bearer secret `GetSecretValue`（Bearer ARN のみ） |
| Backend task | `${name_prefix}-ecs-task-role` | DB secret `GetSecretValue`（DB secret ARN のみ）。Bearer 取得権限なし |
| migration execution | `${name_prefix}-migration-execution-role` | ECR pull（repo ARN 限定）, migration log group 書込 |
| migration task | `${name_prefix}-migration-task-role` | DB secret `GetSecretValue`（DB secret ARN のみ）。awslogs 権限なし |
| migration launcher | `${name_prefix}-migration-launcher-role` | **role 本体 + trust policy のみ**。`ecs:RunTask`/`iam:PassRole` policy は dev root（Task 27）で attach |

最初の 4 role name は bootstrap の PassRole ARN 組み立てと完全一致させる契約。launcher は
PassRole 対象ではない。

## iam↔ecs 循環の回避

- Backend / migration の CloudWatch Logs log group ARN は
  `data.aws_partition` / `data.aws_caller_identity` / `var.aws_region` / `name_prefix`
  から文字列組み立てで解決し、ecs module 出力に依存しない（partition を `aws` 固定にしない）。
- migration-launcher role は本 module では body + trust のみ。RunTask policy は ecs の
  migration cluster/task-def ARN を必要とするため dev root で attach する。

## 入力

- `name_prefix` / `common_tags` / `aws_region`（既定 `ap-northeast-1`）
- `backend_ecr_repository_arn`（dev root で `module.ecr.repository_arns["backend-api"]` を供給）
- `migration_ecr_repository_arn`（dev root で `module.ecr.repository_arns["db-migration"]` を供給）
- `backend_bearer_secret_arn`（dev root の Bearer Secret）
- `db_secret_arn`（aurora の DB secret）
- `migration_launcher_trusted_principal_arns`（Operator principal、既定空。実 ARN は Parameter Sheet 供給、repo に記載しない）

## 出力

5 ロールの name/arn と、PassRole allowlist（4 ARN）を出力する。

## Wildcard Exception

`Resource = "*"` を許容するのは `ecr:GetAuthorizationToken` のみ
（`aws:RequestedRegion` 制約）。CloudWatch Logs の log group は Terraform が事前作成し、
execution role は各専用 log group 配下の log stream だけへ書き込む。詳細は `wildcard-exceptions.md` /
`wildcard_exceptions.json`。

## テスト

`tests/test_iam_snapshot.py` は Terraform/AWS を実行しない静的テスト。5 ロール定義・
決定的名称・Resource_Level_Action の `*` 非使用（Wildcard_Exception を除く）・log group
ARN が partition 変数を使用・ecs 出力非依存・PassRole allowlist 4 ARN・機微/実 ARN
非混入を検証する。

## 検証分類

- Category A（本 Task で必須）: 上記静的テスト、`terraform validate`。
- Category C: なし。
