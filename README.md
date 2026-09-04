# AWS Incident & Security Operations Platform

社内運用向け内部基盤（**Product_A**）と関係者向け公開ポータル（**Product_B**）を、AWS 上に疎結合で構築するポートフォリオ兼実務想定の成果物です。両者は単一システムへ統合せず、**A→B の一方向・非同期連携のみ**を許容します。

- **Product_A（内部運用・処理基盤）**: ECS Fargate による同期 API（Backend_API / FastAPI）、EKS による非同期ワーカー・CronJob（Worker_Alarm / Worker_Finding / Cronjob_Summary）、Aurora PostgreSQL による永続化。Operator がインシデント・アラーム・セキュリティ Finding・対応履歴・月次集計を管理します。
- **Product_B（公開・配信ポータル）**: CloudFront + S3(OAC) + WAF + Cognito + API Gateway + Lambda + DynamoDB。Viewer が障害ステータス・メンテナンス情報・月次レポートを閲覧します。
- **A→B 連携**: Cronjob_Summary が月次レポートを Portal_Storage(S3 `reports/*`) へ配置し、メタ情報を `report_metadata`、公開ステータスを `public_status_items`（DynamoDB）へ反映します。Product_B から Product_A への書き込みは行いません。

対象は **dev 環境の MVP** です。リージョンは `ap-northeast-1`、命名規則は `ops-platform-dev-<resource>`。

---

## ディレクトリ構成

```
.
├─ infra/
│  ├─ environments/dev/     # dev 環境の Terraform ルート（backend/provider/共通変数/命名helper）
│  └─ modules/              # 再利用可能な Terraform モジュール群
│     ├─ network/           # VPC/Subnet/SG/NAT/IGW/VPCエンドポイント
│     ├─ ecr/               # ECR リポジトリ
│     ├─ alb/               # ALB / Target Group / リスナー
│     ├─ ecs/               # ECS cluster / task / service
│     ├─ eks/               # EKS / Fargate Profile / IRSA
│     ├─ aurora/            # Aurora Serverless v2 (PostgreSQL)
│     ├─ messaging/         # SQS + DLQ + EventBridge
│     ├─ s3-portal/         # Portal_Storage (OAC 保護)
│     ├─ cloudfront/        # CloudFront + OAC + WAF
│     ├─ waf/               # WAF Web ACL（cloudfront と統合可）
│     ├─ cognito/           # Cognito User Pool / App Client
│     ├─ apigateway/        # API Gateway (Cognito JWT Authorizer)
│     ├─ lambda/            # Portal_API Lambda
│     ├─ dynamodb/          # Portal_DB 4テーブル
│     ├─ logging/           # CloudWatch Logs グループ
│     ├─ monitoring/        # CloudWatch Alarm / Dashboard / SNS
│     └─ iam/               # 最小権限 IAM ロール群
├─ apps/
│  ├─ backend-api/          # ECS Backend_API (FastAPI, Python) + app/ + Dockerfile
│  ├─ eks-workers/          # EKS ワーカー3種 + k8s manifest
│  │  ├─ alarm-event-processor/
│  │  ├─ security-finding-worker/
│  │  ├─ monthly-summary-cronjob/
│  │  └─ k8s/
│  ├─ portal-frontend/      # Product_B 静的フロント (src/, public/)
│  └─ portal-lambda/        # Product_B Portal_API (Lambda, Python)
├─ docs/                    # 設計・運用ドキュメント（architecture/db/api/operation/security/runbook）
├─ bootstrap/               # 初回のみローカル apply する土台（state/pipeline/exec-role）
├─ scripts/                 # デプロイ・サンプルデータ投入スクリプト
└─ .gitignore
```

---

## 構築手順（Bootstrap → Infra_Pipeline → App_Deploy）

インフラは 3 層に分離しています。**実際の `terraform apply` / デプロイは、変更内容（plan）をユーザーが確認・承認した後にのみ実行してください。** 本 README のコマンドは手順を示すものであり、承認前の自動 apply は行いません。

### 1. Bootstrap（ローカル初回のみ）

パイプライン自身を作るための「鶏卵問題」を回避するため、remote state / CI/CD 土台 / 実行用 IAM Role を初回だけローカルから作成します。

```bash
# bootstrap/ で（内容確認後、ユーザー承認のうえで）
terraform -chdir=bootstrap init
terraform -chdir=bootstrap plan     # 作成予定リソースを必ず確認
terraform -chdir=bootstrap apply    # ← 承認後にのみ実行
```

作成物: remote state 用 S3（バージョニング/暗号化/public access block）、state lock（`use_lockfile=true` を第一候補、DynamoDB lock は代替案）、CodePipeline / CodeBuild、artifact 用 S3、terraform-exec-role。

### 2. Infra_Pipeline（本体インフラ / CodePipeline + CodeBuild）

main への merge/push でパイプラインが起動し、次の順で実行します。

```
terraform fmt → terraform validate → terraform plan → 手動承認 → terraform apply
```

- `terraform plan` で作成/変更/削除予定リソースと、**コスト影響が大きいリソース（Aurora / NAT / EKS / CloudFront）** を明示します。
- **手動承認が無い限り `terraform apply` は実行しません**。ローカル端末からの継続 apply は行いません。

### 3. App_Deploy（インフラ apply と分離）

```bash
# ECS: build → ECR push → service update
scripts/deploy-ecs.sh
# EKS: build → ECR push → kubectl apply
scripts/deploy-eks.sh
# CloudFront: frontend build → S3 sync → invalidation
scripts/deploy-frontend.sh
```

> `scripts/*` は後続タスクで実装します（現状はプレースホルダ）。

---

## 削除（撤去）手順

不要なリソースを削除してコストを止められます。**依存関係の逆順**で撤去してください。撤去も破壊的操作のため、ユーザー承認後にのみ実行します。

1. **App レイヤの停止**
   - ECS service の desired_count を 0 に、または service 削除。
   - EKS の Deployment / CronJob を削除（`kubectl delete -f apps/eks-workers/k8s/`）。
   - CloudFront ディストリビューションを無効化。
2. **S3 / ECR の中身削除**（`terraform destroy` 前に空にする必要がある）
   - Portal_Storage / artifact / state 以外の S3 バケットのオブジェクトを削除。
   - ECR リポジトリのイメージを削除。
3. **本体インフラの撤去**
   ```bash
   terraform -chdir=infra/environments/dev plan -destroy   # 削除対象を確認
   terraform -chdir=infra/environments/dev destroy          # ← 承認後にのみ実行
   ```
   - コスト影響が大きい **Aurora / NAT Gateway / EKS / CloudFront** が削除対象に含まれることを確認します。
4. **Bootstrap の手動削除（最後）**
   - remote state / CI/CD 土台は最後に撤去します。state 用 S3 と artifact S3 のオブジェクトを空にしてから削除。
   - DynamoDB lock table を使っている場合は併せて削除。
5. **残存確認**
   - CloudWatch Logs グループ、Secrets Manager シークレット、WAF Web ACL 等の取り残しがないか確認します。

---

## 注意点

- **dev 環境限定**: 本構成は dev 環境の MVP です。prod / staging は対象外です（Req 24.1）。
- **ALB 公開範囲**: Product_A は社内運用基盤です。デモ用に public ALB とする場合でも、**許可 CIDR 限定を強く推奨**します（`sg-alb` の `0.0.0.0/0` はデモ用と明記）。本番想定では **internal ALB もしくは許可 CIDR 限定**とします（Req 15.1）。
- **コスト影響が大きいリソース**: **Aurora / NAT Gateway / EKS / CloudFront** はコスト影響が大きいため、`terraform plan` で明示し、不要時は上記撤去手順で停止してください（Req 23.2, 24）。代替案（Aurora→RDS t4g.micro、NAT→VPC エンドポイント、CloudFront→PriceClass_100）を設計文書に記載しています。
- **シークレットをコードに直書きしない**: DB パスワード等は Secrets Manager で管理し、ソースコード / IaC / 環境変数へ平文で含めません（Req 16.1/16.2）。`.env` / `*.pem` / `credentials` 等は `.gitignore` で除外済み（Req 16.3）。
- **承認前の terraform apply 禁止**: 本体インフラの作成・更新は Infra_Pipeline の**手動承認後**にのみ実行します。ローカルからの継続 apply は行いません（Req 21.4, 21.5, 23.3）。
- **レポートファイルは MVP ではダミー/非機微のみ**: 機微レポートは後続 Phase で署名付きアクセス（CloudFront signed URL/cookie または API 経由の S3 pre-signed URL）を導入します。

---

## ドキュメント

| ドキュメント | 内容 |
| --- | --- |
| [docs/architecture/architecture-overview.md](docs/architecture/architecture-overview.md) | 全体アーキテクチャ、ECS/EKS/CloudFront を分ける理由、A→B 連携 |
| [docs/db/db-design.md](docs/db/db-design.md) | Aurora 7テーブル / DynamoDB 4テーブル、TTL/GSI 設計理由 |
| [docs/api/api-design.md](docs/api/api-design.md) | Product_A / Product_B の API 一覧 |
| [docs/operation/operation.md](docs/operation/operation.md) | 運用手順、デプロイ設計、監視、デモシナリオ |
| [docs/security/security.md](docs/security/security.md) | OAC/WAF/Cognito JWT/Secrets Manager/最小権限 IAM/ALB 公開範囲 |
| [docs/runbook/runbook.md](docs/runbook/runbook.md) | 障害時対応、DLQ 運用、撤去手順 |

補足設計ドキュメント: [terraform-structure](docs/architecture/terraform-structure.md) / [terraform-backend-design](docs/architecture/terraform-backend-design.md) / [deployment-design](docs/operation/deployment-design.md) / [app-deployment-design](docs/operation/app-deployment-design.md) / [cicd-design](docs/operation/cicd-design.md) / [implementation-plan](docs/operation/implementation-plan.md)。
