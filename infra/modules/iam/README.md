# module: iam

最小権限 IAM ロール群を定義する。

| ロール | 用途 |
| --- | --- |
| ecs-task-execution-role | ECS タスク実行（ECR pull、CloudWatch Logs） |
| ecs-task-role（backend-api） | Secrets Manager 読取、Aurora 接続、CloudWatch Logs（Portal 書込なし） |
| eks-worker-role（IRSA） | SQS 受信/削除、Aurora 接続、CloudWatch Logs |
| eks-cronjob-role（IRSA） | Aurora 接続、Portal_Storage/Portal_DB 書込、CloudWatch Logs（A→B 連携限定） |
| lambda-portal-role | DynamoDB 読取＋page_view_logs 書込、CloudWatch Logs（Product_A 書込なし） |

- 対応要件: Req 17.1, 17.3, 14.3
- 実装は各 module および後続タスクで追加する（プレースホルダ）。
