# Wildcard Exception Registry — iam module

本 module の IAM policy で `Resource = "*"` を許容するのは、AWS がリソースレベルの
ARN 制限をサポートしない Action に限る（Req 2.5, 2.6）。各エントリは
`aws:RequestedRegion` 条件で使用リージョンを制約する。機械可読版は
`wildcard_exceptions.json`。

| Action | 理由 | Condition | 付与ロール |
| --- | --- | --- | --- |
| `ecr:GetAuthorizationToken` | ECR 認証トークンは account/region スコープで、resource-level ARN を取れない | `aws:RequestedRegion = ap-northeast-1` | ecs-task-execution-role / migration-execution-role |

上記以外の Resource_Level_Action は、すべて個別 ARN（ECR repository / DB secret /
Bearer secret / log stream）へ限定する。CloudWatch Logs の log group は Terraform が
事前作成するため、execution role に `logs:CreateLogGroup` は付与しない。
`Resource = "*"` は上記 Action 以外に存在
してはならない（静的テストで検出）。
