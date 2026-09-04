# セキュリティ設計

design.md の「セキュリティ設計 / IAM 設計 / ネットワーク設計」を要約する（Req 26.2, 26.3）。

## 対策一覧

| 項目 | 対策 | 対応要件 |
| --- | --- | --- |
| S3 オリジン保護 | public access block 有効＋**OAC 経由のみ許可**（それ以外は拒否） | Req 12.2, 12.3 |
| レポートファイルアクセス制御 | **MVP はダミー/非機微のみ配信**。機微レポートは後続 Phase で CloudFront signed URL/cookie または API 発行の S3 pre-signed URL | Req 11, 14 |
| Web 保護 | WAF Managed Rules 1 つ以上＋Rate-based rule | Req 13 |
| Viewer 認証 | Cognito JWT（Portal_API は JWT 必須、欠落/無効は 401） | Req 9 |
| Product_A ALB 公開範囲 | 社内基盤。デモ用 public でも**許可 CIDR 限定/認証/README 注意書き**。本番は internal ALB または許可 CIDR 限定 | Req 15 |
| シークレット | Secrets Manager 管理、IaC/コード平文禁止 | Req 16.1, 16.2 |
| 機微ファイル除外 | `.gitignore`（シークレット・ローカル state） | Req 16.3 |
| 通信 | HTTPS（CloudFront/ALB） | Req 12.1 |
| 権限 | 最小権限 IAM（IRSA）、B→A 書き込みなし | Req 17, 14.3 |

## IAM（最小権限）

| ロール | 主な権限（最小） | 備考 |
| --- | --- | --- |
| ecs-task-execution-role | ECR pull、CloudWatch Logs 出力 | 実行基盤用 |
| ecs-task-role（backend-api） | Secrets Manager 読取、Aurora 接続、CloudWatch Logs | **Portal_DB/Storage 書込権限なし** |
| eks-worker-role（IRSA, alarm/finding） | SQS 受信/削除、Aurora 接続、CloudWatch Logs | Pod 単位付与 |
| eks-cronjob-role（IRSA, summary） | Aurora 接続、**Portal_Storage/Portal_DB 書込**、CloudWatch Logs | **A→B 書込はこのロールに限定** |
| lambda-portal-role | DynamoDB 読取＋page_view_logs 書込、CloudWatch Logs | **Product_A 書込権限なし** |
| terraform-exec-role | インフラ作成に必要な権限 | Bootstrap で定義 |

**B→A 一方向性の担保**: lambda-portal-role に Product_A/Aurora 書き込み権限を付与しないことで、IAM レベルで Req 14.3 の一方向性を保証する。

## ネットワーク境界

- VPC 10.0.0.0/16、public / private-app / isolated-db サブネット（AZ a/c）。Aurora は isolated-db に配置し外部通信なし（Req 15.4）。
- Security Group は業務上必要な通信のみ許可（Req 15.2）。
  - `sg-alb`: 443 from 許可 CIDR（**デモ用 0.0.0.0/0 でも許可 CIDR 限定を推奨**）
  - `sg-ecs`: 8080 from sg-alb / 5432 to sg-db
  - `sg-eks`: 5432 to sg-db（外部はエンドポイント/NAT 経由）
  - `sg-db`: 5432 from sg-ecs, sg-eks のみ
- 外向き通信は NAT Gateway(single-AZ) と VPC エンドポイント（S3/ECR/Secrets Manager/CloudWatch Logs）で最小化する（Req 24.7）。
