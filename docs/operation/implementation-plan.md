# 実装計画（要約）

tasks.md の Implementation Plan を要約する（Req 26.2）。正本は `.kiro/specs/aws-incident-security-ops-platform/tasks.md`。

## フェーズ構成

- **Phase 1: リポジトリ・ドキュメント・Terraform 土台** — リポジトリ骨格、`.gitignore`、README、docs、Bootstrap（state/pipeline/exec-role）、dev ルート、network/ecr/Infra_Pipeline。
- **Phase 2: 成果物A ECS/EKS 内部運用基盤** — Aurora + スキーマ、Backend_API（FastAPI）、ECS/ALB、EKS ワーカー3種、非同期経路（SQS/EventBridge）、ログ集約。
- **Phase 3: 成果物B CloudFront 配信ポータル** — DynamoDB、s3-portal(OAC)、CloudFront/WAF、Cognito、API Gateway、Portal_API(Lambda)、静的フロント、A→B 連携。
- **Phase 4: 運用・セキュリティ・デモ整備** — サンプルデータ、監視（Alarm/Dashboard/SNS）、App_Deploy スクリプト、Runbook / デモシナリオ / アーキ図、README 最終化。

## テスト方針

- 純粋ロジック（集計・検証・冪等取込・判定・監査・命名規則）は Property 1〜11 に対応する PBT（Python Hypothesis、最低 100 反復、タグ付与）で検証。DB 依存は testcontainers(PostgreSQL) / moto / DynamoDB Local で分離。
- AWS マネージドサービス挙動・インフラ配線は統合テスト / IaC スナップショット / スモークテストで検証（PBT 対象外）。
- `*` 付きサブタスクは任意（MVP 短縮時スキップ可）。コア実装タスクには `*` を付けない。

## 注意

実際の terraform apply / デプロイ実行 / 手動承認 / AWS コンソール操作は本計画のコーディング対象外。スクリプト・manifest・IaC コードの作成のみを含む。
