# Implementation Plan: AWS Incident & Security Operations Platform

## Overview

本実装計画は、requirements.md（Requirement 1〜26）と design.md に基づき、疎結合な2つの成果物（Product_A: ECS/EKS 内部運用基盤、Product_B: CloudFront 配信ポータル）と A→B 一方向連携、IaC（Terraform）、CI/CD、ドキュメントを段階的に構築する。

各タスクは小さく分割し、前タスクの成果物を次タスクが利用する形で積み上げる。純粋ロジック（集計・検証・冪等取込・判定・監査・命名規則）は design.md の Correctness Properties（Property 1〜11）に対応するプロパティベーステスト（PBT、Python Hypothesis、最低100反復）で検証する。AWS マネージドサービスの挙動・インフラ配線は統合テスト／IaC スナップショット／スモークテストで検証する。

実装言語: Backend_API・EKS ワーカー・Lambda は Python、IaC は Terraform、EKS は素の Kubernetes manifest（`kubectl apply`）。

**PBT タグ形式**: `# Feature: aws-incident-security-ops-platform, Property {number}: {property_text}`

---

## Tasks

### Phase 1: リポジトリ・ドキュメント・Terraform 土台

- [x] 1. リポジトリ骨格とドキュメント整備
  - [x] 1.1 リポジトリのディレクトリ骨格を作成する
    - `infra/environments/dev`、`infra/modules`、`apps/`（`apps/backend-api`、`apps/eks-workers`、`apps/portal-frontend`、`apps/portal-lambda`）、`docs/`、`bootstrap/`、`scripts/` の空ディレクトリ構造と各ディレクトリの `.gitkeep`/`README` プレースホルダを作成する
    - _Requirements: 20.2, 22.1_
  - [x] 1.2 `.gitignore` を作成する
    - Terraform ローカル state（`*.tfstate`、`*.tfstate.*`、`.terraform/`）、`*.tfvars.local`、シークレット類（`.env`、`*.pem`、`credentials`）、Python/Node 生成物を除外する
    - _Requirements: 16.3_
  - [x] 1.3 トップレベル README（構築・削除手順・注意点）を作成する
    - Bootstrap→Infra_Pipeline→App_Deploy の順序、削除（撤去）手順、ALB 公開範囲の注意書き（デモ用 public でも許可 CIDR 限定）、dev 環境限定の注意点を記載する
    - _Requirements: 26.1, 15.1, 24.1_
  - [x] 1.4 `docs/` 配下の設計・運用ドキュメントを作成する
    - `docs/architecture.md`、`docs/db.md`、`docs/api.md`、`docs/operation.md`、`docs/security.md`、`docs/runbook.md` を作成し、design.md の該当セクション要約と設計理由を反映する
    - _Requirements: 26.2, 26.3_

- [x] 2. Bootstrap（ローカル初回のみ）Terraform コード作成
  - [x] 2.1 remote state 用 S3 と state lock 定義を作成する
    - `bootstrap/` に remote state 用 S3 バケット（バージョニング/暗号化/public access block）、state lock は `use_lockfile=true`（S3 ネイティブロック）を第一候補として定義し、DynamoDB lock table は代替案として任意（コメント/変数フラグ）で定義する
    - _Requirements: 20.3, 20.4, 21.1_
  - [x] 2.2 CI/CD 土台リソース（CodePipeline/CodeBuild/artifact S3/terraform-exec-role）を作成する
    - `bootstrap/` に CodePipeline、CodeBuild プロジェクト、artifact 用 S3、terraform-exec IAM Role（最小権限）を定義する
    - _Requirements: 21.1, 17.2_
  - [x]* 2.3 Bootstrap の IaC スナップショット/構成テストを作成する
    - `terraform validate` と plan 相当の構成検証で、state 用 S3 の public access block 有効・暗号化、artifact S3、terraform-exec-role の存在を確認する
    - _Requirements: 20.4, 21.1_

- [x] 3. dev 環境 Terraform ルートと共通設定
  - [x] 3.1 `infra/environments/dev` のルート構成と共通変数を作成する
    - `use_lockfile=true` を用いた S3 backend 参照、provider（region=`ap-northeast-1`）、共通変数（project=`ops-platform`、env=`dev`）、共通タグ locals、命名 helper（`ops-platform-dev-<resource>`）を定義する
    - _Requirements: 20.1, 20.2, 20.3, 19.1, 19.2, 19.3, 24.1_
  - [x]* 3.2 命名規則ヘルパーのプロパティテストを作成する（Property 11）
    - **Property 11: リソース命名規則遵守** — 命名 helper が生成する名前が `^ops-platform-dev-.+` に一致することを Hypothesis で検証する（純粋関数として helper を Python 側にも実装、または生成名を検証）
    - `# Feature: aws-incident-security-ops-platform, Property 11: For any Platform が作成するリソース定義について、そのリソース名は命名規則 ops-platform-dev-<resource> のパターン（^ops-platform-dev-.+）に一致しなければならない`
    - **Validates: Requirements 19.1**

- [x] 4. ネットワーク・ECR・Infra_Pipeline 定義
  - [x] 4.1 network module を作成する
    - `infra/modules/network`: VPC(10.0.0.0/16)、public/private-app/isolated-db サブネット（AZ a/c）、IGW、NAT Gateway(single-AZ)、SG(sg-alb/sg-ecs/sg-eks/sg-db 最小許可)、VPC エンドポイント（S3/ECR/Secrets Manager/CloudWatch Logs）を定義する
    - _Requirements: 15.1, 15.2, 15.4, 24.7_
  - [x] 4.2 ecr module を作成する
    - `infra/modules/ecr`: backend-api / eks-workers 用 ECR リポジトリ（命名規則・タグ・イメージスキャン）を定義する
    - _Requirements: 19.1, 19.2, 22.2, 22.3_
  - [x] 4.3 Infra_Pipeline（fmt→validate→plan→承認→apply）を定義する
    - `bootstrap/` または dev ルートに buildspec と CodePipeline ステージ（`terraform fmt`→`validate`→`plan`→手動承認→`apply`）を定義し、plan で作成/変更/削除一覧とコスト影響大リソース（Aurora/NAT/EKS/CloudFront）を明示、承認なしでは apply しない構成にする
    - _Requirements: 21.2, 21.3, 21.4, 21.5, 23.1, 23.2, 23.3_
  - [x]* 4.4 network/ecr/pipeline の IaC スナップショットテストを作成する
    - SG が業務上必要な通信のみ許可、isolated-db が外部通信なし、命名/タグ/region、パイプライン手順順序を plan/構成スナップショットで検証する
    - _Requirements: 15.2, 15.4, 19.1, 19.2, 19.3, 21.3, 23.1_

- [x] 5. Checkpoint — Phase 1 の検証
  - Ensure all tests pass, ask the user if questions arise.

### Phase 2: 成果物A ECS/EKS 内部運用基盤

- [x] 6. Aurora とスキーマ土台
  - [x] 6.1 aurora module と Secrets Manager 連携を作成する
    - `infra/modules/aurora`: Aurora Serverless v2 (PostgreSQL, Writer 1台/Reader なし/最小ACU=0.5/最大ACU=2)、isolated-db subnet 配置、Secrets Manager による DB 認証情報管理（平文禁止）、RDS t4g.micro 代替案をコメントで明記する
    - _Requirements: 8.2, 15.4, 16.1, 16.2, 24.3, 24.4_
  - [x] 6.2 DB スキーマとマイグレーションを作成する
    - 7テーブル（incidents / incident_comments / findings / finding_triage / alarm_events / monthly_summaries / audit_logs）の DDL とマイグレーションスクリプト（external_id UNIQUE NOT NULL、period UNIQUE NOT NULL、FK/ON DELETE CASCADE）を作成する
    - _Requirements: 8.1_
  - [x]* 6.3 スキーマ適用スモークテストを作成する
    - testcontainers(PostgreSQL) にマイグレーション適用後、7テーブルと主要制約（UNIQUE）が存在することを確認する
    - _Requirements: 8.1_

- [x] 7. Backend API（FastAPI）データ層と共通基盤
  - [x] 7.1 Backend API プロジェクト骨格を作成する
    - `apps/backend-api`: `Dockerfile`、`requirements.txt`（FastAPI/SQLAlchemy/psycopg/Hypothesis 等）、`app/` パッケージ、`README.md`、Secrets Manager から DB 認証情報取得する接続層を作成する
    - _Requirements: 16.2, 26.3_
  - [x] 7.2 データアクセス層とリポジトリ関数を実装する
    - incidents/comments/findings/triage/summaries/audit_logs に対する CRUD/集計クエリ関数を実装する（純粋に近い集計・変換ロジックを分離）
    - _Requirements: 8.2_
  - [x] 7.3 認可ミドルウェアと共通エラーハンドラを実装する
    - 認可情報欠落時 401、必須項目欠落時 400（欠落項目提示）、未登録識別子 404、予期例外 500（相関ID）を返す共通機構を実装する
    - _Requirements: 2.3, 3.3, 3.5, 4.3, 5.2_
  - [x]* 7.4 認可欠落 401 のプロパティテストを作成する（Property 2）
    - **Property 2: 認可欠落時 401** — 保護された任意のエンドポイント×認可情報なしリクエストで常に 401 を返すことを検証する
    - `# Feature: aws-incident-security-ops-platform, Property 2: For any 保護された Backend_API エンドポイントおよび有効な認可情報を伴わない任意のリクエストについて、Backend_API は常に HTTP 401 応答を返さなければならない`
    - **Validates: Requirements 2.3**
  - [x]* 7.5 未登録識別子 404 のプロパティテストを作成する（Property 4）
    - **Property 4: 未登録識別子への参照は常に 404** — 存在しない任意の識別子（インシデントID/FindingID/年月）で参照系 API が常に 404 を返すことを testcontainers で検証する
    - `# Feature: aws-incident-security-ops-platform, Property 4: For any Aurora_DB / Portal_DB に存在しない任意の識別子について、当該識別子を指定した参照 API は常に HTTP 404 応答を返さなければならない`
    - **Validates: Requirements 3.3, 4.3, 5.2, 11.3**
  - _Implemented in Task 7: backend-api project skeleton, database layer with 7 models, auth middleware, common error handlers (401/400/404/500), and tests (Property 2/4)._

- [x] 8. Backend API エンドポイント実装
  - [x] 8.1 ダッシュボード集計 API を実装する
    - `GET /dashboard/summary`: incident_count / finding_count / status_breakdown を Aurora から集計して返す
    - _Requirements: 2.1, 2.2_
  - [x]* 8.2 ダッシュボード集計整合性のプロパティテストを作成する（Property 1）
    - **Property 1: ダッシュボード集計整合性** — incident_count/finding_count が件数と一致し、status_breakdown の合計が総件数と一致することを検証する
    - `# Feature: aws-incident-security-ops-platform, Property 1: For any インシデント集合および Finding 集合について、ダッシュボード集計が返す incident_count は件数と一致し、finding_count は件数と一致し、ステータス別集計の各値の合計は総件数と一致しなければならない`
    - **Validates: Requirements 2.1**
  - [x] 8.3 インシデント CRUD API を実装する
    - `GET /incidents`、`GET /incidents/{id}`（詳細＋comments、404）、`POST /incidents`（必須検証、400＋欠落項目）、`PATCH /incidents/{id}/status`（更新＋audit_logs 記録、404）を実装する
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 8.3_
  - [x]* 8.4 作成/更新ラウンドトリップのプロパティテストを作成する（Property 3）
    - **Property 3: 作成/更新ラウンドトリップ** — 有効な入力で作成後、同一IDで取得すると内容が一致することを testcontainers で検証する
    - `# Feature: aws-incident-security-ops-platform, Property 3: For any 必須項目を満たした有効なインシデント入力について、作成後に同一 ID で取得すると、取得結果は作成時に指定した内容と一致しなければならない`
    - **Validates: Requirements 3.4, 8.2**
  - [x]* 8.5 必須項目欠落 400 のプロパティテストを作成する（Property 5）
    - **Property 5: 必須項目欠落は 400＋欠落項目提示** — 必須項目の空でない部分集合を除いた入力で 400 を返し、除いた各項目が欠落項目として含まれることを検証する
    - `# Feature: aws-incident-security-ops-platform, Property 5: For any 有効なインシデント入力から必須項目の空でない部分集合を取り除いた入力について、インシデント作成 API は常に HTTP 400 応答を返し、かつエラー内容には取り除かれた各必須項目が欠落項目として含まれなければならない`
    - **Validates: Requirements 3.5**
  - [x]* 8.6 状態変更の監査記録のプロパティテストを作成する（Property 6）
    - **Property 6: 状態変更は監査ログ記録** — 登録済みインシデント/Finding の任意の有効な状態変更後、audit_logs がちょうど1件増加し変更前後値が記録されることを検証する
    - `# Feature: aws-incident-security-ops-platform, Property 6: For any 登録済みインシデントまたは Finding と、その任意の有効な状態変更について、状態変更操作の後に audit_logs のレコード件数はちょうど 1 件増加し、変更前後の値が記録されなければならない`
    - **Validates: Requirements 3.6, 8.3**
  - [x] 8.7 Finding 参照 API と月次集計 API を実装する
    - `GET /findings`、`GET /findings/{id}`（triage 含む、404）、`GET /summaries/{yyyymm}`（404）を実装し、FastAPI で OpenAPI(Swagger) を自動生成・公開する
    - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.2, 26.2_
  - [x]* 8.8 Backend API の単体テストを作成する
    - 一覧/詳細取得の具体例、空集合・重複ステータスの境界、404/400/401 のエラー条件を検証する
    - _Requirements: 3.1, 3.2, 4.1, 5.1_
  - _Implemented in Task 8: dashboard summary, incidents CRUD (POST/PATCH), findings/summaries reference APIs, with tests for Property 1-6 and business API examples._

- [x] 9. ECS/ALB インフラ定義
  - [x] 9.1 alb module を作成する
    - `infra/modules/alb`: ALB、Target Group、リスナー(HTTP 80 fallback / HTTPS 443)、アクセスログ、許可 CIDR 限定の SG（デモ用 public でも許可 CIDR 限定）を定義する
    - _Requirements: 15.1, 15.3_
  - [x] 9.2 ecs module を作成する
    - `infra/modules/ecs`: cluster、task definition（CPU=256/Mem=512、Secrets Manager 参照）、service（desired_count=1、private subnet）、autoscaling（設計含有・MVP 最小/無効）を定義する
    - _Requirements: 15.3, 16.2, 24.2, 25.1, 25.2_
  - [x]* 9.3 ALB/ECS の IaC スナップショットテストを作成する
    - ALB SG が許可 CIDR 限定、ECS task が Secrets Manager 参照（平文なし）、desired_count=1、命名/タグを検証する
    - _Requirements: 15.3, 16.1, 24.2_
  - _Implemented in Task 9: alb module with HTTP 80 fallback / HTTPS 443 listener, allowed_cidrs restriction, ecs module with FARGATE, task secrets via ARN, and deployment infrastructure._

- [x] 10. EKS 基盤とワーカー実装
  - [x] 10.1 eks module を作成する
    - `infra/modules/eks`: EKS クラスタ、Fargate Profile、namespace=`workers`、IRSA（eks-worker-role / eks-cronjob-role 最小権限）、Fargate 組み込みログルーター用 ConfigMap を定義する
    - _Requirements: 17.1, 17.3, 18.1_
  - [x] 10.2 EKS ワーカーの共通ロジックと Worker_Alarm を実装する
    - `apps/eks-workers`: `Dockerfile`、共通 SQS 受信/削除・DB 接続、`alarm-event-processor`（SQS 取得→alarm_events へ冪等 upsert→メッセージ削除）、k8s manifest、README を作成する
    - _Requirements: 6.2, 6.5, 8.2_
  - [x]* 10.3 アラーム取込冪等性のプロパティテストを作成する（Property 7）
    - **Property 7: アラームイベント取込冪等性** — 同一 external_id を1回/複数回処理してもレコードが同一で件数が増えないことを testcontainers で検証する
    - `# Feature: aws-incident-security-ops-platform, Property 7: For any アラーム風イベントについて、同一イベント（同一 external_id）を 1 回処理した場合と 2 回以上処理した場合とで、alarm_events テーブルの当該レコードは同一であり、レコード件数は増加してはならない`
    - **Validates: Requirements 6.2**
  - [x] 10.4 Worker_Finding を実装する
    - `security-finding-worker`（重大度/リソース種別/対応ステータス判定→findings/finding_triage へ整合登録・冪等）、k8s manifest を作成する
    - _Requirements: 6.3_
  - [x]* 10.5 Finding 判定妥当性と冪等登録のプロパティテストを作成する（Property 8）
    - **Property 8: Finding 判定妥当性と冪等登録** — 判定結果が許容値域内、findings/finding_triage が整合登録され、同一 external_id 再処理で重複しないことを検証する
    - `# Feature: aws-incident-security-ops-platform, Property 8: For any Finding 風イベントについて、Worker_Finding による判定結果（重大度・対応ステータス）は許容される値域に収まり、findings と finding_triage は整合して登録され、かつ同一イベント（同一 external_id）の再処理でレコードが重複してはならない`
    - **Validates: Requirements 6.3**
  - [x] 10.6 Cronjob_Summary の集計ロジックを実装する
    - `monthly-summary-cronjob`（対象期間の incidents/findings/alarm_events 集計→monthly_summaries へ period UNIQUE upsert）、k8s CronJob manifest を作成する（A→B 連携は Phase 3 で追加）
    - _Requirements: 7.1, 7.2_
  - [x]* 10.7 月次集計整合性と再集計冪等性のプロパティテストを作成する（Property 9）
    - **Property 9: 月次集計整合性と再集計冪等性** — 集計値が実件数と一致し、同一年月の再集計後も1行のみ（最新値更新）であることを検証する
    - `# Feature: aws-incident-security-ops-platform, Property 9: For any 対象年月とその期間に属する incidents / findings / alarm_events の集合について、生成する monthly_summaries の各件数は実件数と一致し、かつ同一年月に対する再集計後も 1 行のみでなければならない`
    - **Validates: Requirements 7.1, 7.2**
  - _Implemented in Task 10: eks module with Fargate profiles, IRSA roles, workers namespace; eks-workers project with alarm/finding processors, k8s manifests, and tests for Property 7-9._

- [x] 11. 非同期経路とログ集約インフラ
  - [x] 11.1 sqs/eventbridge module を作成する
    - `infra/modules/messaging`: SQS Standard Queue + DLQ（maxReceiveCount 超過で移動）、EventBridge rule（サンプルイベント投入用）、SQS への配送設定を定義する
    - _Requirements: 6.1, 6.4_
  - [x] 11.2 logging module を作成する
    - `infra/modules/logging`: ECS/EKS/Lambda/ALB/VPC Flow の CloudWatch Logs グループ（保持14〜30日）、EKS Fargate 組み込みログルーター設定を定義する
    - _Requirements: 18.1, 18.2, 18.3_
  - [x]* 11.3 非同期経路の統合テストを作成する
    - EventBridge→SQS→Worker→Aurora を moto 等で1〜3例確認、DLQ 移動・メッセージ削除を代表例で検証する
    - _Requirements: 6.1, 6.4, 6.5_
  - _Implemented in Task 11: messaging module (SQS/DLQ/EventBridge), logging module (Lambda/VPC FlowLogs groups, 14-or-30 day retention), async pipeline integration tests (fake-based pass, moto cases skipped due to moto not installed)._

- [x] 12. Checkpoint — Phase 2 の検証
  - Ensure all tests pass, ask the user if questions arise.
  - _Verified in Task 12: Tasks 6–11 完了確認。全テスト green（bootstrap 27 / dev root 19（Property 11 含む）/ network 6 / ecr 4 / aurora 6 / alb 11 / ecs 8 / eks 13 / messaging 10 / logging 9 / db migrations 8＋1 skip / backend-api 55 / eks-workers 31＋2 skip）。skip は testcontainers(Docker) 1 と moto 未導入 2 のみで実装未完了 skip なし（Property 7/8/9 は fake ベースで pass）。Secret/credential 混入なし（Aurora=RDS 管理シークレット、ECS=ARN 参照のみ）。Product_A/Product_B 分離維持（Phase 3 モジュールは README プレースホルダ、eks-cronjob-role に Portal 書込権限なし、A→B 連携は Phase 3）。dev root は network/ecr/aurora のみ配線、alb/ecs/eks/messaging/logging は依存未確定のため意図的に未配線（各 README に理由明記）。ドキュメント整合（HTTP 80 fallback/HTTPS 443、Fargate 組み込みログルーター DaemonSet 不使用、CloudWatch Logs retention 14/30 離散値、Docker/testcontainers/moto 未実行制約と fake 代替を明記）。Phase 3 進行のブロッカーなし。_

### Phase 3: 成果物B CloudFront 配信ポータル

- [x] 13. Portal_DB とストレージ・配信インフラ
  - [x] 13.1 dynamodb module を作成する
    - `infra/modules/dynamodb`: 4テーブル（public_status_items / report_metadata[GSI gsi_period] / page_view_logs[TTL] / maintenance_windows[TTL]）、全て PAY_PER_REQUEST を定義する
    - _Requirements: 10.1, 11.1, 24.5_
  - [x] 13.2 s3-portal module（OAC 用）を作成する
    - `infra/modules/s3-portal`: public access block 有効、OAC 経由のみ許可するバケットポリシー、`reports/*` プレフィックスを定義する
    - _Requirements: 12.2, 12.3_
  - [x] 13.3 cloudfront/oac/waf module を作成する
    - `infra/modules/cloudfront`: CloudFront(PriceClass_200, S3+API Gateway 2オリジン, HTTPS)、OAC、WAF(Managed Rules 1つ以上＋Rate-based rule)を定義する
    - _Requirements: 12.1, 12.4, 13.1, 13.2, 13.3, 24.6_
  - [x]* 13.4 配信・オリジン保護・WAF の IaC スナップショットテストを作成する
    - S3 public access block 有効、OAC のみ許可のポリシー、CloudFront 2オリジン/PriceClass_200、WAF Managed Rules＋Rate-based rule を検証する
    - _Requirements: 12.2, 12.3, 12.4, 13.1, 13.2, 13.3, 24.6_
  - _Implemented in Task 13: dynamodb module with 4 tables, GSI, TTL; s3-portal module with OAC-only bucket policy, public access block; cloudfront/oac/waf module with 2 origins, PriceClass_200, Managed Rules, Rate-based rule; snapshot tests._

- [x] 14. 認証と Portal API インフラ
  - [x] 14.1 cognito module を作成する
    - `infra/modules/cognito`: User Pool、App Client を定義する
    - _Requirements: 9.1, 9.2_
  - [x] 14.2 apigateway module（Cognito JWT Authorizer）を作成する
    - `infra/modules/apigateway`: `/api/*` ルート、Cognito JWT Authorizer、CloudFront からのルーティングを定義する
    - _Requirements: 9.3, 12.4_
  - [x] 14.3 lambda module を作成する
    - `infra/modules/lambda`: Portal_API Lambda（Python, 256〜512MB, timeout=10s）、lambda-portal-role（DynamoDB 読取＋page_view_logs 書込、Product_A 書込なし）、CloudWatch Logs を定義する
    - _Requirements: 9.3, 14.3, 18.3_
  - _Implemented in Task 14: cognito module (User Pool, public App Client), apigateway module (HTTP API, Cognito JWT Authorizer, /api/* route, aws_lambda_permission), lambda module (256-512MB memory, 10s timeout, portal role with DynamoDB read on 3 tables and write on page_view_logs only, Product_A restricted). 37 passed, 0 skipped.

- [x] 15. Portal_API（Lambda）実装
  - [x] 15.1 Portal_API プロジェクト骨格と共通層を実装する
    - `apps/portal-lambda`: ハンドラ、DynamoDB アクセス層、JWT 検証（欠落/無効時 401）、README を作成する
    - _Requirements: 9.3, 18.3_
  - [x] 15.2 ステータス閲覧 API を実装する
    - `GET /api/status`（一覧）、`GET /api/status/{id}`（詳細）を実装し、閲覧時に page_view_logs へ1件記録、public_status_items 本体は変更しない
    - _Requirements: 10.1, 10.2, 10.3_
  - [x]* 15.3 閲覧記録の副作用不変条件のプロパティテストを作成する（Property 10）
    - **Property 10: 閲覧記録の副作用不変条件** — 閲覧後に page_view_logs がちょうど1件増加し、閲覧対象 public_status_items 本体が変更されないことを moto/DynamoDB Local で検証する
    - `# Feature: aws-incident-security-ops-platform, Property 10: For any 認証済み Viewer による障害ステータス閲覧または障害詳細閲覧について、閲覧操作の後に page_view_logs のレコードはちょうど 1 件増加し、かつ閲覧対象の public_status_items 本体は変更されてはならない`
    - **Validates: Requirements 10.3**
  - [x] 15.4 月次レポート閲覧 API を実装する
    - `GET /api/reports`（一覧）、`GET /api/reports/{id}`（メタ＋レポートファイル参照情報、未登録は 404）を実装する
    - _Requirements: 11.1, 11.2, 11.3_
  - [x]* 15.5 Portal_API の単体テストを作成する
    - JWT 欠落/無効 401、未登録レポート 404、一覧/詳細取得の具体例を moto/DynamoDB Local で検証する
    - _Requirements: 9.3, 10.1, 11.1, 11.3_
  - _Implemented in Task 15: portal-lambda project (handler, config, auth JWT-claims fail-closed 401, DynamoDB access layer with lazy boto3, in-memory fakes), status API (GET /api/status, /api/status/{id}) with exactly-one page_view_logs write and public_status_items immutability, reports API (GET /api/reports, /api/reports/{id}, meta only), Property 10 (Hypothesis 100 examples). 21 passed, 0 skipped._

- [x] 16. Status Portal 静的フロントと A→B 連携
  - [x] 16.1 Status Portal 静的フロントを作成する
    - `apps/portal-frontend/src/public`: ログイン（Cognito）、ステータス一覧、障害詳細、レポート一覧、レポート詳細の各画面と `/api/*` 呼び出しを実装する
    - _Requirements: 9.1, 10.1, 10.2, 11.1, 11.2_
  - [x] 16.2 A→B 連携を Cronjob_Summary に実装する
    - `monthly-summary-cronjob` にレポートファイルの Portal_Storage(`reports/*`) 配置、report_metadata 登録、public_status_items 反映を追加する（実行主体は CronJob に限定、MVP はダミー/非機微のみ）
    - _Requirements: 14.1, 14.2, 14.3_
  - [x]* 16.3 A→B 連携の統合テストを作成する
    - Cronjob_Summary の連携処理を moto/DynamoDB Local で1〜2例確認し、report_metadata/public_status_items 反映と S3 配置、B→A 書込が存在しないことを検証する
    - _Requirements: 14.1, 14.2, 14.3_
  - _Implemented in Task 16: portal-frontend static SPA (login/status-list/status-detail/report-list/report-detail, api.js calling /api/status(/{id}) and /api/reports(/{id}), Cognito config placeholders only); A->B linkage in monthly-summary-cronjob (CronJob-only trigger, write-only ports, reports/<period>/summary.json, report_metadata/public_status_items upsert with deterministic slash-free keys, non-sensitive counts/overview only, no B->A path); fake-based integration tests. eks-workers 42 passed / 3 moto-skipped, portal-frontend 13 passed._

- [x] 17. Checkpoint — Phase 3 の検証
  - Ensure all tests pass, ask the user if questions arise.
  - _Verified in Task 17: Tasks 13–16 完了確認。全テスト green（infra dynamodb/s3-portal/cloudfront 33 / infra cognito/apigateway/lambda 37 / portal-lambda 21（Property 10 Hypothesis 100 examples 含む, 0 skip）/ portal-frontend 13（0 skip）/ eks-workers 42＋3 skip）。skip は moto 未導入の 3 変種のみで実装未完了 skip なし（A→B fake ベース 7 pass、Product_A/B 分離テスト pass、Property 10 skip せず pass）。Product_B 構成静的確認（DynamoDB 4 テーブル＋report_metadata gsi_period＋page_view_logs/maintenance_windows TTL＋全 PAY_PER_REQUEST、S3 Portal public access block 全 true＋OAC 経由のみ許可 bucket policy、CloudFront S3+API Gateway 2 オリジン＋WAF Managed Rules＋Rate-based rule、Cognito User Pool＋App Client generate_secret=false、API Gateway Cognito JWT Authorizer＋ANY /api/{proxy+} Lambda 統合＋aws_lambda_permission、Lambda IAM は Product_B 限定・DynamoDB 読取 3 テーブル＋page_view_logs のみ書込）。Portal_API は 4 エンドポイント実装・fail-closed 401・未登録 404・閲覧ごと page_view_logs ちょうど 1 件・public_status_items 本体不変・boto3 lazy init（import 時 AWS 非接続）。frontend 5 画面＋/api 4 エンドポイント参照、Cognito は REPLACE_WITH_* placeholder のみ（実値・実 Token・実ドメイン・実 API URL 非埋め込み）。A→B 連携は Cronjob_Summary 限定起動・reports/<period>/summary.json・report_metadata/public_status_items 決定的キー upsert（再実行で重複せず上書き）・非機微のみ（record.detail 非伝播）・B→A 書込/参照なし。Secret/credential 混入なし（.venv/.env/tfstate/tfvars.local/pem/credentials は git 管理外、コード・README・テスト・frontend に実値なし。検出は .venv 内の第三者ライブラリ例示データのみ）。dev root は network/ecr/aurora のみ配線、Phase 3 modules（dynamodb/s3-portal/cloudfront/cognito/apigateway/lambda）は依存未確定のため意図的に未配線（各 module README に後続配線依存を明記）。ドキュメント整合（Cognito placeholder 方針、Portal Lambda JWT fail-closed/lazy boto3/Product_B 限定、A→B 非機微一方向/B→A なし、moto 未導入 skip・fake 代替を記載）。Phase 4 進行のブロッカーなし。非ブロッカー TODO: dev root README の Phase 3 未配線言及追記、実配線（dynamodb ARN→lambda / cognito issuer_url・app_client_id→apigateway / lambda invoke ARN・function name→apigateway / apigateway domain→cloudfront / cloudfront distribution ARN→s3-portal policy / s3 regional domain→cloudfront S3 origin / WAF us-east-1 provider alias）は後続 Phase で実施。_

### Phase 4: 運用・セキュリティ・デモ整備

- [x] 18. サンプルデータと監視・監査
  - [x] 18.1 サンプルデータ投入スクリプトを作成する
    - `scripts/`: ダミーのアラーム/Finding イベント投入スクリプト（EventBridge/SQS）、非機微レポート・public_status_items のシードスクリプトを作成する
    - _Requirements: 6.1, 14.1, 14.2_
  - [x] 18.2 monitoring module（CloudWatch Alarm/Dashboard/SNS）を作成する
    - `infra/modules/monitoring`: SQS DLQ>0、ECS(CPU/Mem/タスク数)、ALB(5xx/レイテンシ)、Lambda(Errors/Throttles/Duration)、Aurora(ACU/接続数) の Alarm、A/B 分離2ダッシュボード、SNS 通知を定義する
    - _Requirements: 18.1_
  - [x]* 18.3 監査ログ出力確認と監視構成のテストを作成する
    - 状態変更で audit_logs が出力されること（統合）、DLQ>0 Alarm 等の監視構成が存在することをスナップショット/スモークで確認する
    - _Requirements: 8.3, 18.1_
  - _Implemented in Task 18: seed scripts (alarm/finding EventBridge events, portal reports/status seed) with dry-run/print-only default and --execute gate; monitoring module (11 CloudWatch alarms for SQS DLQ>0/ECS/ALB/Lambda/Aurora, SNS topic wired to alarm_actions, A/B-separated dashboards); audit_logs coverage documented via existing Property 6 tests. monitoring+scripts 36 passed / 0 skipped, audit_logs 26 passed._

- [x] 19. App_Deploy スクリプトと運用ドキュメント
  - [x] 19.1 App_Deploy スクリプト（ECS/EKS/CloudFront）を作成する
    - `scripts/deploy-ecs.sh`（build→ECR push→service update）、`scripts/deploy-eks.sh`（build→ECR push→`kubectl apply`）、`scripts/deploy-frontend.sh`（build→S3 sync→invalidation）を作成する（インフラ apply と分離）
    - _Requirements: 22.1, 22.2, 22.3, 22.4_
  - [x] 19.2 Runbook・デモシナリオ・アーキテクチャ図を作成する
    - `docs/runbook.md` 更新、デモシナリオ（`docs/operation.md` 追記）、アーキテクチャ図（`docs/architecture.md` の mermaid）を整備する
    - _Requirements: 26.1, 26.2, 26.3_
  - [x] 19.3 README を更新する（削除手順含む）
    - 構築手順・削除（撤去）手順・注意点（ALB 公開範囲、コスト影響大リソースの停止）を最終化する
    - _Requirements: 26.1_
  - _Implemented in Task 19: App_Deploy scripts (deploy-ecs.sh, deploy-eks.sh, deploy-frontend.sh) with set -euo pipefail, --help, required-env checks, dry-run/print-only default and --execute gate (App-only, no terraform); runbook (alarm/Finding/DLQ>0/Portal/A->B/rollback/teardown checks); demo scenario (docs/operation) with real seed/deploy commands; architecture mermaid (A->B one-way with B->A excluded, Infra_Pipeline vs App_Deploy separation, monitoring/SNS); top-level README (build order, teardown steps, cost/security notes, dev root unwired module table). 50 passed, 0 skipped._

- [ ] 20. 最終 Checkpoint — 全体の検証
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- `*` 付きサブタスクは任意（テスト系: 単体/プロパティ/統合/IaC スナップショット/スモーク）で、MVP 短縮時にスキップ可能。コア実装タスクには `*` を付けない。
- 各タスクは対応 Requirement を `_Requirements: X.Y_` で明記し、トレーサビリティを確保する。
- PBT（Property 1〜11）は design.md の Correctness Properties を参照し、Python Hypothesis で各プロパティ単一テスト・最低100反復・タグ付与で実装する。DB 依存は testcontainers(PostgreSQL) / moto / DynamoDB Local で分離する。
- AWS マネージドサービス挙動・インフラ配線（EventBridge→SQS 配送/DLQ/Cognito/CloudFront/OAC/WAF/IAM/ネットワーク）は PBT 対象外とし、統合テスト・IaC スナップショット・スモークテストで検証する。
- 各 Checkpoint で段階的に検証し、次 Phase の成果物が前 Phase を利用する形で積み上げる。
- 実際の terraform apply / デプロイ実行 / 手動承認 / AWS コンソール操作は本計画のコーディング対象外（スクリプト・manifest・IaC コードの作成のみを含む）。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "id": 1, "tasks": ["2.1", "2.2", "3.1"] },
    { "id": 2, "tasks": ["2.3", "3.2", "4.1", "4.2"] },
    { "id": 3, "tasks": ["4.3", "6.1", "6.2"] },
    { "id": 4, "tasks": ["4.4", "6.3", "7.1", "13.1", "13.2"] },
    { "id": 5, "tasks": ["7.2", "7.3", "13.3", "14.1"] },
    { "id": 6, "tasks": ["7.4", "7.5", "8.1", "8.3", "8.7", "13.4", "14.2", "14.3"] },
    { "id": 7, "tasks": ["8.2", "8.4", "8.5", "8.6", "8.8", "9.1", "9.2", "10.1", "15.1"] },
    { "id": 8, "tasks": ["9.3", "10.2", "10.4", "10.6", "11.1", "11.2", "15.2", "15.4"] },
    { "id": 9, "tasks": ["10.3", "10.5", "10.7", "11.3", "15.3", "15.5", "16.1"] },
    { "id": 10, "tasks": ["16.2", "18.1", "18.2"] },
    { "id": 11, "tasks": ["16.3", "18.3", "19.1", "19.2", "19.3"] }
  ]
}
```
