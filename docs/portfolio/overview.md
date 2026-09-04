# ポートフォリオ概要

本プロジェクトは、AWS 上に構築した **セキュリティインシデント管理基盤** のポートフォリオ兼実務想定成果物です。自己学習を目的とし、dev/MVP 環境で動作検証を行っています。

## プロジェクト概要

| 項目 | 内容 |
| --- | --- |
| プロジェクト名 | AWS Incident & Security Operations Platform |
| 目的 | セキュリティインシデント・アラーム・Finding を管理し、関係者に公開ステータスを配信するシステム |
| 環境 | dev（AWS 東京リージョン: `ap-northeast-1`） |
| 想定ユーザー | 社内運用者（Operator）、公開ポータル閲覧者（Viewer） |

## 解決する課題

- **散在するアラーム・Finding の一元管理**: EventBridge → SQS → Worker 取込で Aurora へ蓄積
- **セキュリティインシデントの記録と追跡**: ステータス変更履歴を audit_logs に記録
- **関係者と非関係者の分離**: Product_A（内部）と Product_B（公開）を明確に分離
- **非同期連携の安全確保**: A→B 連携は一方向・冪等・非機微データのみ

## 想定ユースケース

1. **インシデント管理**: セキュリティアラーム発生 → Worker 取込 → Backend API でステータス管理
2. **月次レポート作成**: CronJob が月次集計 → Product_B へ非同期連携 → Viewer が閲覧
3. **ステータス公開**: 障害状況・メンテナンス情報を Viewer に配信
4. **監査対応**: ステータス変更履歴を audit_logs で追跡

## 使用 AWS サービス一覧

| カテゴリ | サービス | 用途 |
| --- | --- | --- |
| コンピューティング | ECS Fargate | 同期 API（Backend_API） |
| コンピューティング | EKS（Fargate Profile） | 非同期 Worker / CronJob |
| データベース | Aurora Serverless v2（PostgreSQL） | 永続化（incidents, findings, alarm_events 等 7 テーブル） |
| データベース | DynamoDB | 公開ポータル用（public_status_items, report_metadata, page_view_logs, maintenance_windows） |
| メッセージング | SQS（Standard + DLQ） | イベント駆動処理 |
| イベント | EventBridge | アラーム/Finding イベントの受け口 |
| 配信 | CloudFront + S3（OAC） | 静的コンテンツ配信 |
| セキュリティ | WAF | エッジ保護（Rate Limit, IP Block） |
| 認証 | Cognito | Viewer 向け JWT 認証 |
| API | API Gateway | Product_B の API エントリ |
| サーバーレス | Lambda | Portal_API |
| 監視 | CloudWatch（Alarm / Dashboard / SNS） | 監視・通知 |
| シークレット管理 | Secrets Manager | DB 認証情報 |
| IaC | Terraform | インフラ定義 |
| CI/CD | GitHub Actions | 自動テスト |

## Product_A / Product_B の分離

| 特性 | Product_A（内部運用・処理基盤） | Product_B（公開・配信ポータル） |
| --- | --- | --- |
| コンポーネント | ECS（Backend_API）、EKS（Worker/CronJob）、Aurora | CloudFront + S3 + Lambda + DynamoDB |
| アクセス | Operator（社内） | Viewer（Cognito 認証） |
| 役割 | インシデント管理、アラーム取込、月次集計 | ステータス閲覧、レポート配信 |
| データ保持 | 機微を含む可能性あり | 非機微・ダミーのみ |

## A→B 一方向連携

- **実行主体**: `monthly-summary-cronjob`（EKS CronJob）のみ
- **データフロー**:
  1. CronJob が月次集計を実行
  2. レポートファイルを Portal_Storage（S3 `reports/<period>/summary.json`）へ配置
  3. メタ情報を `report_metadata`（DynamoDB）へ登録
  4. 公開ステータスを `public_status_items`（DynamoDB）へ反映
- **制約**: B→A への書き込み・参照は設計上排除。連携データは非機微・ダミーのみ。

## セキュリティ配慮

- **Secret 管理**: DB パスワードは Secrets Manager で管理し、コード・IaC に平文含まず
- **認証・認可**: Cognito JWT（Cognito Authorizer）による API 保護
- **ネットワーク**: ALB は許可 CIDR 限定を推奨（WAF でエッジ保護）
- **最小権限 IAM**: タスクごとに Role を分離
- **OAC**: S3 へのアクセスは CloudFront 経由のみ

## コスト配慮

- **Aurora Serverless v2**: 必要に応じて Auto Pause
- **dev 環境 MVP**: 最小限のリソースサイズ
- **コスト影響大リソースの可視化**: `terraform plan` で明示
- **CloudWatch Logs**: 14〜30 日保持

## CI/CD・テスト方針

- **CI**: GitHub Actions（push / PR / workflow_dispatch）
- **テスト**: suite 別実行（conftest.py 衝突回避）
  - infra module tests（静的スナップショット）
  - backend-api tests（FastAPI + SQLAlchemy）
  - eks-workers tests（Property Based Testing）
  - portal-lambda tests（Property Based Testing）
  - scripts tests + deploy syntax check
  - static safety scan（Secret/ARN 混入検出）

## 実AWS適用前の注意点

1. **dev/MVP 限定**: 本構成は dev 環境が対象。prod/staging は後続 Phase
2. **Aurora サイジング**: MVP 最小構成。prod では Aurora Provisioned 検討
3. **NAT Gateway コスト**: データ転送量を監視し、VPC エンドポイント検討
4. **WAF コスト**: リクエスト数に応じた料金設計
5. **CI/CD secrets**: AWS 認証情報・シークレットは GitHub Secrets で管理
6. **災害復旧**: backup/restore 戦略は MVP 範囲外
