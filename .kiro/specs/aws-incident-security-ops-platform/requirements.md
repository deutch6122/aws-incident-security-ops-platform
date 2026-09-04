# Requirements Document

## Introduction

本ドキュメントは、AWS 上に構築するポートフォリオ兼実務想定の成果物「AWS Incident & Security Operations Platform（成果物A）」および「CloudFront Status & Report Portal（成果物B）」の要件を定義する。

成果物Aは、社内運用担当者がインシデント・アラーム・セキュリティ検出結果・対応履歴・月次集計を管理する内部運用基盤である。ECS Fargate（同期API）と EKS（非同期ワーカー/CronJob）を役割分担し、Aurora PostgreSQL にデータを永続化する。

成果物Bは、障害ステータス・メンテナンス情報・月次レポートを関係者が閲覧する軽量な公開・配信ポータルである。CloudFront + S3 + OAC + WAF + Cognito + API Gateway + Lambda + DynamoDB で構成する。

両成果物は無理に統合せず疎結合を保ち、成果物Aで生成した月次レポート/公開ステータス情報を成果物Bで閲覧する **緩やかな一方向連携（A→B）** のみを許容する。

本フェーズでは dev 環境で動作する MVP を優先しつつ、商用運用を意識したネットワーク・IAM・ログ・監視・セキュリティ・IaC 設計を要件へ反映する。設計理由の文章化、コストを抑えた代替案の提示、承認前の terraform apply 抑止を重視する。

すべての要件は EARS パターンと INCOSE 品質ルールに従う。設計・実装の詳細は design.md 以降で扱う（本書は「何を（What）」に集中する）。

---

## Glossary

- **Platform**: 成果物A（AWS Incident & Security Operations Platform）と成果物B（CloudFront Status & Report Portal）を包含する成果物全体の総称。
- **Product_A**: 成果物A。ECS/EKS を用いた内部運用・処理基盤。
- **Product_B**: 成果物B。CloudFront を用いた公開・閲覧・配信ポータル。
- **Backend_API**: Product_A の ECS Fargate 上で稼働する同期バックエンド API（第一候補言語=Python FastAPI）。
- **Worker_Alarm**: EKS 上の `alarm-event-processor`。アラーム風イベントを取り込み処理するワーカー。
- **Worker_Finding**: EKS 上の `security-finding-worker`。Security Hub 風 Finding を分類・処理するワーカー。
- **Cronjob_Summary**: EKS 上の `monthly-summary-cronjob`。月次集計を生成する定期ジョブ。
- **Aurora_DB**: Product_A のデータストア（Aurora PostgreSQL、第一候補 Aurora Serverless v2）。
- **Event_Bus**: EventBridge によるイベント入口。
- **Message_Queue**: SQS Standard Queue（DLQ を伴う）。
- **Portal_CDN**: Product_B の CloudFront ディストリビューション。
- **Portal_Storage**: Product_B の静的サイト/レポート格納用 S3 バケット。
- **Portal_API**: Product_B の API Gateway + Lambda で構成する軽量 API。
- **Portal_DB**: Product_B の DynamoDB（`public_status_items` / `report_metadata` / `page_view_logs` / `maintenance_windows`）。
- **WAF_Policy**: Product_B の CloudFront に関連付ける AWS WAF Web ACL。
- **Auth_Service**: Product_B の閲覧者認証を提供する Amazon Cognito。
- **Bootstrap_Stack**: ローカルから初回のみ terraform apply する土台リソース群（remote state 用 S3、state lock 設定、CodePipeline、CodeBuild、artifact 用 S3、Terraform 実行用 IAM Role）。
- **Infra_Pipeline**: 本体インフラを terraform で作成・更新する CodePipeline + CodeBuild。
- **App_Deploy**: アプリケーション（ECS/EKS/CloudFront）のデプロイ工程。インフラ apply とは分離する。
- **Operator**: Product_A を利用する社内運用担当者。
- **Viewer**: Product_B を閲覧する関係者（認証済み利用者）。
- **Platform_Engineer**: Platform の構築・運用・デプロイを行う担当者。
- **MVP**: dev 環境で動作する最小実装範囲。
- **Region**: デプロイ対象リージョン（`ap-northeast-1`）。
- **Naming_Convention**: リソース命名規則 `project-env-resource`（project 名=`ops-platform`、env=`dev`）。

---

## Requirements

### Requirement 1: 成果物A・B の分離と緩やかな連携

**User Story:** As a Platform_Engineer, I want Product_A と Product_B を疎結合で設計し A→B の一方向連携のみを許容したい, so that それぞれを独立して構築・運用でき、ポートフォリオとして分離の設計思想を説明できる。

#### Acceptance Criteria

1. THE Platform SHALL Product_A と Product_B を独立したコンポーネントとして定義する。
2. THE Platform SHALL Product_A から Product_B への一方向のデータ連携（月次レポートおよび公開ステータス情報）のみを許容する。
3. IF Product_B から Product_A への同期呼び出しが要求された場合, THEN THE Platform SHALL 当該連携を要件対象外として拒否する。
4. WHEN Product_A が月次レポートまたは公開ステータス情報を生成する, THE Platform SHALL 当該データを Product_B が参照可能な連携経路（Portal_DB または Portal_Storage）へ受け渡す。
5. THE Platform SHALL Product_A と Product_B を単一システムへ統合しない構成で定義する。

### Requirement 2: 成果物A ダッシュボード API

**User Story:** As an Operator, I want ダッシュボード API を通じて運用状況の要約を取得したい, so that インシデントと Finding の現況を一覧で把握できる。

#### Acceptance Criteria

1. WHEN Operator がダッシュボード API へ要求を送信する, THE Backend_API SHALL インシデント件数・Finding 件数・対応ステータス別集計を含む要約データを返却する。
2. THE Backend_API SHALL Aurora_DB を参照してダッシュボードの集計値を取得する。
3. IF ダッシュボード API 要求に有効な認可情報が付与されていない場合, THEN THE Backend_API SHALL HTTP 401 応答を返却する。

### Requirement 3: 成果物A インシデント管理 API

**User Story:** As an Operator, I want インシデントの一覧・詳細・作成・ステータス更新を行いたい, so that インシデント対応を記録・追跡できる。

#### Acceptance Criteria

1. WHEN Operator がインシデント一覧 API へ要求を送信する, THE Backend_API SHALL 登録済みインシデントの一覧を返却する。
2. WHEN Operator がインシデント ID を指定して詳細 API へ要求を送信する, THE Backend_API SHALL 当該インシデントの詳細と対応履歴（incident_comments）を返却する。
3. IF 指定されたインシデント ID が Aurora_DB に存在しない場合, THEN THE Backend_API SHALL HTTP 404 応答を返却する。
4. WHEN Operator が必須項目を満たしたインシデント作成 API 要求を送信する, THE Backend_API SHALL 新規インシデントを Aurora_DB の incidents テーブルへ登録する。
5. IF インシデント作成 API 要求に必須項目が欠落している場合, THEN THE Backend_API SHALL HTTP 400 応答と欠落項目を示すエラー内容を返却する。
6. WHEN Operator がインシデントステータス更新 API 要求を送信する, THE Backend_API SHALL 当該インシデントのステータスを更新し、変更内容を audit_logs テーブルへ記録する。

### Requirement 4: 成果物A セキュリティ Finding 参照 API

**User Story:** As an Operator, I want Security Finding の一覧と詳細を参照したい, so that 検出されたセキュリティリスクを確認できる。

#### Acceptance Criteria

1. WHEN Operator が Finding 一覧 API へ要求を送信する, THE Backend_API SHALL findings テーブルの Finding 一覧を返却する。
2. WHEN Operator が Finding ID を指定して Finding 詳細 API へ要求を送信する, THE Backend_API SHALL 当該 Finding の詳細と finding_triage 情報を返却する。
3. IF 指定された Finding ID が Aurora_DB に存在しない場合, THEN THE Backend_API SHALL HTTP 404 応答を返却する。

### Requirement 5: 成果物A 月次集計 API

**User Story:** As an Operator, I want 月次集計データを取得したい, so that 月単位の運用状況を把握しレポートに利用できる。

#### Acceptance Criteria

1. WHEN Operator が対象年月を指定して月次集計 API へ要求を送信する, THE Backend_API SHALL monthly_summaries テーブルから当該年月の集計データを返却する。
2. IF 指定された年月の集計データが Aurora_DB に存在しない場合, THEN THE Backend_API SHALL HTTP 404 応答を返却する。

### Requirement 6: 成果物A 非同期イベント取り込み

**User Story:** As a Platform_Engineer, I want EventBridge→SQS 経由でサンプルイベントを非同期に取り込みたい, so that 実運用に近いイベント駆動処理を再現できる。

#### Acceptance Criteria

1. WHEN サンプルイベントが Event_Bus へ送信される, THE Event_Bus SHALL 当該イベントを Message_Queue へ配送する。
2. WHEN Message_Queue にアラーム風イベントが到達する, THE Worker_Alarm SHALL 当該イベントを取得し、alarm_events テーブルへ登録する。
3. WHEN Message_Queue にセキュリティ Finding 風イベントが到達する, THE Worker_Finding SHALL 当該イベントの重大度・リソース種別・対応ステータスを判定し、findings テーブルおよび finding_triage テーブルへ登録する。
4. IF Message_Queue のメッセージ処理が規定回数失敗した場合, THEN THE Message_Queue SHALL 当該メッセージを DLQ へ移動する。
5. THE Worker_Alarm SHALL Message_Queue から取得し処理が完了したメッセージを Message_Queue から削除する。

### Requirement 7: 成果物A 月次集計ジョブ

**User Story:** As a Platform_Engineer, I want 月次集計を定期的に生成したい, so that 月次レポートの元データを自動作成できる。

#### Acceptance Criteria

1. WHEN Cronjob_Summary が実行される, THE Cronjob_Summary SHALL 対象期間の incidents・findings・alarm_events を集計し、monthly_summaries テーブルへ登録する。
2. WHERE 同一対象年月の集計が既に存在する場合, THE Cronjob_Summary SHALL 当該年月の集計データを最新の集計結果で更新する。

### Requirement 8: 成果物A データ永続化

**User Story:** As a Platform_Engineer, I want 運用データを Aurora PostgreSQL に永続化したい, so that インシデント・Finding・履歴・監査ログ・集計を一貫して保存できる。

#### Acceptance Criteria

1. THE Aurora_DB SHALL incidents・incident_comments・findings・finding_triage・alarm_events・monthly_summaries・audit_logs の各テーブルを保持する。
2. WHEN Backend_API または EKS ワーカーがデータ書き込みを実行する, THE Aurora_DB SHALL 当該データを永続化する。
3. WHEN Operator がインシデントまたは Finding の状態を変更する, THE Backend_API SHALL 変更操作を audit_logs テーブルへ記録する。

### Requirement 9: 成果物B 閲覧者認証

**User Story:** As a Viewer, I want ログイン画面から認証したい, so that 許可された関係者のみがステータスとレポートを閲覧できる。

#### Acceptance Criteria

1. WHEN Viewer が有効な資格情報でログイン要求を送信する, THE Auth_Service SHALL 認証トークンを発行する。
2. IF Viewer が無効な資格情報でログイン要求を送信する場合, THEN THE Auth_Service SHALL 認証を拒否しエラー応答を返却する。
3. IF Portal_API へ有効な認証トークンを伴わない要求が到達する場合, THEN THE Portal_API SHALL HTTP 401 応答を返却する。

### Requirement 10: 成果物B ステータス閲覧

**User Story:** As a Viewer, I want 障害ステータスと詳細を閲覧したい, so that 現在の障害状況を確認できる。

#### Acceptance Criteria

1. WHEN 認証済み Viewer が障害ステータスページを要求する, THE Portal_API SHALL Portal_DB の public_status_items から現在の障害ステータス一覧を返却する。
2. WHEN 認証済み Viewer が特定の障害詳細を要求する, THE Portal_API SHALL 当該障害の詳細情報を返却する。
3. WHEN 認証済み Viewer がステータスページまたは詳細ページを閲覧する, THE Portal_API SHALL 閲覧記録を Portal_DB の page_view_logs へ登録する。

### Requirement 11: 成果物B 月次レポート閲覧

**User Story:** As a Viewer, I want 月次レポートの一覧と詳細を閲覧したい, so that 過去の運用レポートを参照できる。

#### Acceptance Criteria

1. WHEN 認証済み Viewer が月次レポート一覧ページを要求する, THE Portal_API SHALL Portal_DB の report_metadata からレポート一覧を返却する。
2. WHEN 認証済み Viewer が特定のレポート詳細を要求する, THE Portal_API SHALL 当該レポートのメタ情報と Portal_Storage 上のレポートファイル参照情報を返却する。
3. IF 指定されたレポートが Portal_DB に存在しない場合, THEN THE Portal_API SHALL HTTP 404 応答を返却する。

### Requirement 12: 成果物B 配信とオリジン保護

**User Story:** As a Platform_Engineer, I want CloudFront + OAC で S3 を保護しつつ配信したい, so that S3 を直接公開せずに安全に静的コンテンツを配信できる。

#### Acceptance Criteria

1. THE Portal_CDN SHALL Viewer 向けコンテンツを HTTPS で配信する。
2. THE Portal_Storage SHALL S3 public access block を有効化した状態で構成する。
3. IF Portal_Storage への要求が Portal_CDN の OAC 経由でない場合, THEN THE Portal_Storage SHALL 当該要求を拒否する。
4. THE Portal_CDN SHALL Portal_Storage を REST オリジンとして参照する。

### Requirement 13: 成果物B Web 保護（WAF）

**User Story:** As a Platform_Engineer, I want CloudFront に WAF を関連付けたい, so that 基本的な Web 攻撃とアクセス過多を抑止できる。

#### Acceptance Criteria

1. THE WAF_Policy SHALL Portal_CDN に関連付けられた状態で構成する。
2. THE WAF_Policy SHALL AWS Managed Rules を1つ以上適用する。
3. WHEN 単一送信元からの要求が設定した閾値を超過する, THE WAF_Policy SHALL Rate-based rule に基づき当該要求を制限する。

### Requirement 14: A→B レポート/ステータス連携

**User Story:** As a Platform_Engineer, I want Product_A の月次レポートと公開ステータスを Product_B へ反映したい, so that 運用基盤で生成した情報を関係者が閲覧できる。

#### Acceptance Criteria

1. WHEN Product_A が月次レポートを確定する, THE Platform SHALL 当該レポートのメタ情報を Portal_DB の report_metadata へ、レポートファイルを Portal_Storage へ反映する。
2. WHEN Product_A が公開用ステータスを更新する, THE Platform SHALL 当該ステータスを Portal_DB の public_status_items へ反映する。
3. THE Platform SHALL A→B 連携を一方向データ受け渡しとして定義し、Product_B から Product_A への書き込みを行わない構成とする。

### Requirement 15: ネットワークと通信制御

**User Story:** As a Platform_Engineer, I want VPC/Subnet/Security Group を必要最小限で設計したい, so that 商用運用を意識した安全なネットワーク境界を構成できる。

#### Acceptance Criteria

1. THE Product_A SHALL VPC・Subnet・Security Group・ALB を含むネットワーク構成で定義する。
2. THE Security Group SHALL 業務上必要な通信経路のみを許可する規則で構成する。
3. WHEN Operator が Backend_API へアクセスする, THE Product_A SHALL ALB 経由で Backend_API へ要求を到達させる。
4. THE Aurora_DB SHALL 許可されたアプリケーションコンポーネントからのみ接続可能なネットワーク境界内に配置する。

### Requirement 16: 認証情報とシークレット管理

**User Story:** As a Platform_Engineer, I want シークレットをコードに含めずに管理したい, so that 認証情報漏洩リスクを低減できる。

#### Acceptance Criteria

1. THE Platform SHALL DB パスワードおよびシークレットをソースコードおよび IaC の平文へ含めない構成で定義する。
2. WHEN アプリケーションコンポーネントが DB パスワードを必要とする, THE Platform SHALL シークレット管理サービス経由で当該値を取得する構成とする。
3. THE Platform SHALL `.gitignore` によりシークレットおよびローカル state を含む機微ファイルをバージョン管理対象外とする。

### Requirement 17: 最小権限 IAM

**User Story:** As a Platform_Engineer, I want IAM を最小権限で設計したい, so that 権限過多による影響範囲を抑えられる。

#### Acceptance Criteria

1. THE Platform SHALL 各コンポーネントの IAM ロールを、その機能遂行に必要な権限のみで構成する。
2. THE Bootstrap_Stack SHALL Terraform 実行用 IAM Role を定義する。
3. WHERE コンポーネントが AWS リソースへアクセスする, THE Platform SHALL 当該アクセスに必要な権限のみを付与する。

### Requirement 18: ログと監視

**User Story:** As a Platform_Engineer, I want ログを集約し監視できるようにしたい, so that 運用状況とトラブルシューティングに必要な情報を得られる。

#### Acceptance Criteria

1. THE Product_A SHALL ECS・EKS・Lambda のログを CloudWatch Logs へ集約する構成で定義する。
2. WHEN Backend_API または EKS ワーカーが処理を実行する, THE Product_A SHALL 実行ログを CloudWatch Logs へ出力する。
3. THE Portal_API SHALL Lambda 実行ログを CloudWatch Logs へ出力する。

### Requirement 19: リソース識別と既存環境への非干渉

**User Story:** As a Platform_Engineer, I want 明確な命名規則とタグを付与したい, so that 既存 AWS 環境へ影響を与えずリソースを識別できる。

#### Acceptance Criteria

1. THE Platform SHALL リソースを命名規則 `project-env-resource`（project=`ops-platform`、env=`dev`）に従って命名する。
2. THE Platform SHALL 作成する全リソースへ Platform を識別するタグを付与する。
3. THE Platform SHALL リソースを Region（`ap-northeast-1`）に作成する。

### Requirement 20: Terraform 構成と remote backend

**User Story:** As a Platform_Engineer, I want Terraform を module 化し remote backend で管理したい, so that 再利用性と state 管理を確立できる。

#### Acceptance Criteria

1. THE Platform SHALL インフラを Terraform で定義する。
2. THE Platform SHALL Terraform を `infra/environments/dev` と `infra/modules/*` の構成で定義する。
3. THE Infra_Pipeline SHALL Terraform state を remote backend（S3 + DynamoDB lock）で管理する。
4. WHERE 初期構築段階である場合, THE Bootstrap_Stack SHALL remote state 用 S3 バケットと state lock 設定を作成する。

### Requirement 21: Bootstrap と CI/CD パイプライン

**User Story:** As a Platform_Engineer, I want 本体インフラを CodePipeline+CodeBuild から Terraform 実行したい, so that ローカル継続 apply を避け、承認付きで安全にインフラを更新できる。

#### Acceptance Criteria

1. THE Bootstrap_Stack SHALL remote state 用 S3・state lock 設定・CodePipeline・CodeBuild・artifact 用 S3・Terraform 実行用 IAM Role を作成する。
2. WHEN main ブランチへの merge または push が発生する, THE Infra_Pipeline SHALL パイプラインを起動する。
3. WHEN Infra_Pipeline が実行される, THE Infra_Pipeline SHALL `terraform fmt`・`terraform validate`・`terraform plan`・手動承認・`terraform apply` の順で処理を実行する。
4. IF 手動承認が付与されていない場合, THEN THE Infra_Pipeline SHALL `terraform apply` を実行しない。
5. THE Platform SHALL 本体インフラの作成・更新をローカル端末からの継続的 terraform apply では行わない構成とする。

### Requirement 22: アプリケーションデプロイの分離

**User Story:** As a Platform_Engineer, I want アプリデプロイをインフラ apply から分離したい, so that インフラとアプリを独立して安全にリリースできる。

#### Acceptance Criteria

1. THE App_Deploy SHALL インフラの terraform apply 工程と分離した工程で定義する。
2. WHEN Backend_API をデプロイする, THE App_Deploy SHALL Docker build・ECR push・ECS service update の順で処理を実行する。
3. WHEN EKS ワーカーをデプロイする, THE App_Deploy SHALL Docker build・ECR push・`kubectl apply` または Helm upgrade により処理を実行する。
4. WHEN Product_B のフロントエンドをデプロイする, THE App_Deploy SHALL frontend build・S3 sync・CloudFront invalidation の順で処理を実行する。

### Requirement 23: 変更影響の事前提示と承認

**User Story:** As a Platform_Engineer, I want apply 前に作成・変更・削除予定リソースとコスト影響を確認したい, so that 意図しない変更やコスト増を防げる。

#### Acceptance Criteria

1. WHEN Infra_Pipeline が `terraform plan` を実行する, THE Infra_Pipeline SHALL 作成予定・変更予定・削除予定リソースの一覧を提示する。
2. WHEN Infra_Pipeline が変更内容を提示する, THE Infra_Pipeline SHALL コスト影響が大きいリソースを明示する。
3. IF 承認者が変更内容を承認していない場合, THEN THE Infra_Pipeline SHALL `terraform apply` を保留する。

### Requirement 24: コスト最適化

**User Story:** As a Platform_Engineer, I want dev 環境で小さいスペックから開始したい, so that コストを抑えつつ MVP を運用できる。

#### Acceptance Criteria

1. THE Platform SHALL dev 環境のみを対象として構成する。
2. THE Backend_API SHALL ECS Fargate 上で desired_count=1、CPU=0.25 vCPU 相当、Memory=0.5〜1GB 相当の初期最小構成で稼働する。
3. THE Aurora_DB SHALL 最小 ACU=0.5、最大 ACU=2 の Aurora Serverless v2 を第一候補として構成する。
4. WHERE Aurora Serverless v2 のコストが制約を超える場合, THE Platform SHALL RDS PostgreSQL single-AZ（db.t4g.micro 相当）を代替案として提示する。
5. THE Portal_DB SHALL DynamoDB Billing mode を PAY_PER_REQUEST として構成する。
6. THE Portal_CDN SHALL コスト優先の Price Class で構成する。
7. WHERE 特定コンポーネントがコスト影響の大きいリソースを含む場合, THE Platform SHALL 安価な代替案を設計文書に明記する。

### Requirement 25: スケーリングの設計含有（MVP 非必須）

**User Story:** As a Platform_Engineer, I want Auto Scaling/HPA を設計に含めつつ MVP では最小化したい, so that 将来の負荷増へ拡張でき、かつ初期コストを抑えられる。

#### Acceptance Criteria

1. THE Product_A SHALL ECS Auto Scaling を設計に含める。
2. WHERE MVP 段階である場合, THE Product_A SHALL ECS Auto Scaling を無効または最小構成とする。
3. THE Product_A SHALL EKS の HPA を設計に含める。
4. WHERE MVP 段階である場合, THE Product_A SHALL HPA を必須実装対象外とする。

### Requirement 26: ドキュメントと運用手順

**User Story:** As a Platform_Engineer, I want 構築・削除手順と設計理由を文書化したい, so that ポートフォリオとして説明でき、安全に運用・撤去できる。

#### Acceptance Criteria

1. THE Platform SHALL 構築手順・削除手順・注意点を README に記載する。
2. THE Platform SHALL 各主要設計判断の理由を設計文書へ記載する。
3. THE Platform SHALL `docs/{architecture,db,api,operation,security,runbook}` 配下に運用・設計関連ドキュメントを配置する構成で定義する。

---

## スコープ

### 目的

- 社内運用担当者向けの内部運用基盤（Product_A）と、関係者向けの公開・配信ポータル（Product_B）を、AWS リソースで実務想定の構成として設計・構築する。
- 設計力・構築力・運用設計力を示せるポートフォリオ成果物を作る。
- dev 環境で動作する MVP を優先しつつ、商用運用を意識した設計を反映する。

### スコープ（対象）

- Product_A：Backend_API（ECS Fargate）、EKS ワーカー3種（Worker_Alarm / Worker_Finding / Cronjob_Summary）、Aurora_DB、EventBridge→SQS 非同期経路、CloudWatch Logs 集約、VPC/Subnet/SG/ALB、IAM。
- Product_B：CloudFront、S3（OAC）、WAF、Cognito、API Gateway + Lambda、DynamoDB、CloudWatch Logs、IAM。
- MVP の各 API・画面・DB テーブル・イベント経路。
- A→B の一方向連携（月次レポート/公開ステータス）。
- Terraform による IaC（`infra/environments/dev`、`infra/modules/*`）、remote backend（S3 + DynamoDB lock）。
- Bootstrap（ローカル初回のみ）と Infra_Pipeline（CodePipeline+CodeBuild、承認付き）。
- アプリケーションデプロイ（ECS/EKS/CloudFront）のインフラ apply からの分離。
- ドキュメント（`docs/*`）と README（構築・削除手順・注意点）。

### 非スコープ（対象外）

- prod / staging など dev 以外の環境構築。
- Product_B から Product_A への同期呼び出し・双方向連携・書き込み連携。
- 独自ドメイン取得と ACM 証明書適用（MVP では任意、後続 Phase）。
- Aurora Multi-AZ / 自動バックアップ / Performance Insights の本番構成（MVP はコスト優先、設計検討のみ）。
- 本番レベルの高可用性・冗長化・大規模スケーリングの実装。
- 実際の Security Hub / CloudWatch Alarm 連携（MVP はサンプル/ダミーイベント投入）。
- Terraform リソース作成用途での CodeDeploy 利用（CodeDeploy は ECS Blue/Green 候補に限定）。

### 成果物A・成果物Bの分離方針

1. Product_A と Product_B を単一システムへ統合しない（Requirement 1）。
2. Product_A は内部運用・処理基盤として設計する。
3. Product_B は公開・閲覧・配信ポータルとして設計する。
4. 連携は A→B の一方向（月次レポート/公開ステータス）に限定する（Requirement 14）。
5. Terraform module、リポジトリ構成、デプロイ工程も A/B を分離した単位で構成する。

### ユーザー種別

- **Operator（社内運用担当者）**：Product_A の API を利用し、インシデント・Finding・月次集計を管理する。
- **Viewer（関係者/閲覧者）**：Product_B にログインし、障害ステータス・メンテナンス情報・月次レポートを閲覧する。
- **Platform_Engineer（構築・運用担当者）**：Terraform/Bootstrap/Pipeline を用いて Platform を構築・デプロイ・運用する。

### MVP 範囲

- Product_A：ダッシュボード / インシデント一覧・詳細・作成・ステータス更新 / Finding 一覧・詳細 / 月次集計の各 API、EKS ワーカー3種、DBテーブル7種、EventBridge→SQS→Worker→Aurora の非同期経路。
- Product_B：ログイン / 障害ステータス / 障害詳細 / 月次レポート一覧 / レポート詳細の各画面、CloudFront+S3+OAC+WAF+Cognito+API Gateway+Lambda+DynamoDB(4テーブル) 構成。
- スケール（Auto Scaling/HPA）は設計に含めるが MVP では無効/最小/非必須（Requirement 25）。
- Aurora はコスト優先の最小構成、代替案（RDS t4g.micro）を明記（Requirement 24）。

### 将来拡張

- 独自ドメイン + ACM 証明書適用、prod/staging 環境の追加。
- Aurora Multi-AZ / バックアップ / Performance Insights など本番可用性強化。
- Auto Scaling / HPA の有効化と負荷試験に基づくチューニング。
- 実 Security Hub / CloudWatch Alarm / パッチ状況データとの実連携。
- ECS Blue/Green（CodeDeploy）による無停止デプロイ。
- WAF ルールの拡充（検知→ブロック方針の段階的強化）。
- Terraform state のローカルから remote backend への移行完了。
