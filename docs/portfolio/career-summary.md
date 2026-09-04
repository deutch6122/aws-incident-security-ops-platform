# 職務経歴書転用文

このドキュメントは、職務経歴書や案件面談でそのまま使える文章案です。**ポートフォリオ（自己学習プロジェクト）であることを明確に伝える**表現にしています。

---

## 3行要約

> AWS 上にセキュリティインシデント管理基盤を構築。ECS と EKS で同期・非同期処理を分离し、Aurora PostgreSQL と DynamoDB でデータを分離 хранить。Terraform で IaC、Property Based Testing で品质保证、GitHub Actions で CI/CD を 实现한ポートフォリオ です。

---

## 職務経歴書向けの実績文

### フォーマット例（1）

```
【AWS インフラ構築・otnet】
セキュリティインシデント管理基盤の構築を担当。

- ECS Fargate による Backend API（FastAPI）の 设计・実装
- EKS による非同期 Worker・CronJob の 设计・実装
- Aurora PostgreSQL（7テーブル）と DynamoDB（4テーブル）の DB 设计
- Product_A（内部運用基盤）と Product_B（公開ポータル）の分離设计
- A→B 一方向・非同期連携の実装（CronJob 主体）
- Terraform による module 分割（18 modules）のIaC
- GitHub Actions CI/CD（8 jobs）の 構築
- Property Based Testing（Hypothesis）によるテスト品质保证
- Cognito + API Gateway + Lambda + WAF + CloudFront の セキュア構成
- CloudWatch Alarm・Dashboards・SNS 通知の 监��设计

环境: AWS (ap-northeast-1) / Python 3.11 / Terraform/ECS/EKS/DynamoDB/Aurora
```

### フォーマット例（2）

```
【インフラエンジニア】
AWS を活用したクラウドインフラの構築・自动化を経験。

- Terraform を用いた Infrastructure as Code の实现（18 modules）
- ECS + EKS の ハイブリッド构成による 同期/非同期処理の分离
- Aurora Serverless v2 および DynamoDB の 選定と 设计
- CloudFront + S3（OAC） + WAF のセキュアな公开基盤構築
- Cognito + API Gateway + Lambda の サーバーレス API 構築
- GitHub Actions による 自动测试・静的 分析 pipeline 構築
- 监视设计（CloudWatch Alarm/Dashboard/SNS）の 実装
- Secret 管理（Secrets Manager）の 実装

技术: AWS / Terraform / Python / FastAPI / Kubernetes / GitHub Actions
```

---

## 案件面談向けの説明文

### 30秒バージョン

> セキュリティインシデント管理基盤のポートフォリオを作りました。AWS の ECS と EKS でシステムを构成し、Aurora と DynamoDB でデータを管理しています。Product_A と Product_B を明確に分离し、月次レポート作る 时にだけ A→B へデータを渡す 设计にしています。Terraform でインフラを 代码化し、Property Based Testing で 测试品质保证を行っています。

### 1分バージョン

> セキュリティインシデント管理基盤のポートフォリオを担当しました。AWS 上に、ECS Fargate で同期 API、EKS で非同期ワーカーを动かし、Aurora PostgreSQL にデータをためる Product_A と、CloudFront + Lambda + DynamoDB で构成される Product_B を構築しました。
> 
> 特徴は、Product_A と Product_B を明確に分离したことです。社内运用データと公开データを同一个 システムに混ぜず、月次レポート作る 时にだけ A→B へデータを渡す一方向设计にしています。これにより、一方の障害が他方へ波及する 的风险を軽減しています。
> 
> Terraform でインフラを module 分割（约18 modules）し、GitHub Actions で自动测试を 回しています。测试には Property Based Testing（Hypothesis）を取り入れており、バグの早期 发现を 检测しています。

### 详细バージョン

> **プロジェクト概要**
> - 名前: AWS Incident & Security Operations Platform
> - 目的: セキュリティインシデント・アラーム・Finding の管理と、関係者へのステータス公开
> - 环境: AWS dev（ap-northeast-1）
> 
> **担当工程**
> - 基本设计（ architecture 设计、DB 设计、API 设计）
> - 詳細设计・実装（Terraform / Python FastAPI / EKS Worker / Lambda）
> - 测试（Property Based Testing / 单元测试 / 統合测试）
> - CI/CD 構築（GitHub Actions / 静的解析 / safety scan）
> 
> **技术ハイライト**
> - ECS + EKS の ハイブリッド构成で 同期/非同期処理を分离
> - Aurora PostgreSQL（7テーブル） + DynamoDB（4テーブル）の DB 分离设计
> - Product_A / Product_B の 完全分离 + A→B 一方向連携
> - Terraform module 分割（18 modules）による IaC
> - Property Based Testing（Hypothesis）による 高品质 测试
> - Cognito JWT / WAF / OAC / Secrets Manager による セキュリティ强化

---

## 使用技术一览

| カテゴリ | 技术 |
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
| 编程言語 | Python 3.11 |
| Web フレームワーク | FastAPI |
| 测试 | pytest, Hypothesis (Property Based Testing) |
| 缓存 | Secrets Manager |

---

## 担当工程

| 工程 | 経験内容 |
| --- | --- |
| 基本设计 | アーキテクチャ設計、DB設計、API設計、セキュリティ設計 |
| 詳細设计・実装 | Terraform module 実装、Python アプリケーション実装、K8s manifest |
| 测试 | 单元测试、Property Based Testing、統合测试、snapshot 测试 |
| CI/CD 構築 | GitHub Actions workflow 設計、safety scan 実装 |
| 監視设计 | CloudWatch Alarm / Dashboard / SNS 実装 |

---

## アピールポイント

1. **AWS サービスの選定眼**: ECS/EKS/Aurora/DynamoDB/CloudFront など、责務に最適なサービスを選定した经验
2. **分离原则の実践**: Product_A / Product_B の 完全分离、Terraform module 分割
3. **A→B 一方向设计**: セキュリティと可用性を意识した架构判断
4. **テスト品质保证**: Property Based Testing（Hypothesis）による バグ早期発見
5. **CI/CD 整備**: 8 jobs の 自动测试、safety scan、deploy script 语法检查
6. **セキュリティ考虑**: Secrets Manager、Cognito JWT、WAF、OAC、最小権限 IAM

---

## 注意: 实的案件而非误认的表达

职务経歴書や案件面談で説明する际、以下の point に注意してくだい。

### ✅ 適切な表現

- 「ポートフォリオとして」
- 「自己学習プロジェクトとして」
- 「検証用/dev 環境で」
- 「MVP（Minimum Viable Product）として」
- 「学习用に構築した」

### ❌ 避けるべき表現

- 实的案件のように装う表现（「担当した案件」「本番环境」など）
- 实客户名や实的プロジェクト名を挙げる
- 实Secret、実ARN、実ドメインを话题にする

### 前置きの一例

> 「これは私のポートフォリオ（自己学習プロジェクト）で、AWS 上にセキュリティインシデント管理基盤を構築したものです。实的案件ではなく、云计算とアーキテクチャ设计を 学习する目的で作りました。」

这样、前置きをすることで、面试官也能正确理解这个项目的背景。

---

この文档はそのまま使うのではなく、自分の情况に合わせて调整してください。
特に「3行要約」「案件面談向けの说明文」は、事前に練習して自信を持って説明できるようにしましょう。
