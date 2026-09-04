# アーキテクチャ解説

AWS Incident & Security Operations Platform のアーキテクチャを詳しく解説します。

## 全体アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              全体アーキテクチャ                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────┐     ┌──────────────────────────────────────────┐ │
│  │      Operator        │     │              Viewer                      │ │
│  │   (社内運用者)        │     │           (Portal 閲覧者)                 │ │
│  └──────────┬───────────┘     └────────────────────┬───────────────────┘ │
│             │                                         │                    │
│             ▼                                         │                    │
│  ┌────────────────────────────────────────────────────▼─────────────────┐ │
│  │                       Product_A（内部運用基盤）                      │ │
│  │  ┌──────────┐    ┌──────────────┐    ┌──────────────────────────┐  │ │
│  │  │   ALB    │───▶│  ECS         │───▶│     Aurora PostgreSQL    │  │ │
│  │  │          │    │ Backend_API  │    │  (incidents/findings等)   │  │ │
│  │  └──────────┘    └──────────────┘    └──────────────────────────┘  │ │
│  │         │                │                      ▲                   │ │
│  │         │        ┌───────▼───────┐             │                   │ │
│  │         │        │  EKS Workers  │             │                   │ │
│  │         │        │  • alarm-event│             │                   │ │
│  │         │        │  • security-  │─────────────┘                   │ │
│  │         │        │    finding    │                                   │ │
│  │         │        │  • monthly-   │                                   │ │
│  │         │        │    summary    │                                   │ │
│  │         │        └───────────────┘                                   │ │
│  │         │                │                                            │ │
│  │         │        ┌───────▼───────┐    ┌──────────────────────────┐  │ │
│  │         │        │ EventBridge   │───▶│ SQS (Standard + DLQ)     │  │ │
│  │         │        │               │    │                          │  │ │
│  │         │        └───────────────┘    └──────────────────────────┘  │ │
│  └─────────┼────────────────────────────────────────────────────────────┘ │
│            │                                              │                │
│            │ A→B 一方向（非同期）                         │                │
│            ▼                                              ▼                │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │                    Product_B（公開ポータル）                          ││
│  │                                                                         ││
│  │  ┌──────────────┐    ┌──────────────┐    ┌────────────────────────┐ ││
│  │  │ CloudFront   │───▶│    S3        │    │   API Gateway          │ ││
│  │  │   + WAF      │    │  (OAC保護)   │    │   + Lambda             │ ││
│  │  └──────────────┘    └──────────────┘    │   + DynamoDB           │ ││
│  │         │                                   └────────────────────────┘ ││
│  │         │                    ┌─────────────────────────────────────────┤
│  │         │                    │            Cognito (JWT)               │
│  │         └────────────────────┴─────────────────────────────────────────┘
│  │                                        │
│  └────────────────────────────────────────┘
│                                           │
│  ┌────────────────────────────────────────▼───────────────────────────────┐
│  │                       監視・通知                                           │
│  │    CloudWatch Alarms (DLQ/ECS/ALB/Lambda/Aurora) → SNS → 通知         │
│  │    CloudWatch Dashboards (Product_A / Product_B 分離)                   │
│  └────────────────────────────────────────────────────────────────────────┘
```

## Product_A の役割

| コンポーネント | 責務 |
| --- | --- |
| **ECS + Backend_API** | FastAPI ベースの同期 API。Operator が incidents/findings/alarm_events/月次集計を管理。 |
| **EKS Workers** | 非同期処理。EventBridge → SQS 駆動でアラーム/Finding 取込、月次集計生成。 |
| **Aurora PostgreSQL** | 7 テーブル（incidents, findings, alarm_events, finding_triage, monthly_summaries, audit_logs, maintenance_windows）。 |
| **EventBridge + SQS** | アラーム/Finding イベントの受領とキューイング。DLQ で失敗処理。 |

## Product_B の役割

| コンポーネント | 責務 |
| --- | --- |
| **CloudFront + S3 + OAC** | 静的コンテンツのエッジ配信。OAC で S3 へのアクセスを CloudFront 経由に限定。 |
| **WAF** | エッジ保護。Rate Limit、IP ブロック、SQL インジェクション対策。 |
| **Cognito + API Gateway + Lambda** | Viewer 向け API。JWT 認証で保護。 |
| **DynamoDB** | 4 テーブル（public_status_items, report_metadata, page_view_logs, maintenance_windows）。 |

## Backend API / ECS の説明

- **ECS Fargate**: サーバーレスコンテナ実行。ALB 配下でリクエスト処理。
- **Backend_API（FastAPI）**:
  - `GET /dashboard/summary`: インシデント/Finding 件数統計
  - `GET/POST /incidents`, `PATCH /incidents/{id}/status`: インシデント管理
  - `GET /findings`: Finding 一覧
  - `GET /monthly-summaries`: 月次集計
  - 状態変更時に `audit_logs` に記録（Property 6）

## EKS Workers の説明

| Worker | 処理内容 |
| --- | --- |
| **alarm-event-processor** | SQS からアラームイベントを取得し、`alarm_events` テーブルへ upsert（`external_id` UNIQUE で冪等） |
| **security-finding-worker** | SQS から Finding 風イベントを取得し、`findings` / `finding_triage` へ登録（同一 `external_id` は重複しない） |
| **monthly-summary-cronjob** | 月次集計を実行し、A→B 連携の唯一の実行主体として Portal_Storage / report_metadata / public_status_items へ反映 |

## Aurora PostgreSQL の説明

7 テーブル設計:
- **incidents**: インシデント管理（id, title, status, severity, created_at, updated_at）
- **findings**: セキュリティ Finding（id, external_id, title, severity, status）
- **alarm_events**: アラーム取込履歴（id, external_id, alarm_name, source, created_at）
- **finding_triage**: Finding のトリアージ結果（finding_id, triage_status, assigned_to）
- **monthly_summaries**: 月次集計（id, period, incident_count, finding_count, created_at）
- **audit_logs**: 状態変更履歴（id, entity_type, entity_id, field, old_value, new_value, changed_at）
- **maintenance_windows**: メンテナンス時間帯定義

## SQS / EventBridge の説明

- **EventBridge**: アラーム/Finding イベントの入り口。カスタムイベントバス不使用。
- **SQS Standard**: メッセージ処理。失敗時に再配送し、上限超過分は DLQ へ退避。
- **DLQ**: 処理に失敗したメッセージを集約。DLQ > 0 で CloudWatch Alarm 発報。

## CloudFront / S3 OAC / WAF の説明

- **CloudFront**: エッジ配信。PriceClass 100（日本東京）。
- **OAC（Origin Access Control）**: S3 へのアクセスを CloudFront 経由に限定。直接アクセスをブロック。
- **WAF**: 
  - Rate-based rule（1 分あたり 1000 リクエスト 超過でブロック）
  - IP reputation block（AWSManagedRulesAnonymousIpList）
  - SQL injection rule

## Cognito / API Gateway / Lambda の説明

- **Cognito User Pool**: Viewer 用ユーザープール。JWT 発行。
- **API Gateway**: Product_B の API エントリ。Cognito Authorizer で JWT 検証。
- **Lambda（Portal_API）**: 
  - `GET /api/status`: 公開ステータス一覧
  - `GET /api/status/{id}`: 個別ステータス
  - `GET /api/reports`: レポート一覧
  - `GET /api/reports/{id}`: レポート詳細
  - 閲覧ごとに `page_view_logs` を increment（Property 10）

## CloudWatch / SNS monitoring の説明

| アラーム | 対象リソース |
| --- | --- |
| SQS DLQ > 0 | DLQ メッセージ滞留 |
| ECS CPU / Memory / タスク数 | Backend_API コンテナ |
| ALB 5xx / Latency | Product_A ALB |
| Lambda Errors / Throttles / Duration | Portal_API Lambda |
| Aurora ACU / Connection Count | Aurora クラスタ |

- **ダッシュボード**: Product_A / Product_B を分離した 2 ダッシュボード
- **SNS 通知**: アラーム発報時にトピック経由で通知

## Terraform module 分割の意図

| Module | 責務 |
| --- | --- |
| `network` | VPC/Subnet/SG/NAT/IGW/VPCエンドポイント |
| `ecr` | ECR リポジトリ |
| `alb` | ALB / Target Group / リスナー |
| `ecs` | ECS cluster / task / service |
| `eks` | EKS cluster / Fargate Profile / IRSA |
| `aurora` | Aurora Serverless v2 |
| `messaging` | SQS + DLQ + EventBridge |
| `s3-portal` | Portal_Storage（OAC 保護） |
| `cloudfront` | CloudFront + OAC + WAF 統合 |
| `cognito` | Cognito User Pool / App Client |
| `apigateway` | API Gateway（Cognito Authorizer） |
| `lambda` | Portal_API Lambda |
| `dynamodb` | 4 テーブル（GSI/TTL 設計） |
| `logging` | CloudWatch Logs グループ |
| `monitoring` | CloudWatch Alarm / Dashboard / SNS |
| `iam` | 最小権限 IAM ロール |

- **再利用性**: 環境間で module を流用可能
- **可読性**: インフラ構成が明らかになる

## dev root 未実装モジュールの理由

`infra/environments/dev` ルートは現状 **network / ecr / aurora** のみを wiring しています。未 wiring の module は依存値（ARN / issuer / domain 等）が未確定のためです。

| 未 wiring module | 渡す必要がある値 |
| --- | --- |
| alb / ecs / eks | network, ecr, aurora |
| messaging / logging | SQS ARN, EventBridge, Logs |
| dynamodb | テーブル ARN → lambda |
| s3-portal | → cloudfront |
| cloudfront | s3-portal, apigateway, WAF |
| cognito | → apigateway |
| apigateway | lambda invoke ARN |
| lambda | dynamodb, CloudWatch |
| monitoring | 各リソース識別子 |

## Terraform と App Deploy を分離した理由

| 観点 | Infra_Pipeline | App_Deploy |
| --- | --- | --- |
| 変更頻度 | 低（週〜月単位） | 高（日〜週単位） |
| 影響範囲 | 全体（VPC/DB 等） | 局所（コンテナ/静的ファイル） |
| 実行コスト | 高（リソース作成） | 低（コンテナ更新） |
| 承認要件 | 手動承認必須 | 任意（dry-run 既定） |
| terraform 呼び出し | 行う | 行わない |

- **Infrastructure as Code**: Terraform で管理
- **App Deploy**: コンテナビルド・ECR プッシュ・ECS/EKS 更新
- **分離の利点**: インフラ変更とアプリ変更を独立してリリース可能
