# 職務経歴書転用文

このドキュメントは、職務経歴書や案件面談でそのまま使える文章案です。**ポートフォリオ（自己学習プロジェクト）であることを明確に伝える**表現にしています。

---

## 3行要約

> AWS 上にセキュリティインシデント管理基盤を構築。ECS と EKS で同期・非同期処理を分離し、Aurora PostgreSQL と DynamoDB でデータを分離して永続化。Terraform で IaC、Property Based Testing で品質保証、GitHub Actions で CI/CD を実現したポートフォリオです。

---

## 職務経歴書向けの実績文

### フォーマット例（1）

```
【AWS インフラ構築】
セキュリティインシデント管理基盤の構築を担当。

- ECS Fargate による Backend API（FastAPI）の設計・実装
- EKS による非同期 Worker・CronJob の設計・実装
- Aurora PostgreSQL（7テーブル）と DynamoDB（4テーブル）の DB 設計
- Product_A（内部運用基盤）と Product_B（公開ポータル）の分離設計
- A→B 一方向・非同期連携の実装（CronJob 主体）
- Terraform による module 分割（18 modules）の IaC
- GitHub Actions CI/CD（8 jobs）の構築
- Property Based Testing（Hypothesis）によるテスト品質保証
- Cognito + API Gateway + Lambda + WAF + CloudFront のセキュア構成
- CloudWatch Alarm・Dashboards・SNS 通知の監視設計

環境: AWS (ap-northeast-1) / Python 3.11 / Terraform / ECS / EKS / DynamoDB / Aurora
```

### フォーマット例（2）

```
【インフラエンジニア】
AWS を活用したクラウドインフラの構築・自動化を経験。

- Terraform を用いた Infrastructure as Code の実現（18 modules）
- ECS + EKS のハイブリッド構成による同期/非同期処理の分離
- Aurora Serverless v2 および DynamoDB の選定と設計
- CloudFront + S3（OAC） + WAF のセキュアな公開基盤構築
- Cognito + API Gateway + Lambda のサーバーレス API 構築
- GitHub Actions による自動テスト・静的解析パイプライン構築
- 監視設計（CloudWatch Alarm/Dashboard/SNS）の実装
- Secret 管理（Secrets Manager）の実装

技術: AWS / Terraform / Python / FastAPI / Kubernetes / GitHub Actions
```

---

## 案件面談向けの説明文

### 30秒バージョン

> セキュリティインシデント管理基盤のポートフォリオを作りました。AWS の ECS と EKS でシステムを構成し、Aurora と DynamoDB でデータを管理しています。Product_A と Product_B を明確に分離し、月次レポートを作るときにだけ A→B へデータを渡す設計にしています。Terraform でインフラをコード化し、Property Based Testing でテスト品質保証を行っています。

### 1分バージョン

> セキュリティインシデント管理基盤のポートフォリオを担当しました。AWS 上に、ECS Fargate で同期 API、EKS で非同期ワーカーを動かし、Aurora PostgreSQL にデータをためる Product_A と、CloudFront + Lambda + DynamoDB で構成される Product_B を構築しました。
> 
> 特徴は、Product_A と Product_B を明確に分離したことです。社内運用データと公開データを同一のシステムに混ぜず、月次レポートを作るときにだけ A→B へデータを渡す一方向設計にしています。これにより、一方の障害が他方へ波及するリスクを軽減しています。
> 
> Terraform でインフラを module 分割（約18 modules）し、GitHub Actions で自動テストを回しています。テストには Property Based Testing（Hypothesis）を取り入れており、バグの早期発見に努めています。

### 詳細バージョン

> **プロジェクト概要**
> - 名前: AWS Incident & Security Operations Platform
> - 目的: セキュリティインシデント・アラーム・Finding の管理と、関係者へのステータス公開
> - 環境: AWS dev（ap-northeast-1）
> 
> **担当工程**
> - 基本設計（アーキテクチャ設計、DB 設計、API 設計）
> - 詳細設計・実装（Terraform / Python FastAPI / EKS Worker / Lambda）
> - テスト（Property Based Testing / 単体テスト / 統合テスト）
> - CI/CD 構築（GitHub Actions / 静的解析 / safety scan）
> 
> **技術ハイライト**
> - ECS + EKS のハイブリッド構成で同期/非同期処理を分離
> - Aurora PostgreSQL（7テーブル） + DynamoDB（4テーブル）の DB 分離設計
> - Product_A / Product_B の完全分離 + A→B 一方向連携
> - Terraform module 分割（18 modules）による IaC
> - Property Based Testing（Hypothesis）による高品質テスト
> - Cognito JWT / WAF / OAC / Secrets Manager によるセキュリティ強化

---

## 使用技術一覧

| カテゴリ | 技術 |
| --- | --- |
| クラウド | AWS (ap-northeast-1) |
| コンテナ | ECS Fargate, EKS (Fargate Profile) |
| データベース | Aurora Serverless v2 (PostgreSQL), DynamoDB |
| サーバーレス | Lambda, API Gateway |
| CDN・セキュリティ | CloudFront, S3 (OAC), WAF, Cognito |
| メッセージング | SQS, EventBridge |
| 監視 | CloudWatch (Alarm, Dashboard, Logs), SNS |
| IaC | Terraform |
| CI/CD | GitHub Actions |
| プログラミング言語 | Python 3.11 |
| Web フレームワーク | FastAPI |
| テスト | pytest, Hypothesis (Property Based Testing) |
| Secret 管理 | Secrets Manager |

---

## 担当工程

| 工程 | 経験内容 |
| --- | --- |
| 基本設計 | アーキテクチャ設計、DB 設計、API 設計、セキュリティ設計 |
| 詳細設計・実装 | Terraform module 実装、Python アプリケーション実装、K8s manifest |
| テスト | 単体テスト、Property Based Testing、統合テスト、snapshot テスト |
| CI/CD 構築 | GitHub Actions workflow 設計、safety scan 実装 |
| 監視設計 | CloudWatch Alarm / Dashboard / SNS 実装 |

---

## アピールポイント

1. **AWS サービスの選定眼**: ECS/EKS/Aurora/DynamoDB/CloudFront など、責務に最適なサービスを選定した経験
2. **分離原則の実践**: Product_A / Product_B の完全分離、Terraform module 分割
3. **A→B 一方向設計**: セキュリティと可用性を意識したアーキテクチャ判断
4. **テスト品質保証**: Property Based Testing（Hypothesis）によるバグ早期発見
5. **CI/CD 整備**: 8 jobs の自動テスト、safety scan、deploy script 構文チェック
6. **セキュリティ考慮**: Secrets Manager、Cognito JWT、WAF、OAC、最小権限 IAM

---

## 注意: 実案件ではなくポートフォリオであることを誤認されない表現

職務経歴書や案件面談で説明する際、以下のポイントに注意してください。

### 適切な表現

- 「ポートフォリオとして」
- 「自己学習プロジェクトとして」
- 「検証用/dev 環境で」
- 「MVP（Minimum Viable Product）として」
- 「学習用に構築した」

### 避けるべき表現

- 実案件のように装う表現（「担当した案件」「本番環境」など）
- 実際の顧客名や実案件のプロジェクト名を挙げる
- 実 Secret、実 ARN、実ドメインを話題にする

### 前置きの一例

> 「これは私のポートフォリオ（自己学習プロジェクト）で、AWS 上にセキュリティインシデント管理基盤を構築したものです。実案件ではなく、クラウドとアーキテクチャ設計を学習する目的で作りました。」

このように前置きをすることで、面接官もこのプロジェクトの背景を正しく理解できます。

---

このドキュメントはそのまま使うのではなく、自分の状況に合わせて調整してください。
特に「3行要約」「案件面談向けの説明文」は、事前に練習して自信を持って説明できるようにしましょう。
