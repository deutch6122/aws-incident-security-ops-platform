# scripts

運用・デプロイ・サンプルデータ投入スクリプトを配置する。

## 内容（予定）

- `deploy-ecs.sh` … build → ECR push → ECS service update（Req 22.2）
- `deploy-eks.sh` … build → ECR push → `kubectl apply`（Req 22.3）
- `deploy-frontend.sh` … build → S3 sync → CloudFront invalidation（Req 22.4）
- サンプルイベント投入（EventBridge/SQS）、非機微レポート・public_status_items シード（Req 6.1, 14.1, 14.2）

> 実装は Task 18.1 / 19.1 で追加する（プレースホルダ）。App_Deploy はインフラ apply と分離する。
