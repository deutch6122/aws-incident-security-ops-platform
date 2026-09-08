# Implementation Plan: dev-full-stack-wiring

## Overview

本計画は Feature「dev-full-stack-wiring」を、requirements.md（Requirement 1〜33 + Traceability + Verification Classification）と承認済み design.md に基づき、実装可能な単位へ分解したものである。目的は dev Terraform ルート（`infra/environments/dev`）を 17 モジュール（network / ecr / aurora / alb / ecs / eks / messaging / logging / dynamodb / s3-portal / cloudfront / cognito / apigateway / lambda / monitoring / iam / waf）で完全配線し、阻害要因 B-001〜B-034（P0=24 / P1=9 / P2=1）を静的・mock 検証レベルで解消することにある。

**阻害要因 Priority（原本「05_阻害要因」シート確定値・唯一の正）**: P0 = B-001〜B-024（24 件）、P1 = B-025〜B-033（9 件）、P2 = B-034（1 件）。本計画・requirements.md・design.md はこの原本値に統一する。

**本フェーズは設計・実装（IaC / アプリ / スクリプト）・テスト・ドキュメントのリポジトリ内修正に限定する。** 実 AWS 操作（`terraform apply` / AWS CLI / kubectl / docker build・push / deploy script `--execute`）は一切行わない。Category C の項目は手順とチェック内容のみ記述し、Operator 承認後の保留検証として扱う。

**依存順の厳守（循環回避）**:
- Bearer Secret / ECR / Aurora → iam → ecs
- iam と ecs → dev root の migration-launcher policy（root で両 output を参照）
- DynamoDB / S3 Portal 基盤 / Messaging / Aurora → eks
- Cognito / Lambda → API Gateway → CloudFront
- Portal S3 基盤 → CloudFront → dev root bucket policy
- WAF（us-east-1）→ CloudFront
- 各基盤 output 確定後 → Monitoring
- iam↔ecs 循環は log group ARN の文字列組み立てで回避、s3-portal↔cloudfront は root bucket policy で回避、iam↔ecs migration-launcher は root policy（ecs output 参照）で回避

**Lambda package** は versioned S3 object 方式（`lambda_package_s3_bucket` / `lambda_package_s3_key` / `lambda_package_s3_object_version` / `lambda_source_code_hash`）に固定し、ローカル filename 方式へ戻さない。

**実リポジトリパス（確定）**: bootstrap は `bootstrap/`（`bootstrap/iam.tf` / `bootstrap/cicd.tf` / `bootstrap/buildspec/*.yml`）。EKS マニフェストは `apps/eks-workers/k8s/*.yaml`。ルート `k8s/` や `infra/bootstrap/` は作成・参照しない。

各 Task には「実装目的 / 新規作成ファイル / 変更が必要な既存ファイル / 実装内容 / 先行 Task / Requirement・AC / 阻害要因 / Verification Category / 完了条件 / ローカル・CI テスト / Category C 保留検証 / rollback」を記載する。

## Current Progress（2026-09-06）

- トップレベル Task: **35 / 35 完了**。
- 必須チェック項目: **40 / 40 完了**（任意の Task 11.1* は集計対象外）。
- 完了済み: Task 1〜35（任意の11.1を除く）、9.1、9.2、16.1、21.1、24.1。
- 次の依存順: リポジトリ内実装は完了。Operator承認後に `docs/operation/aws-build-procedure.md` 付録AのCategory Cを順番に実施する。
- 実AWS操作・`terraform plan/apply`・Docker・kubectl・deploy `--execute` は未実施。完了チェックはローカル静的検証・単体テスト・`terraform validate` の範囲を示す。

## Tasks

- [x] 1. Spec 整合と共通 Terraform バージョン定義の作成
  - **実装目的**: 全 stage（ローカル / CI / CodeBuild）が単一 source of truth から同一 Terraform バージョンを導入できるようにする（Req 24）。以降 Task の前提となる共通基盤。
  - **新規作成ファイル**: `.terraform-version`（値 `1.13.3`）、`.terraform-version.checksums`（arch 別 SHA256 pin: `linux/amd64` / `darwin/arm64` を最低限記録する非機微ファイル）。
  - **変更が必要な既存ファイル**: なし（本 Task では既存ファイルを変更しない。CI / buildspec への配線は Task 29 / 30 で行う）。
  - **実装内容**: `.terraform-version` に単一パッチバージョン `1.13.3` を記載。公式 `SHA256SUMS`（1.13.3）から arch 別 SHA256 を取得し `.terraform-version.checksums` に `arch→SHA256` 形式で記録。値は複数の buildspec / workflow に重複記載しない方針を README コメントで明記。
  - **先行 Task**: なし。
  - _Requirements: 24.1, 24.2_
  - **阻害要因**: B-020。
  - **Verification Category**: A。
  - **完了条件**: 両ファイルが存在し、`.terraform-version` が `1.13.3`、checksums が 2 arch 以上を含む。
  - **ローカル/CI テスト**: ファイル存在と内容の unit/静的検証（バージョン文字列一致、checksums の arch キー存在）。
  - **Category C 保留検証**: なし。
  - **rollback**: 追加した 2 ファイルを削除する。

- [x] 2. ECR を 5 リポジトリ化（migration リポジトリ追加）
  - **実装目的**: Backend_API + worker 3 種 + migration の計 5 リポジトリを維持し、ワークロードごとに一意イメージを参照可能にする（Req 8）。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `infra/modules/ecr/variables.tf`（`repository_components` の `length == 4` 固定 validation を 5 コンポーネント許容へ変更。許容集合 `backend-api` / `alarm-event-processor` / `security-finding-worker` / `monthly-summary-cronjob` / `db-migration`）、必要な範囲で `infra/modules/ecr/main.tf` / `outputs.tf`（リポジトリ出力に `db-migration` を含める）。
  - **実装内容**: validation を 5 コンポーネント許容へ変更し、`db-migration` リポジトリを追加。各リポジトリ ARN / URL を output。
  - **先行 Task**: なし。
  - _Requirements: 8.1, 8.5_
  - **阻害要因**: B-009。
  - **Verification Category**: A。
  - **完了条件**: `terraform validate`（ecr module）が 5 コンポーネントで成功、`db-migration` 出力が存在。
  - **ローカル/CI テスト**: `terraform fmt` / `init -backend=false` / `validate`（ecr module）、5 リポジトリ一意性の contract/unit test。
  - **Category C 保留検証**: 実 ECR への push / image-pull（Req 8.4）。
  - **rollback**: validation を 4 固定へ戻し `db-migration` 出力を削除。

- [x] 3. Backend 内部 Bearer Secret を dev root に作成
  - **実装目的**: `BACKEND_INTERNAL_BEARER_TOKEN` を Terraform 生成・Secrets Manager 保管し、ARN を iam / ecs へ渡す単一所有点を dev root に確立する（Req 4）。iam↔ecs 循環を避けるため module 外に置く。
  - **新規作成ファイル**: なし（dev root 内に定義）。
  - **変更が必要な既存ファイル**: `infra/environments/dev/main.tf`（`random_password.backend_bearer` length>=32、`aws_secretsmanager_secret.backend_bearer`、`aws_secretsmanager_secret_version.backend_bearer`）、`infra/environments/dev/variables.tf`（`backend_bearer_secret_recovery_window_days`）、`infra/environments/dev/versions.tf`（`random_password` を使用するため `required_providers` に HashiCorp Random provider `hashicorp/random ~> 3.6` を追加）。
  - **実装内容**: `random_password`(length>=32) → `aws_secretsmanager_secret`(`recovery_window_in_days = var...`) → `secret_version` に実値格納。値は output しない。ARN は Task 4（iam）/ Task 10（ecs）が入力で受ける。
  - **先行 Task**: なし（dev root の骨格は Task 27 で完成するが、本リソースは独立して定義可能）。
  - _Requirements: 4.1, 4.2, 27.2, 27.3_
  - **阻害要因**: B-005, B-033。
  - **Verification Category**: A。
  - **完了条件**: Secret 実値が output / log / plaintext env / repo に出ない。`validate` 成功。
  - **ローカル/CI テスト**: secret hygiene 静的テスト（output に secret 値なし）、`terraform validate`（dev root、本リソース単体で解決可能な範囲）。
  - **Category C 保留検証**: 実 apply による Secret 作成。
  - **rollback**: 3 リソースと変数を除去。

- [x] 4. IAM module に 5 ロールを実装
  - **実装目的**: Product_A の ECS 系 5 ロール（Backend ECS task execution / Backend ECS task / migration execution / migration task / migration-launcher role 本体+trust のみ）を最小権限で新規実装する（Req 2）。
  - **新規作成ファイル**: `infra/modules/iam/main.tf`、`infra/modules/iam/variables.tf`、`infra/modules/iam/outputs.tf`、`infra/modules/iam/wildcard-exceptions.md`、`infra/modules/iam/wildcard_exceptions.json`。
  - **変更が必要な既存ファイル**: `infra/modules/iam/README.md`（実装反映）。
  - **実装内容**: 5ロールを決定的名称 `${name_prefix}-ecs-task-execution-role` / `${name_prefix}-ecs-task-role` / `${name_prefix}-migration-execution-role` / `${name_prefix}-migration-task-role` / `${name_prefix}-migration-launcher-role` で定義する。Backend execution role に ECR pull / Logs / Bearer secret GetSecretValue、Backend task role にDB secret GetSecretValue、migration execution roleにECR pull/awslogs、migration task roleにDB secret GetSecretValueのみを付与する。migration-launcher roleはrole本体+trust policyのみ（RunTask policyはTask 27でroot attach）。log group ARNはpartition/account/region/name prefixから組み立て、ecs outputに依存しない。Wildcard_ExceptionをRegistryへ記録する。
  - **先行 Task**: 2（ECR ARN）, 3（Bearer ARN）。Aurora ARN は既存配線済み module 出力。
  - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 2.7_
  - **阻害要因**: B-002, B-032。
  - **Verification Category**: A。
  - **完了条件**: 5 ロールが定義され、Resource_Level_Action に `*` なし（Wildcard_Exception を除く）、log group ARN が partition 変数を使用、`validate` 成功。
  - **ローカル/CI テスト**: `terraform fmt` / `init -backend=false` / `validate`（iam module）。IAM policy static test は Task 34 で集約。
  - **Category C 保留検証**: なし。
  - **rollback**: iam module の新規ファイルを削除し README を元へ戻す。

- [x] 5. bootstrap terraform-exec-role に PassRole を追加
  - **実装目的**: task definition 登録時に bootstrap の terraform-exec-role が本 Feature の 4 role へ PassRole できるようにする（Req 2.6, 2.8）。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `bootstrap/iam.tf`（terraform-exec-role の policy を持つファイル）。
  - **実装内容**: terraform-exec-roleのpolicyに`iam:PassRole`を追加する。対象4 ARNは`data.aws_partition.current.partition`、`data.aws_caller_identity.current.account_id`、共有`name_prefix`と、`${name_prefix}-ecs-task-execution-role` / `${name_prefix}-ecs-task-role` / `${name_prefix}-migration-execution-role` / `${name_prefix}-migration-task-role`から`bootstrap/iam.tf`内で組み立てる。`Condition: iam:PassedToService = ecs-tasks.amazonaws.com`を必須とし、Dev_Rootのstate/output/data lookupには依存しない。CodeBuild roleにmigration起動用PassRoleは付与しない。
  - **先行 Task**: 4（4 role ARN 確定）。
  - _Requirements: 2.6, 2.8, 2.10_
  - **阻害要因**: B-002, B-032。
  - **Verification Category**: A。
  - **完了条件**: PassRole allowlist が 4 ARN のみ、`PassedToService` condition 付き、bootstrap がDev_Root stateを参照せず、`validate` 成功。
  - **ローカル/CI テスト**: `terraform validate`（bootstrap）、PassRole allowlist static test、bootstrapの4 role名とiam moduleの4 role名が完全一致するcontract test、dev state非参照test（Task 34 集約）。
  - **Category C 保留検証**: 実 pipeline での register-task-definition。
  - **rollback**: 追加した PassRole statement を除去。

- [x] 6. Network module に Security Group を単一所有で追加配線
  - **実装目的**: ALB→ECS(`var.app_port`=8080)、migration→DB(5432)、DB←migration、および migration→必要 AWS サービス(HTTPS 443、NAT または VPC endpoint) の private 到達性を network module 単一所有で確立する（Req 19.3, 5.1）。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `infra/modules/network/main.tf`（SG 本体と SG rule の単一所有者。既存 alb/ecs/eks/db SG に加えて migration SG を定義。ALB→ECS(`var.app_port`)、migration→DB(5432)、DB←migration、NAT 経路の migration→`external_https_egress_cidrs` HTTPS 443、VPC endpoint 経路の migration→endpoint SG HTTPS 443 と endpoint SG←migration HTTPS 443（`enable_vpc_endpoints` 条件付き、既存 ECS/EKS と同一パターン）の rule を管理）、`infra/modules/network/outputs.tf`（migration SG ID を `security_group_ids.migration` として追加）、`infra/modules/network/tests/test_network_snapshot.py`（後述の検証を追加）。dev root 配線は Task 27 で行う。
  - **実装内容**: SG とルールは network module が単一所有。migration SG は inbound なし・public 経路なし。application 通信は DB 向け 5432、タスク起動・Secret 取得・ログ出力に必要な AWS サービス通信は HTTPS 443 に限定し、NAT 経路（`external_https_egress_cidrs`）と VPC endpoint 経路（ECR API/DKR・Secrets Manager・CloudWatch Logs の interface endpoint、ECR layer 取得は既存 S3 gateway endpoint）のどちらでも成立させる。本 Task は network module 内だけを変更し、ALB/ECS/migration への root 配線と ALB 側 SG 二重作成の無効化は Task 27 で行う。
  - **先行 Task**: なし（network は配線済み。SG は module 間で参照）。
  - _Requirements: 19.3, 5.1_
  - **阻害要因**: B-026, B-006。
  - **Verification Category**: A。
  - **完了条件**: migration SG は inbound なし・public ingress なし。application 通信は DB 向け 5432 に限定し、タスク起動・Secret 取得・ログ出力に必要な AWS サービス通信は HTTPS 443 に限定して NAT・VPC endpoint のどちらでも成立する。ALB→ECS は `var.app_port`（既定 8080）。migration SG ID が output され、network module 単体の `validate` が成功する。
  - **ローカル/CI テスト**: `terraform validate`、network migration SG static test（inbound なし / DB 5432 のみ / NAT 443 egress / endpoint 443 egress・ingress / output / app_port 8080 / 0.0.0.0/0 ingress なし）、network boundary static test（Task 34 集約）。
  - **Category C 保留検証**: 実 traffic 到達性（DB 5432 と AWS サービス 443 の疎通）。
  - **rollback**: 追加 SG / rule を除去し alb SG 作成を元へ戻す。

- [x] 7. ALB アクセスログと TLS リダイレクト
  - **実装目的**: ALB を TLS 終端（HTTPS:443, ACM 必須）、HTTP:80 を 301/302 redirect、access-logs bucket + delivery policy を整える（Req 18, 19, 16）。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `infra/modules/alb/*.tf`（HTTPS listener + ACM入力、80→443 redirect action、access logging入力、target groupはHTTP:8080維持、外部SGを受け取るinterface）、`infra/modules/alb/variables.tf` / `outputs.tf`。dev rootの証明書変数、access-log bucket/policy、network SG配線はTask 27で行う。
  - **実装内容**: HTTP listener を forward から redirect(HTTPS) へ変更し、443 listenerに入力されたACM証明書をbindする。access-log bucket名/prefixを入力として受け、外部SG利用時にSGを自作しないmodule interfaceを完成させる。本Taskはalb module内だけを変更する。
  - **先行 Task**: 6（SG）。
  - _Requirements: 18.2, 19.1, 19.2, 19.3_
  - **阻害要因**: B-018, B-026。
  - **Verification Category**: A。
  - **完了条件**: ACM ARN入力が必須、redirect action設定済み、access logging入力と外部SG interfaceが定義され、alb module単体の`validate`成功。
  - **ローカル/CI テスト**: `terraform validate`、listener redirect/access-logging/external-SG interfaceのstatic test。
  - **Category C 保留検証**: 実 HTTP→HTTPS redirect（Req 19.2）、実 access-logging plan 出力（Req 18.2）。
  - **rollback**: alb moduleのlistener/access-logging/external-SG interface変更をrevert。

- [x] 8. Messaging を 2 系統（alarm / finding）に分離
  - **実装目的**: alarm 系統と finding 系統をそれぞれ独立の rule + queue + DLQ（maxReceiveCount=5）で定義し、相互混在を排除する（Req 6）。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `infra/modules/messaging/*.tf`（系統ごとに `aws_cloudwatch_event_rule` + `aws_sqs_queue` + DLQ、`redrive_policy.maxReceiveCount = 5`、detail-type で event pattern 限定）、`infra/modules/messaging/variables.tf` / `outputs.tf`（`alarm_event_detail_types` / `finding_event_detail_types` / `sqs_max_receive_count`(既定5)、queue url/arn 出力）。
  - **実装内容**: EventBridge target で alarm→alarm queue、finding→finding queue に限定。DLQ を系統ごとに分離。queue url/arn を系統別に output。
  - **先行 Task**: なし。
  - _Requirements: 6.1, 6.2, 6.7_
  - **阻害要因**: B-007。
  - **Verification Category**: A（config）/ B（routing via mock/LocalStack）。
  - **完了条件**: 2 系統が独立、maxReceiveCount=5、`validate` 成功。
  - **ローカル/CI テスト**: `terraform validate`、event-pattern static test、queue/DLQ config test（Task 34）。
  - **Category C 保留検証**: 実 EventBridge/SQS routing（Req 6.3, 6.4）、実 max-receive 挙動（Req 6.7）。
  - **rollback**: 単一系統構成へ戻す。

- [x] 9. Backend DB Secret / dbname フォールバック / Bearer 認証
  - **実装目的**: Backend_API に `BACKEND_DB_NAME` フォールバックと Bearer 認証依存を実装する（Req 3, 4.4, 4.5）。
  - **新規作成ファイル**: `apps/backend-api/tests/` 配下の unit / property test（dbname フォールバック、bearer 認証）。
  - **変更が必要な既存ファイル**: `apps/backend-api/app/config.py`（`db_name: str | None`（`BACKEND_DB_NAME`）追加）、`apps/backend-api/app/db/secrets.py`（`dbname` を optional 解析する経路追加、双方欠落で値非露出の設定エラー）、`apps/backend-api/app/db/session.py`（resolver で `settings.db_name` 採用）、FastAPI bearer 認証依存関数（既存 `internal_bearer_token: SecretStr` を用いた `Authorization: Bearer` 検証、失敗は 401 + `WWW-Authenticate: Bearer`）。
  - **実装内容**: 解決順 `secret.dbname`(非空) → `BACKEND_DB_NAME` → 起動失敗（値非露出）。bearer 完全一致で成功、欠落/非 Bearer/不一致は 401。
  - **先行 Task**: なし（アプリ層、独立）。
  - _Requirements: 3.4, 3.5, 3.6, 4.4, 4.5_
  - **阻害要因**: B-003, B-004, B-005。
  - **Verification Category**: A。
  - **完了条件**: RDS 管理形ペイロード（dbname 省略）で解決名 = `BACKEND_DB_NAME`、bearer 失敗が 401 + header。
  - **ローカル/CI テスト**: dbname フォールバック property test（Task 9.1）、bearer 認証 unit test（Task 9.2）。
  - **Category C 保留検証**: なし。
  - **rollback**: config.py / secrets.py / session.py の変更と認証依存を revert。

- [x] 9.1 Backend dbname フォールバック property test を実装
  - **Property 1: dbname フォールバック解決**
  - **Validates: Requirements 3.4, 3.5, 3.6**
  - Hypothesis で RDS 管理形ペイロードと `BACKEND_DB_NAME` の組を生成し解決名を assert。タグコメント `Feature: dev-full-stack-wiring, Property 1`。max_examples>=100。
  - _Requirements: 3.4, 3.5, 3.6_

- [x] 9.2 Backend Bearer 認証 unit test を実装
  - 完全一致成功 / 欠落 / 非 Bearer / 不一致（401 + `WWW-Authenticate: Bearer`）を検証。
  - _Requirements: 4.4, 4.5_

- [x] 10. ECS Backend task / service 配線
  - **実装目的**: Backend task definition に DB Secret ARN(plaintext env) と Bearer(secrets 注入) を設定し、`ecs_desired_count=0` を許容、log group を持つ（Req 3, 4, 29.1）。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `infra/modules/ecs/*.tf`（task definition の `environment` に `BACKEND_DB_SECRET_ARN`(ARN 文字列のみ)、`secrets` に Bearer(Secrets Manager 参照)、`aws_cloudwatch_log_group.this`、execution/task role を iam 出力で受ける、`desired_count = var.ecs_desired_count`、SG は network module から受け取る）、`infra/modules/ecs/variables.tf`（`ecs_desired_count`(既定0) / `ecs_task_cpu` / `ecs_task_memory` / `backend_db_name` / role ARN / bearer secret ARN / SG ID）、`infra/modules/ecs/outputs.tf`（cluster_name / service_name）。
  - **実装内容**: DB secret は plaintext env に ARN のみ（取得はアプリ=task role）。Bearer は `secrets` 注入（取得は execution role）。log group name を output しない（iam は文字列組み立て）。
  - **先行 Task**: 3（Bearer ARN）, 4（role ARN）, 6（network SG）, 7（ALB target）。
  - _Requirements: 3.1, 3.2, 3.3, 4.3, 29.1_
  - **阻害要因**: B-003, B-005。
  - **Verification Category**: A。
  - **完了条件**: DB secret plaintext 平文が env/output に出ない、Bearer は secrets 注入、`desired_count=0` 可、`validate` 成功。
  - **ローカル/CI テスト**: `terraform validate`、secret hygiene static test（Task 34）。
  - **Category C 保留検証**: 実 task 起動。
  - **rollback**: task definition の env/secrets 変更と変数/出力を revert。

- [x] 11. migration image / runner / task definition
  - **実装目的**: private-app subnet 内の専用 ECS one-off task で DB migration を実行できる構成を作る（Req 5）。
  - **新規作成ファイル**: `apps/db-migration/Dockerfile`（migration 専用。**build context をリポジトリルート**とし `docker build -f apps/db-migration/Dockerfile .` でルートの `db/migrations` を COPY する）、`apps/db-migration/run_migration.py`（psycopg runner、`db/migrations/*.sql` 実行）、schema 存在テスト（**Docker 非依存**: `db/migrations/*.sql` の静的解析、または in-memory / file-based fixture で 7 業務テーブルと制約を assert、管理/システムテーブル除外）。
  - **変更が必要な既存ファイル**: `infra/modules/ecs/*.tf`（migration task definition を Backend とは別に定義、migration execution role + migration task role を両設定、`migration_cluster_arn` / `migration_task_definition_arn` を output、migration 用 log group）、`infra/modules/ecs/variables.tf`（migration role ARN 入力）。
  - **実装内容**: migration 専用 Dockerfile + psycopg runner が `db/migrations/0001_init_schema.sql` を実行。build context はリポジトリルート固定（`db/migrations` を COPY するため）。task に `BACKEND_DB_SECRET_ARN`(plaintext env) を渡し dbname 欠落時は `BACKEND_DB_NAME`。awslogs 権限は execution role 側。Backend runtime image に migration SQL を含めない。
  - **先行 Task**: 2（db-migration リポジトリ）, 4（migration roles）, 10（ecs 骨格）。
  - _Requirements: 5.1, 5.3, 5.4, 5.5_
  - **阻害要因**: B-006, B-009。
  - **Verification Category**: A（Docker 非依存 schema test）/ C（実 Aurora migration・testcontainers 版）。
  - **完了条件**: migration task definition が両 role を持ち、`migration_cluster_arn` / `migration_task_definition_arn` を output、Docker 非依存 schema test が 7 テーブル + 制約を検証（総数 7 を要求しない）、Dockerfile build context がルート。
  - **ローカル/CI テスト**: schema 存在 unit test（SQL 静的解析 or Docker 不要 fixture、Category A）、`terraform validate`。testcontainers 版 schema test は Category C（任意 `*`、Task 11.1）。
  - **Category C 保留検証**: 実 Aurora への migration 実行（Req 5.3, 5.5）、testcontainers による実 PostgreSQL schema 検証。
  - **rollback**: migration task definition / Dockerfile / runner / output を除去。

- [ ] 11.1* migration testcontainers schema test を実装（任意）
  - testcontainers で実 PostgreSQL を起動し migration SQL 適用後に 7 業務テーブルと制約を検証する任意の追加検証。Docker が必要なため Category C 相当。未導入時 skip は Category A の Definition of Done に影響しない。
  - _Requirements: 5.3, 5.4_

- [x] 12. migration dry-run 起動スクリプト
  - **実装目的**: Operator がmigration-launcher-roleを利用してmigration one-off taskを安全に単発起動できるスクリプトを整備する（Req 5, 30）。root policyはTask 27で実装する。
  - **新規作成ファイル**: `scripts/deploy-migration.sh`（新規作成に固定。既定 dry-run では AWS CLI を実行しない。`--execute` 時のみ Fargate 起動）。
  - **変更が必要な既存ファイル**: なし。dev rootの`aws_iam_role_policy.migration_launcher`はTask 27で実装する。
  - **実装内容**: `scripts/deploy-migration.sh` は `require_env` で必須値チェックし、terraformを呼ばない。`--execute`時のFargate起動に以下を必須化: migration cluster/task definition、private-app subnet IDs、migration専用SG ID、`assignPublicIp=DISABLED`、`--launch-type FARGATE`、migration-launcher-roleのAssumeRole、`aws ecs wait tasks-stopped`、container exitCodeが0であることの確認。非0/停止理由異常/タイムアウト時はスクリプトも非0終了。root policyの権限契約と必須環境変数はstatic/snapshot testで固定する。
  - **先行 Task**: 4（launcher role）, 6（migration SG / subnet）, 11（ecs migration output）。
  - _Requirements: 5.1, 30.1, 30.2, 30.3_
  - **阻害要因**: B-006。
  - **Verification Category**: A。
  - **完了条件**: `scripts/deploy-migration.sh`が既定dry-runでAWS CLIを実行せず、`--execute`時に上記必須項目を満たす。
  - **ローカル/CI テスト**: shell syntax(`bash -n`) + dry-run snapshot test、必須環境変数と実行コマンドのstatic test。
  - **Category C 保留検証**: 実 run-task 起動（Req 5.3）。
  - **rollback**: scriptを除去。

- [x] 13. EKS IRSA 3 系統（worker 2 分割 + cronjob）
  - **実装目的**: 単一 worker role を alarm/finding に 2 分割し、cronjob を含む 3 IRSA を最小権限で整える（Req 6.5, 2.4, 10.2）。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `infra/modules/eks/*.tf`（`var.sqs_queue_arns`(list) を廃止し `var.alarm_queue_arn` / `var.finding_queue_arn` へ分割、`eks-alarm-worker-role` / `eks-finding-worker-role` / `eks-cronjob-role` の IRSA を ServiceAccount 単位で整理、各 worker/cronjob role に DB secret GetSecretValue(DB ARN のみ)、cronjob role に Portal S3 `reports/*` PutObject + report_metadata/public_status_items PutItem）、`infra/modules/eks/variables.tf`（queue arn 分割、`eks_kubernetes_version`(既定1.36) / `eks_public_access_cidrs`(必須, 0.0.0.0/0 禁止 validation) / `eks_operator_principal_arn` / DynamoDB table ARN / Portal bucket ARN）。
  - **実装内容**: 各 worker role は自系統 queue ARN のみ許可。cronjob role は A→B 唯一の書込主体。access entry は Task 27 の dev root で作成。
  - **先行 Task**: 8（queue arn）, 17（DynamoDB ARN）, 21（Portal S3 基盤の bucket ARN）, Aurora（DB secret ARN, 配線済み）。
  - _Requirements: 2.4, 6.5, 10.2, 20.1, 20.5_
  - **阻害要因**: B-007, B-010, B-023, B-025。
  - **Verification Category**: A。
  - **完了条件**: alarm/finding role が自系統 queue のみ、cronjob が指定 2 テーブル + reports/* のみ、`eks_public_access_cidrs` に 0.0.0.0/0 拒否 validation、`validate` 成功。
  - **ローカル/CI テスト**: `terraform validate`、IAM policy static test（scope, Task 34）、CIDR validation static test。
  - **Category C 保留検証**: `kubectl auth can-i`（Req 20.4）、EKS Running（Req 8.4）。
  - **rollback**: 単一 worker role 構成へ戻し変数を revert。

- [x] 14. EKS Fargate logging を既存 manifest で構成
  - **実装目的**: Fargate 組み込みログルーターで Pod stdout/stderr を CloudWatch Logs へ転送する（可観測性、既存 eks module 実態に整合）。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `apps/eks-workers/k8s/00-namespace.yaml`（`aws-observability` namespace）、`apps/eks-workers/k8s/40-fargate-logging.yaml`（`aws-logging` ConfigMap、`output=cloudwatch_logs`、出力先は既存 `aws_cloudwatch_log_group.workers`）。ルート `k8s/` の新規ファイルは作らない。
  - **実装内容**: `aws-observability` namespace と `aws-logging` ConfigMap を既存 manifest 上で構成。適用順は worker ワークロードより先（Task 15 / 32 の適用順に明記）。
  - **先行 Task**: 13（eks IRSA）。
  - _Requirements: 20.1_
  - **阻害要因**: B-023。
  - **Verification Category**: A（manifest 静的）/ C（実適用）。
  - **完了条件**: 2 manifest が存在し placeholder なし（レンダリング後検査対象）。
  - **ローカル/CI テスト**: manifest 構文 / placeholder-absence unit test（Task 34）。
  - **Category C 保留検証**: 実 kubectl apply とログ転送確認。
  - **rollback**: 該当 manifest 変更を revert。

- [x] 15. EKS manifest レンダリングと Placeholder 検査
  - **実装目的**: `deploy-eks.sh` を envsubst レンダリング + placeholder 検査へ拡張し、3 リポジトリ・workload 別 image を参照する（Req 7, 8.2, 8.3, 9.1）。
  - **新規作成ファイル**: なし（既存 `apps/eks-workers/k8s/*.yaml` の placeholder 入りを利用）。
  - **変更が必要な既存ファイル**: `scripts/deploy-eks.sh`（単一 `ECR_REPO` 参照を 3 リポジトリ参照へ、envsubst で一時 manifest 生成、生成後 `${...}` / `REPLACE_WITH_*` 走査、残存で非ゼロ終了、`--execute` 時のみ apply、terraform を呼ばない、docker build は `--platform linux/amd64`）、`apps/eks-workers/k8s/20-alarm-event-processor.yaml` / `21-security-finding-worker.yaml` / `30-monthly-summary-cronjob.yaml`（workload 別 image 参照、2 workload が同一リポジトリを参照しない）。
  - **実装内容**: レンダリング → placeholder 検査 → (execute 時のみ)apply。適用順に `apps/eks-workers/k8s/00-namespace.yaml`（aws-observability）+ `40-fargate-logging.yaml`（aws-logging ConfigMap）を先行。
  - **先行 Task**: 2（3 リポジトリ）, 14（logging manifest）。
  - _Requirements: 7.1, 7.2, 7.3, 8.2, 8.3, 9.1, 30.1, 30.3_
  - **阻害要因**: B-008, B-009, B-028。
  - **Verification Category**: A。
  - **完了条件**: placeholder 残存で非ゼロ終了、3 リポジトリ参照、workload 別 image、docker build に `--platform linux/amd64`。
  - **ローカル/CI テスト**: placeholder-absence unit test、distinct workload image contract/unit test、shell syntax + dry-run snapshot（Task 34）。
  - **Category C 保留検証**: 実 apply / workload Running（Req 8.4）、image architecture inspect（Req 9.2）。
  - **rollback**: deploy-eks.sh を単一リポジトリ版へ revert。

- [x] 16. Product A→B 連携（Cronjob_Summary）
  - **実装目的**: Cronjob_Summary manifest に 3 portal env を定義し、決定的キー + upsert で冪等・失敗報告する（Req 10）。
  - **新規作成ファイル**: A→B 決定的キー導出のアプリ実装（`apps/eks-workers/workers` 内の Cronjob_Summary エントリ）と対応する property/unit test。
  - **変更が必要な既存ファイル**: `apps/eks-workers/k8s/30-monthly-summary-cronjob.yaml`（reports bucket / report_metadata table / public_status_items table の 3 env）、`apps/eks-workers/workers/*`（決定的 S3 key `reports/<YYYYMM>.json` と DynamoDB item key 導出、upsert `PutItem`、いずれか失敗で run 失敗報告）。
  - **実装内容**: 同一期間 → 同一キー、異なる期間 → 異なるキー。リトライ時 upsert で 1 オブジェクト / 各 1 item に収束。3 出力のいずれか失敗で失敗報告。
  - **先行 Task**: 13（cronjob IRSA）, 17（DynamoDB）, 21（Portal S3 基盤）。
  - _Requirements: 10.1, 10.3, 10.4, 10.6_
  - **阻害要因**: B-010。
  - **Verification Category**: A（key 導出/失敗報告）/ B（収束）/ C（実 S3/DynamoDB）。
  - **完了条件**: 3 env 定義、決定的キー導出、失敗時 run 失敗報告。
  - **ローカル/CI テスト**: A→B 決定的キー property test（Task 16.1）、失敗報告 unit test。
  - **Category C 保留検証**: 実 S3/DynamoDB write 収束（Req 10.4）。
  - **rollback**: cronjob manifest env と導出/報告ロジックを revert。

- [x] 16.1 A→B 決定的キー導出 property test を実装
  - **Property 2: A→B 連携の決定的キー導出**
  - **Validates: Requirements 10.3, 10.4**
  - Hypothesis で対象期間を生成し、同一期間→同一キー / 異なる期間→異なるキーを assert。タグコメント `Feature: dev-full-stack-wiring, Property 2`。max_examples>=100。
  - _Requirements: 10.3, 10.4_

- [x] 17. DynamoDB 4 テーブル配線
  - **実装目的**: Portal_DB の 4 テーブルを配線し、cronjob / lambda へ table ARN を供給する（Req 10.2 の前提）。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `infra/modules/dynamodb/*.tf`（`public_status_items` / `report_metadata` / `page_view_logs` / `maintenance_windows` の 4 テーブル、table ARN/name 出力）、`infra/modules/dynamodb/variables.tf` / `outputs.tf`。
  - **実装内容**: 4 テーブル定義、`report_metadata_table_name` / `public_status_items_table_name` 等を output（cronjob manifest / lambda / frontend config 用）。
  - **先行 Task**: なし。
  - _Requirements: 10.1, 10.2_
  - **阻害要因**: B-010。
  - **Verification Category**: A。
  - **完了条件**: 4 テーブルが定義され table ARN/name を出力、`validate` 成功。
  - **ローカル/CI テスト**: `terraform validate`、contract test（output→input, Task 34）。
  - **Category C 保留検証**: 実 apply。
  - **rollback**: dynamodb module 変更を revert。

- [x] 18. Lambda 再現 ZIP と versioned S3 package
  - **実装目的**: 決定的 zip を生成し、lambda module へ versioned S3 object 参照を渡す（Req 11）。ローカル filename 方式へ戻さない。
  - **新規作成ファイル**: `apps/portal-lambda/build.sh`（固定 mtime / ソート順 / 固定 permission で決定的 zip 生成。`apps/portal-lambda/requirements.txt` の依存ライブラリ（バージョン固定）と `apps/portal-lambda/app/` を正しい Lambda ディレクトリ構造で同梱し `apps/portal-lambda/dist/portal-api.zip` を生成）、再現ハッシュ unit test（2 回生成し hash 一致）。
  - **変更が必要な既存ファイル**: `infra/modules/lambda/variables.tf`（`package_s3_object_version` / `source_code_hash` 入力変数を追加）、`infra/modules/lambda/main.tf`（`aws_lambda_function` の `s3_object_version` / `source_code_hash` へ配線）。
  - **実装内容**: `build.sh` が依存バージョン固定・固定 mtime/順序/permission で決定的 zip を生成。lambda module へ `lambda_package_s3_bucket` / `lambda_package_s3_key`(`lambda/<commit-sha>/portal-api.zip`) / `lambda_package_s3_object_version` / `lambda_source_code_hash`。ローカルパスは渡さない。artifact bucket への実 upload は Category C。
  - **先行 Task**: なし（lambda module interface 変更は独立）。
  - _Requirements: 11.1, 11.2, 11.3_
  - **阻害要因**: B-011。
  - **Verification Category**: A（hash 一致 / S3 参照 wiring）/ C（実 package upload）。
  - **完了条件**: lambda module が `package_s3_object_version` / `source_code_hash` を受ける、`apps/portal-lambda/build.sh` が依存バージョン固定で同一ソース 2 回生成 hash 一致。
  - **ローカル/CI テスト**: reproducible-hash unit test（2 回生成一致、100 回不要）、S3 参照 wiring contract/static test、`terraform validate`。
  - **Category C 保留検証**: 実 artifact bucket upload（Req 11.1）、invoke smoke（Req 11.4）。
  - **rollback**: lambda module の 2 入力変数と `build.sh` を revert。

- [x] 19. Cognito code + PKCE 設定
  - **実装目的**: public client（generate_secret=false）で authorization code + PKCE を有効化、implicit 無効、domain / callback / logout を設定する（Req 12）。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `infra/modules/cognito/*.tf`（User Pool domain、app client `generate_secret=false`、code grant + PKCE 有効 / implicit 無効、callback URL 1 以上 / logout URL 1 以上、issuer URL + app client id を非空 output）、`infra/modules/cognito/variables.tf`（`cognito_callback_urls`(非空 validation) / `cognito_logout_urls`(非空) / `cognito_keep_localhost_urls`(既定 false)）。
  - **実装内容**: 初回は `http://localhost:5173/callback` / `http://localhost:5173/`（placeholder ではない実 URL）。CloudFront 確定後 HTTPS へ置換（Task 32 手順）。空リストで plan/apply validation エラー。
  - **先行 Task**: なし。
  - _Requirements: 12.1, 12.2, 12.3, 12.4_
  - **阻害要因**: B-012。
  - **Verification Category**: A。
  - **完了条件**: code+PKCE 有効 / implicit 無効、callback/logout 空で validation エラー、issuer/app client id 非空出力。
  - **ローカル/CI テスト**: cognito flows test（code+PKCE 有効 / implicit 無効）、`terraform validate`、callback/logout validation test。
  - **Category C 保留検証**: 実 sign-in（Req 13.7）。
  - **rollback**: cognito module 変更を revert。

- [x] 20. API Gateway（$default + /api/{proxy+} + JWT authorizer）
  - **実装目的**: `$default` stage と `/api/{proxy+}` route、Cognito JWT authorizer を配線する（Req 14.1）。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `infra/modules/apigateway/*.tf`（`$default` stage、route `/api/{proxy+}`、Cognito issuer/app client id を用いた JWT authorizer、api domain を output）、`infra/modules/apigateway/variables.tf`（cognito issuer / app client id 入力）。
  - **実装内容**: Lambda を統合先に、JWT authorizer で 200/401 判定（実 HTTP は C）。
  - **先行 Task**: 18（lambda）, 19（cognito）。
  - _Requirements: 14.1_
  - **阻害要因**: B-014。
  - **Verification Category**: A（config）/ C（実 HTTP）。
  - **完了条件**: `$default` + `/api/{proxy+}` + JWT authorizer、`validate` 成功。
  - **ローカル/CI テスト**: API Gateway route/stage static test、`terraform validate`。
  - **Category C 保留検証**: 実 /api HTTP 200/401（Req 14.3, 14.4）。
  - **rollback**: apigateway module 変更を revert。

- [x] 21. Portal S3 基盤（bucket / 命名 / 暗号化 / versioning）
  - **実装目的**: Portal_Storage の S3 基盤を確立し、cronjob IRSA / CloudFront が参照する bucket 出力を提供する（Req 15.1, 16.1）。循環回避のため policy は付けない。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `infra/modules/s3-portal/*.tf`（bucket 本体 + public access block + SSE 暗号化 + versioning、bucket policy は Task 27 の dev root で作成（本モジュール内では未作成）、名称に account id/region suffix・63 字以内、`bucket_name` / `bucket_regional_domain_name` / `bucket_arn` を output）、`infra/modules/s3-portal/variables.tf` / `outputs.tf`。
  - **実装内容**: s3-portal を policy なしで確定（本モジュールに bucket policy / `cloudfront_distribution_arn` を持たない。OAC bucket policy は Task 27 の dev root が所有）。bucket 名式は `local`（stem 切り詰め）+ `data.aws_caller_identity` + `var.aws_region`（suffix `<account-id>-<region>`）。cronjob IRSA（Task 13）は本 bucket ARN のみに依存し CloudFront 完了を待たない。
  - **先行 Task**: なし。
  - _Requirements: 15.1, 16.1, 16.3_
  - **阻害要因**: B-015, B-016。
  - **Verification Category**: A。
  - **完了条件**: bucket / SSE / public access block / versioning が定義、policy 未作成、bucket 名 63 字以内、`validate` 成功。
  - **ローカル/CI テスト**: `terraform validate`、bucket naming property test（Task 21.1）。
  - **Category C 保留検証**: 実 plan bucket 一意性（Req 16.4）。
  - **rollback**: s3-portal 変更を revert。

- [x] 21.1 バケット命名 property test を実装
  - **Property 4: バケット命名の一意性と長さ**
  - **Validates: Requirements 16.1, 16.2, 16.3**
  - Hypothesis で account id / region を生成し、Portal / ALB access-logs 名が suffix を含み相異なり 63 字以内であることを assert。タグコメント `Feature: dev-full-stack-wiring, Property 4`。max_examples>=100。
  - _Requirements: 16.1, 16.2, 16.3_

- [x] 22. CloudFront module統合（OAC / behavior分離）
  - **実装目的**: distributionを作成し`/api/*` behaviorを分離するCloudFront moduleを完成させる（Req 14.2）。root bucket policyはTask 27で実装する。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `infra/modules/cloudfront/*.tf`（default behavior=S3 OAC、`/api/*` behavior=API originパス保持 / `CachingDisabled` / `AllViewerExceptHostHeader` / `redirect-to-https` / メソッド全セット、WAF ARN入力、`distribution_arn`をoutput）、`infra/modules/cloudfront/variables.tf` / `outputs.tf`。dev rootのmodule block、price class変数、`aws_s3_bucket_policy.portal_oac`はTask 27で実装する。
  - **実装内容**: S3 regional domain、API domain、WAF ARNを入力として受けるcloudfront moduleを完成させる。bucket policyはmodule内で作らず、Task 27のroot glueへ委ねる。本Taskはcloudfront module単体でvalidate可能にする。
  - **先行 Task**: 20（apigateway origin）, 21（Portal S3 基盤）, 23（WAF web_acl_arn）。
  - _Requirements: 14.2, 15.2_
  - **阻害要因**: B-014, B-015。
  - **Verification Category**: A。
  - **完了条件**: `/api/*` behavior分離、必要な3 origin/security入力、distribution ARN出力があり、cloudfront module単体の`validate`成功。
  - **ローカル/CI テスト**: CloudFront path preserve/interface static test、`terraform validate`。
  - **Category C 保留検証**: 実 CloudFront HTTP 応答（Req 14.3, 14.4）。
  - **rollback**: cloudfront module変更をrevert。

- [x] 23. WAF module（us-east-1 / logging / KMS / redaction）
  - **実装目的**: CLOUDFRONT スコープの Web ACL を us-east-1 で新規作成し、logging / KMS / redaction を構成する（Req 17）。
  - **新規作成ファイル**: `infra/modules/waf/main.tf`、`infra/modules/waf/variables.tf`、`infra/modules/waf/outputs.tf`。
  - **変更が必要な既存ファイル**: `infra/modules/waf/README.md`（実装反映）。
  - **実装内容**: `aws_wafv2_web_acl`(scope=CLOUDFRONT)、`AWSManagedRulesCommonRuleSet`常時 + `waf_additional_managed_rule_groups`(既定空)、visibility_config metrics/sampled有効。loggingは`waf_logging_enabled`(既定true)条件付き`aws_wafv2_web_acl_logging_configuration` + log group(名`aws-waf-logs-`開始、`waf_log_retention_days`)。KMSは`waf_logging_enabled && waf_kms_enabled`(既定true)条件付き。`redacted_fields`に`Authorization`/`Cookie`。`web_acl_arn`をoutput。子moduleのresourceは`aws.us_east_1` aliasを直接参照せず、Task 27のmodule provider mappingで注入される標準`aws` providerを使用する。
  - **先行 Task**: なし（provider aliasはTask 27でdev rootに定義し、module provider mappingで子の標準`aws`へ注入する）。
  - _Requirements: 17.1_
  - **阻害要因**: B-017。
  - **Verification Category**: A（wiring）/ C（実 plan 出力）。
  - **完了条件**: scope=CLOUDFRONT、log group名`aws-waf-logs-`開始、redacted_fields設定、子module内alias参照なし、`validate`成功。
  - **ローカル/CI テスト**: `terraform fmt` / `init -backend=false` / `validate`（waf module）、provider-alias wiring static test。
  - **Category C 保留検証**: 実 plan の us-east-1 Web ACL 作成（Req 17.2）。
  - **rollback**: waf module 新規ファイルを削除し README を戻す。

- [x] 24. Frontend OAuth フローと config 生成
  - **実装目的**: code+PKCE+state 検証、token 保存方式、logout 削除、`deploy-frontend.sh` の config.js 生成 + placeholder 検査を実装する（Req 13）。
  - **新規作成ファイル**: OAuth state 検証の純関数と対応 property test、frontend 認証フロー unit test。
  - **変更が必要な既存ファイル**: Portal_Frontend のソース（callback で code+PKCE 完了、送出/返却 `state` 一致検証、不一致はトークン保存せずエラー、access token in-memory + `state`/PKCE verifier は sessionStorage、expiry 失効管理、logout で削除 + Cognito logout URL redirect）、`scripts/deploy-frontend.sh`（Terraform 出力から一時 `config.js` 生成、placeholder 走査、残存で非ゼロ終了・非公開、`--execute` 時のみ sync、docker build を伴う場合は `--platform linux/amd64`）。
  - **実装内容**: state 純関数（等しい時のみ code 交換へ進む）を分離し PBT 対象化。
  - **先行 Task**: 19（cognito）, 22（cloudfront 出力）。
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 30.1, 30.3_
  - **阻害要因**: B-013, B-027。
  - **Verification Category**: A。
  - **完了条件**: state 不一致でトークン非保存 + エラー、placeholder 残存で非ゼロ終了・非公開。
  - **ローカル/CI テスト**: OAuth state property test（Task 24.1）、frontend 認証 unit test、placeholder-absence unit test、shell syntax + dry-run snapshot（Task 34）。
  - **Category C 保留検証**: 実 4 API sign-in（Req 13.7）。
  - **rollback**: frontend 認証変更と deploy-frontend.sh を revert。

- [x] 24.1 OAuth state 検証 property test を実装
  - **Property 3: OAuth `state` 検証**
  - **Validates: Requirements 13.1, 13.2**
  - Hypothesis で送出/返却 state の組を生成し、一致時のみ成功・不一致は拒否かつトークン非保存を assert。タグコメント `Feature: dev-full-stack-wiring, Property 3`。max_examples>=100。
  - _Requirements: 13.1, 13.2_

- [x] 25. Monitoring 配線と SNS 通知
  - **実装目的**: monitoring を全 output で配線し、2 DLQ alarm と変数化 SNS subscription を構成する（Req 22）。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `infra/modules/monitoring/*.tf`（ecs / eks / alb / lambda / aurora / messaging 出力入力、alarm/finding 2 DLQ alarm、SNS subscription を `monitoring_enable_sns_subscription`(変数) 制御、endpoint は SSM Parameter Store 参照で解決、実値を tfvars/README/output に書かない）、`infra/modules/monitoring/variables.tf`（`monitoring_enable_sns_subscription` / `monitoring_notification_endpoint`(SSM 参照)）。
  - **実装内容**: 2 DLQ それぞれに alarm。未確認 subscription でも apply を失敗させない。
  - **先行 Task**: 7（alb）, 8（messaging）, 10（ecs）, 13（eks）, 18（lambda）, Aurora（配線済み）。
  - _Requirements: 22.1, 22.2, 22.3_
  - **阻害要因**: B-030。
  - **Verification Category**: A。
  - **完了条件**: 全 output 配線、2 DLQ alarm、endpoint 実値が repo/output に出ない、`validate` 成功。
  - **ローカル/CI テスト**: `terraform validate`、secret hygiene static test（endpoint 実値非混入, Task 34）、contract test。
  - **Category C 保留検証**: 実 alarm-state / notification / email 確認（Req 22.4）。
  - **rollback**: monitoring module 変更を revert。

- [x] 26. VPC Flow Logs
  - **実装目的**: logging module に `aws_flow_log` と IAM role を追加する（Req 21）。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `infra/modules/logging/*.tf`（`aws_flow_log` + 関連 IAM role + log group）、`infra/modules/logging/variables.tf`（retention 等）。
  - **実装内容**: Flow Log を log group へ記録する構成。
  - **先行 Task**: network（配線済み）。
  - _Requirements: 21.1_
  - **阻害要因**: B-029。
  - **Verification Category**: A（wiring）/ C（実 log-stream）。
  - **完了条件**: `aws_flow_log` + IAM role + log group が定義、`validate` 成功。
  - **ローカル/CI テスト**: `terraform validate`、flow-log resource wiring static test。
  - **Category C 保留検証**: 実 flow-log entries（Req 21.2）。
  - **rollback**: logging module 変更を revert。

- [x] 27. dev root 全 module 配線
  - **実装目的**: 未配線12 + iam/wafを配線し、root glue resourceを単一Taskで実装して、各module単体実装を循環のない完全なdev rootへ統合する（Req 1, 2.8, 15, 16, 17, 18, 20.3）。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `infra/environments/dev/main.tf`（全module block、root glue、EKS access entry）、`infra/environments/dev/providers.tf`（`aws.us_east_1` aliasとWAF provider mapping）、`infra/environments/dev/variables.tf`（全module入力、ALB ACM ARN、ALB access-log bucket設定、CloudFront price class等）、`infra/environments/dev/outputs.tf`（外部利用の非機微値のみ）。
  - **実装内容**: 以下を本Taskで一括実装する。
    - alb / ecs / eks / messaging / logging / dynamodb / s3-portal / cloudfront / cognito / apigateway / lambda / monitoring / iam / waf のmodule blockとoutput/input接続。
    - network moduleのALB/ECS/migration SG IDを各利用箇所へ配線し、alb moduleのSG自作を無効化。
    - dev root所有のBackend Bearer Secretをiam/ecsへ接続。
    - `aws_iam_role_policy.migration_launcher`: migration task definition/cluster限定RunTask、DescribeTasksの必要最小権限、migration execution/task role 2 ARNだけのPassRoleと`PassedToService`条件。
    - ALB access-log bucket、暗号化/public access block/log-delivery policy、account id/regionを含む63文字以内の一意名、alb module入力。
    - `aws_s3_bucket_policy.portal_oac`: `module.cloudfront.distribution_arn`をSourceArnとしてs3-portal bucketへ後付け。
    - `providers = { aws = aws.us_east_1 }`でWAFへaliasを標準`aws`として注入。子moduleはaliasを直接参照しない。
    - `aws_eks_access_entry`とpolicy association。
    - 依存グラフをoutput参照 + 最小`depends_on`で確立。iam↔ecs、s3-portal↔cloudfront、migration-launcherの循環を作らない。
  - **先行 Task**: 3〜26（各 module 実装完了）。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.8, 15.1, 15.2, 16.2, 16.3, 17.1, 18.1, 20.3_
  - **阻害要因**: B-001, B-002, B-015, B-016, B-017, B-018, B-024, B-032。
  - **Verification Category**: A。
  - **完了条件**: 17 module配線、root glue所有一覧の全項目実装、未宣言入力ゼロ、outputsは外部利用非機微値のみ、cache有りで`init -backend=false` + `validate`がzero exit。
  - **ローカル/CI テスト**: `terraform fmt` / `init -backend=false` / `validate`（dev root）、module output-input contract、bootstrap/dev role-name contract、migration-launcher policy、ALB log bucket policy、WAF provider mapping、S3/CloudFront acyclicityのstatic test（Task 34集約）。
  - **Category C 保留検証**: `kubectl auth can-i`（Req 20.4）、実 plan。
  - **rollback**: 追加module block、root glue resource、provider alias/mapping、変数、出力をrevert。

- [x] 28. Terraform backend / lock / provider 供給
  - **実装目的**: partial backend.tf と lock file をコミットし、local state フォールバックを禁止する（Req 23, 25.2）。
  - **新規作成ファイル**: `infra/environments/dev/backend.tf`（partial、Sensitive_Value なし）、`infra/environments/dev/.terraform.lock.hcl`（dev 構成の provider lock）。
  - **変更が必要な既存ファイル**: `infra/environments/dev/backend.tf.example`（partial 化の説明整合を更新する）。
  - **実装内容**: state bucket 名は静的値化せず `-backend-config` / CodeBuild 環境変数で供給（Task 29）。local state フォールバック禁止。lock file を commit。
  - **先行 Task**: 27（dev root 配線）。
  - _Requirements: 23.1, 23.2, 25.2_
  - **阻害要因**: B-019, B-021。
  - **Verification Category**: A。
  - **完了条件**: partial backend.tf に Sensitive_Value なし、lock file が tracked、backend.tf.example が partial 化に整合更新済み。
  - **ローカル/CI テスト**: backend 設定 static test、secret hygiene（backend.tf に機微値なし, Task 34）。
  - **Category C 保留検証**: 実 plan/apply の state bucket 使用（Req 23.3）。
  - **rollback**: backend.tf / lock file を除去し backend.tf.example を戻す。

- [x] 29. CodePipeline / CodeBuild plan artifact と Lambda package 供給
  - **実装目的**: buildspec で `.terraform-version` + checksum install、stage 別 artifact、binary plan 保護、`TF_VAR_*`/SSM/Secrets Manager 供給、Lambda package の versioned S3 供給を整える（Req 24, 25, 26, 11）。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `bootstrap/buildspec/*.yml`（`buildspec-plan.yml` 等: Terraform を `.terraform-version`(1.13.3) + arch 別 checksum で install、`terraform version` echo を置換、`tfplan.binary` + `plan-summary.txt` を stage-scoped artifact 化、`.terraform.lock.hcl` を artifact に含める、SSM/Secrets Manager から取得値を一時 `TF_VAR_*` に設定、ignored tfvars を artifact 転記しない、一時 tfvars は破棄）、`bootstrap/cicd.tf`（artifact bucket / binary plan bucket 定義: SSE-KMS 必須・アクセス制限・lifecycle expiration、versioning 有効 artifact bucket）。
  - **実装内容**: Lambda package 供給を明記: Bootstrap 完了後の versioning 有効 artifact bucket を使用、`lambda/<commit-sha>/portal-api.zip` へアップロード、object version ID と SHA256 を取得、plan へ bucket/key/version/hash を入力、apply では承認済み plan と同一の version/hash を確認。apply stage は S3 object 参照(bucket/key/version/hash)一致確認 / lockfile 一致 / `terraform init -lockfile=readonly` / 同一 version・provider apply（承認済み binary plan のみ）。実 upload / pipeline 実行は Category C（本 Feature 中は実行しない）。本 Task は実装コードと buildspec の静的検証だけを行う。
  - **先行 Task**: 1（.terraform-version）, 18（lambda S3 参照）, 28（backend/lock）。
  - _Requirements: 24.1, 25.1, 26.1, 26.2, 11.1, 11.2_
  - **阻害要因**: B-020, B-021, B-022, B-011。
  - **Verification Category**: A（buildspec 静的）/ C（実 pipeline 実行 / 実 upload）。
  - **完了条件**: buildspec が単一バージョン install、stage 別 artifact、binary plan / artifact bucket が SSE-KMS/制限/lifecycle、Lambda package 供給処理が静的に整合。
  - **ローカル/CI テスト**: buildspec static check、artifact 構成静的検証、Lambda S3 供給 wiring static test。
  - **Category C 保留検証**: 実 pipeline 実行（Req 24.2, 25.1, 25.3, 26.3）、実 Lambda package upload（Req 11.1）。
  - **rollback**: buildspec / bucket 定義を revert。

- [x] 30. GitHub Actions で Terraform 静的検証
  - **実装目的**: dev root と各 module に fmt / init -backend=false / validate ジョブを追加する（Req 28）。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `.github/workflows/ci.yml`（terraform 静的検証ジョブ追加: root + 各 module の fmt / `init -backend=false` / validate、Terraform は `.terraform-version` + arch 別 checksum で install、provider cache hit 時再利用 / miss 時ネットワーク取得許容、AWS credentials なし、backend 無効、plan/apply なし）。
  - **実装内容**: 既存 suite 別ジョブ構成に terraform 静的検証ジョブと property/unit テストジョブを追加。実 AWS 操作なし。
  - **先行 Task**: 1（.terraform-version）, 27（dev root）。
  - _Requirements: 28.1, 28.2, 28.3_
  - **阻害要因**: B-031。
  - **Verification Category**: A。
  - **完了条件**: CI が fmt/init/validate を実行、credentials なし、plan/apply なし。
  - **ローカル/CI テスト**: workflow 静的検証（ジョブ定義存在）、CI 実行（PR）。
  - **Category C 保留検証**: なし。
  - **rollback**: 追加ジョブを ci.yml から除去。

- [x] 31. Parameter Sheet を新規作成
  - **実装目的**: 阻害要因・パラメータ・供給元・コスト要因・必須事前入力を記載する成果物を新規作成する（Req 26.1, 22.3, 19.1）。
  - **新規作成ファイル**: `docs/operation/aws-resource-parameter-sheet.xlsx`。
  - **変更が必要な既存ファイル**: なし。
  - **実装内容**: workbookには次の9 worksheetを固定で作成する: `00_使い方・前提`、`01_AWSリソース一覧`、`02_Terraform入力値`、`03_ファイル編集マップ`、`04_Terraform出力・取得値`、`05_Deploy環境変数`、`06_コスト・保持期間`、`07_Category-C検証`、`08_destroy前確認`。各構成パラメータ行には、AWSサービス/リソース、Terraform module、resource/data block、variable/output名、対象ファイル、設定箇所、型、必須/任意、既定値、推奨dev値、環境固有値への置換要否、値の取得元、SSM/Secrets Manager供給方法、機微情報区分、未設定時の影響、コスト影響、apply後の確認方法、関連Build Procedure手順番号を記載する。コスト要因と必須事前入力も同じ台帳で追跡し、実ARN/実アカウントID/実ドメイン/実メール/実Secretは記載しない。
  - **先行 Task**: 3〜29（module/dev root/backend/pipeline/deploy scriptの入力・出力・供給経路確定）。
  - _Requirements: 26.1, 26.4, 26.5, 22.3, 19.1_
  - **阻害要因**: B-022, B-030, B-026。
  - **Verification Category**: A。
  - **完了条件**: 9 worksheetと必須列が揃い、全パラメータの供給元・対象ファイル・関連手順が1対1、Sensitive_Value非記載。
  - **ローカル/CI テスト**: workbook構造/必須列test、variable/output/file path/手順番号のdocs-consistency test、secret hygiene（Task 34）。
  - **Category C 保留検証**: なし。
  - **rollback**: xlsx を削除。

- [x] 32. AWS Build Procedure を新規作成
  - **実装目的**: 空アカウント起点の完全構築順序（Two_Phase_Build + bootstrap + Category C 手順 + destroy）を Operator が逐次実行できる形で記載する（Req 29, 20.2, 5.2, 1.8, 22.4）。
  - **新規作成ファイル**: `docs/operation/aws-build-procedure.md`。
  - **変更が必要な既存ファイル**: Correction Gateとして bootstrap/variables.tf / bootstrap/cicd.tf / bootstrap/buildspec/buildspec-plan.yml / bootstrap/buildspec/buildspec.yml / 対応するbootstrap静的テスト（Two Phase、Cognito、MonitoringのSSM入力経路）、infra/environments/dev/outputs.tf（Frontend用Cognito User Pool ID）、docs/operation/aws-resource-parameter-sheet.xlsx（追加入力と手順番号の同期）。既存の無関係な変更には触れない。
  - **実装内容**: 以下を順番に記載（コマンド記載可、実行しない）:
    1. 前提条件、認証、リージョン、予算・コスト警告。
    2. ACM 証明書、DNS、CodeStar Connection 等の事前入力。
    3. Parameter Sheet 完成。
    4. Bootstrap init/plan/ユーザー承認/apply。
    5. Bootstrap outputs と SSM 等の Pipeline 入力設定。
    6. Lambda ZIP 生成（`apps/portal-lambda/build.sh`）・artifact bucket versioned upload。
    7. 本体 plan・承認・初回 apply（ECS desired_count=0）。
    8. 5 イメージ build/push（`--platform linux/amd64`。migration image は build context をリポジトリルートとし `docker build -f apps/db-migration/Dockerfile .`）。
    9. migration 実行（`scripts/deploy-migration.sh --execute`、VPC 内 one-off Fargate task）と exitCode 確認（`aws ecs wait tasks-stopped` / `describe-tasks` lastStatus=STOPPED / exitCode=0）。
    10. desired_count=1 の再 plan・承認・apply。
    11. EKS ログ設定（`apps/eks-workers/k8s/00-namespace.yaml` → `40-fargate-logging.yaml`）、workload 配信。
    12. CloudFront 確定後の Cognito callback / logout URL を HTTPS へ更新（再 plan・承認・apply）。
    13. frontend 配信、sample data、monitoring 確認。
    14. Category C 検証、失敗時停止条件、ロールバック、コスト停止・destroy 手順。
    - EKS version は apply 直前に Standard Support 再確認、外なら停止更新、extended support 前提にしない。SNS email 確認は C、未確認でも apply 失敗しない旨。validate がネットワーク/認証で非ゼロなら失敗理由と未検証範囲を記録（Req 1.8）。
    - 各ファイル編集操作には対象ファイル、block/key、placeholder例、正となる値の取得元、編集完了条件を記載する。
    - 各コマンド操作には手順番号、目的、実行ディレクトリ、前提条件、正確なコマンド、dry-run/plan確認方法、成功時の期待結果、失敗時停止条件、確認ログ/出力、rollback方法、次へ進める条件を記載する。
    - Parameter Sheetの関連手順番号から本書へ一意に到達でき、Bootstrapからdestroyまで未記載の手作業を残さない。
    - **Correction Gate（実装済み）**: Pipeline planがSSMから application_image_tag / ecs_desired_count / Cognito callback・logout・localhost flag / Monitoring subscription・endpoint parameter name・protocolを取得し、初回0台→migration→最終1台、HTTPS URL更新、任意SNS通知をすべて承認付きPipelineで実行できる経路を追加。Frontendの必須入力 cognito_user_pool_id をdev rootの非機微outputへ追加し、Parameter Sheetへ同期した。
  - **先行 Task**: 11（migration）, 13（EKS version）, 18（Lambda）, 19（Cognito）, 27（dev root）, 29（pipeline）, 31（Parameter Sheet）。
  - _Requirements: 5.2, 20.2, 29.2, 29.3, 29.4, 29.5, 29.6, 29.7, 1.8, 22.4_
  - **阻害要因**: B-006, B-023, B-030, B-001。
  - **Verification Category**: A。
  - **完了条件**: 空アカウント起点の14ブロックが順序付きで、全編集・コマンド操作が必須項目を持ち、Parameter Sheetとの相互参照が完成し、未記載操作がない。
  - **ローカル/CI テスト**: 必須章/操作項目/相互参照のdocs-consistency test。
  - **Category C 保留検証**: 記載された全 C 手順の実行。
  - **rollback**: md を削除。

- [x] 33. README / 既存ドキュメント整合
  - **実装目的**: Backend README を router 実装済みへ更新し、ドキュメント整合を確保する（Req 31）。
  - **新規作成ファイル**: なし。
  - **変更が必要な既存ファイル**: `README.md`、`bootstrap/README.md`、`scripts/README.md`、`infra/environments/dev/README.md`、`docs/operation/operation.md`、`docs/runbook/runbook.md`、変更した全`infra/modules/*/README.md`、変更した全`apps/*/README.md`（特に`apps/backend-api/README.md`のrouter実装済み反映）。
  - **実装内容**: 上記固定範囲を実装状態・Parameter Sheet・Build Procedureに同期し、旧3-module-only説明、旧repository数、旧パス、旧deploy入力、未実装表現を残さない。
  - **先行 Task**: 9（backend）, 31（parameter sheet）, 32（build procedure）。
  - _Requirements: 31.1, 31.2, 31.3_
  - **阻害要因**: B-034。
  - **Verification Category**: A。
  - **完了条件**: 固定範囲の全README/docsが実装を反映し、参照切れ・旧値・旧パスがなく、docs-consistency test成功。
  - **ローカル/CI テスト**: docs-consistency test。
  - **Category C 保留検証**: なし。
  - **rollback**: README / docs 変更を revert。

- [x] 34. 全静的・単体・mock 検証の集約実行
  - **実装目的**: A 全件と実行可能な B を集約し、skip を成功扱いしない検証スイートを整える（Req 32）。
  - **新規作成ファイル**: IAM policy static test、Product_B→Product_A boundary static test、module output-input contract test、secret hygiene test、docs-consistency test 等の集約テスト（未整備分）。
  - **変更が必要な既存ファイル**: テスト runner / CI ジョブ定義（Task 30 と整合）。
  - **実装内容**: 以下を集約実行:
    - `terraform fmt` / `init -backend=false` / `validate`（root + 全 module）。
    - property test 4 件（Property 1 dbname / Property 2 A→B キー / Property 3 OAuth state / Property 4 bucket naming、各 Hypothesis max_examples>=100）。これらは Requirement 検証に必要なため必須（`*` なし）。
    - IAM policy static test（wildcard / Registry membership / PassRole allowlist=4 ARN / `PassedToService` 条件 / migration-launcher の PassRole 2 ARN 限定 / iam 所有 5 ロール / scope / log group ARN の partition 変数使用 / bootstrapとiam moduleの4 role名一致 / bootstrapのdev state非参照）。
    - placeholder-absence（EKS manifest + frontend）、Product_B→Product_A boundary、contract（output→input）、distinct workload image、worker idempotency（in-memory fake 反復投入で 1 件収束）、Lambda reproducible-hash（2 回生成一致）、EventBridge/queue isolation（A static + B mock/LocalStack）、queue/DLQ config、cognito flows、API Gateway/CloudFront path、WAF root-to-child provider mappingと子module alias非参照、root glue所有、S3/CloudFront acyclicity、shell syntax + dry-run snapshot、secret hygiene（`git ls-files`）、DB schema検証（Docker非依存）、Parameter Sheetの9 worksheet/必須列/参照、Build Procedureの操作必須項目、固定README/docs範囲の整合。
    - skip 時は成功扱いせず理由・必要環境・残存リスクを報告（moto 未導入等）。testcontainers 版 schema は Category C / 任意のため未導入 skip は A の DoD に影響しない。Category C は Definition of Done に数えない。
  - **先行 Task**: 1〜33。
  - _Requirements: 32.1, 32.2, 32.3, 32.4, 6.5, 6.6, 8.3, 10.5, 11.3, 27.1, 27.2, 27.4, 15.2_
  - **阻害要因**: B-001〜B-034（静的/mock レベル総合確認）。
  - **Verification Category**: A / B（実行可能分）。
  - **完了条件**: A 全件成功、実行可能 B 成功、skip は成功扱いしない。
  - **ローカル/CI テスト**: 上記スイート一式。
  - **Category C 保留検証**: 各 C 項目（Task 35 で一覧化）。
  - **rollback**: 追加テストを除去。
  - **実施結果（2026-09-06）**: Verification AはPython 514件、Node.js 4件、shell構文、Terraform fmt、Bootstrap/Dev Root/全17 moduleのinit（backend=false）/validate、機密情報パターンスキャン、差分品質検査に合格。moto導入後の実行可能Verification Bも合格。任意のTask 11.1* testcontainers smoke 1件だけを未実施とし、成功件数に含めていない。

- [x] 35. Category C 保留検証一覧と最終報告
  - **実装目的**: Definition of Done を確認し、完了報告と Category C 保留検証を明示する（Req 33）。
  - **新規作成ファイル**: なし（Category C 一覧は `docs/operation/aws-build-procedure.md` の付録として記載）。
  - **変更が必要な既存ファイル**: `docs/operation/aws-build-procedure.md`（付録に Category C 一覧を追記）。
  - **実装内容**: 以下を確認・記載:
    - Verification A 全件成功。
    - 実行可能な Verification B 成功。
    - skip を成功扱いしない（skip 理由・必要環境・残存リスクを報告）。
    - Category C は未実施として明示（Req 5.3, 6.3/6.4, 6.7, 8.4/8.5, 9.2, 10.4, 11.4, 13.7, 14.3/14.4, 15.3, 16.4, 17.2, 18.2, 19.2, 20.4, 21.2, 22.4, 23.3/24.2/25.1/25.3/26.3 等）。
    - 全 P0（24 件, B-001〜B-024）を静的/mock レベルで解消しゼロ P0 を報告。残す P1 は書面受容分のみ。
    - region は ap-northeast-1、CLOUDFRONT WAF のみ us-east-1。
    - 完了報告は「statically verified; real AWS plan, apply, and E2E are not performed」と述べ、「AWS build is possible」と断定しない。
  - **先行 Task**: 34。
  - _Requirements: 33.1, 33.2, 33.3, 33.4, 33.5, 33.6, 33.7_
  - **阻害要因**: B-001〜B-034（Definition of Done 総括）。
  - **Verification Category**: A。
  - **完了条件**: ゼロ P0 報告、C 一覧を build procedure 付録へ記載、完了文言が「静的検証済み／実 AWS 未実施」で断定しない。
  - **ローカル/CI テスト**: docs-consistency test（C 一覧整合）。
  - **Category C 保留検証**: 一覧化した全項目（Operator 承認後）。
  - **rollback**: 完了報告記載を revert。
  - **実施結果（2026-09-06）**: `docs/operation/aws-build-procedure.md` 付録Aに全Category Cの要件/AC、状態、保留理由、必要環境、残存リスク、実施手順を記録。付録BにA/B検証結果、任意skip、残存P0=0、region境界、指定の非断定的完了文言を記録し、docs-consistency testに合格。

- [x] 36. Security Hub CRITICAL Finding のPortal一方向連携
  - **実装目的**: native Security Hub Findingを取り込み、CRITICALだけを既存Status Portalへ表示する（Req 34）。
  - **新規作成ファイル**: `apps/eks-workers/workers/critical_finding_linkage.py`。
  - **変更が必要な既存ファイル**: `infra/modules/messaging/*`、`infra/modules/eks/*`、`infra/environments/dev/outputs.tf`、Worker_Finding実装/manifest、Portal frontend、関連テスト/README/運用手順。
  - **実装内容**: Security Hub CRITICAL EventBridge rule→finding queue、ASFF複数Finding解析、全件Aurora冪等登録、CRITICALのみ決定的`status_id`で`public_status_items`へPutItem、Portal詳細へ重要度/リソース種別表示。Product_B→Product_A経路は追加しない。
  - **先行 Task**: 8, 13, 16, 17, 24, 27, 35。
  - _Requirements: 34.1, 34.2, 34.3, 34.4, 34.5, 34.6, 34.7_
  - **Verification Category**: A / C。
  - **完了条件**: EventBridge/IAM/static test、ASFF/CRITICAL限定/idempotency unit test、frontend test、Terraform fmt/validateが成功。
  - **ローカル/CI テスト**: EKS worker、messaging、EKS IAM、frontend、deploy-scriptの各test。
  - **Category C 保留検証**: Security Hub有効化済みdev環境での実Finding→CloudFront表示。BP-13-C02-SHを参照。
  - **rollback**: EventBridge rule/target、finding roleのDynamoDB権限、Worker_FindingのPortal投影、Portal表示拡張を同時にrevertする。

## Notes

- Requirement 検証に必要なテスト（Property 1〜4 の property test、bearer 認証 unit test 等）は**必須（`*` なし）**とし、Task 34 の Definition of Done に含める。
- **真に任意の追加検証のみ `*`（オプション）**とする（例: Task 11.1* の testcontainers 版 schema test。Docker が必要で Category C 相当）。トップレベル Task は `*` を付けない。
- 各 Task は Requirement と Acceptance Criteria を参照し traceability を確保する。
- 本フェーズは実 AWS 操作を行わない。Category C は手順・チェック内容のみ記述し、Operator 承認後の保留検証とする。
- Lambda package は versioned S3 object 方式に固定（ローカル filename 方式へ戻さない）。
- 循環回避（iam↔ecs は log group ARN 文字列組み立て（partition 変数使用）、s3-portal↔cloudfront は root bucket policy、iam↔ecs migration-launcher は root policy）を Task 順序で維持する。
- Security Group は network module 単一所有（alb 側 SG 二重作成は無効化）。
- module実装Taskは当該module内だけを変更し、未配線moduleを参照するroot glueはTask 27へ集約する。各Terraform Taskの完了時点で、そのTaskが掲げるmodule/rootの`terraform validate`を未定義参照なしで実行可能にする。
- bootstrapはDev_Root state/outputに依存せず、partition/account id/shared name prefix/決定的role名からPassRole ARNを組み立て、role-name contract testで一致を保証する。
- property test は 4 件のみ（Property 1〜4）。他は unit / static / contract で検証する。
- 実リポジトリパス: bootstrap は `bootstrap/`（`iam.tf` / `cicd.tf` / `buildspec/*.yml`）、EKS マニフェストは `apps/eks-workers/k8s/*.yaml`。

## P0 阻害要因マッピング表（静的/mock レベル解消の確認 Task）

| 阻害要因 | Priority | 解消を確認する Task | 総合確認 |
| --- | --- | --- | --- |
| B-001 | P0 | Task 27（dev root 全配線）, Task 32（build procedure Req1.8） | Task 34 |
| B-002 | P0 | Task 4（iam 5ロール）, Task 5（bootstrap PassRole）, Task 27（launcher root policy） | Task 34 |
| B-003 | P0 | Task 9（dbname/DB secret）, Task 10（ecs 注入） | Task 34 |
| B-004 | P0 | Task 9（dbname フォールバック + Property 1） | Task 34 |
| B-005 | P0 | Task 3（Bearer Secret）, Task 9（bearer 認証）, Task 10（secrets 注入） | Task 34 |
| B-006 | P0 | Task 11（migration image/runner）, Task 12（launcher）, Task 6（network/Aurora SG） | Task 34 |
| B-007 | P0 | Task 8（2 系統分離）, Task 13（worker 2 分割） | Task 34 |
| B-008 | P0 | Task 15（manifest レンダリング/placeholder 検査） | Task 34 |
| B-009 | P0 | Task 2（ECR 5 リポジトリ）, Task 11（migration リポジトリ）, Task 15（3 リポジトリ参照） | Task 34 |
| B-010 | P0 | Task 16（A→B 連携 + Property 2）, Task 17（DynamoDB）, Task 13（cronjob IRSA） | Task 34 |
| B-011 | P0 | Task 18（Lambda versioned S3 + reproducible hash）, Task 29（package 供給） | Task 34 |
| B-012 | P0 | Task 19（Cognito code+PKCE） | Task 34 |
| B-013 | P0 | Task 24（frontend OAuth + Property 3） | Task 34 |
| B-014 | P0 | Task 20（API Gateway）, Task 22（CloudFront /api/* behavior） | Task 34 |
| B-015 | P0 | Task 21（Portal S3基盤）, Task 22（CloudFront module）, Task 27（root bucket policy） | Task 34 |
| B-016 | P0 | Task 21（Portal bucket命名 + Property 4）, Task 27（ALB log bucket命名） | Task 34 |
| B-017 | P0 | Task 23（WAF us-east-1）, Task 27（provider alias 配線） | Task 34 |
| B-018 | P0 | Task 7（ALB access logging interface）, Task 27（bucket + policy + 配線） | Task 34 |
| B-019 | P0 | Task 28（partial backend） | Task 34 |
| B-020 | P0 | Task 1（.terraform-version）, Task 29（buildspec install） | Task 34 |
| B-021 | P0 | Task 28（lock file）, Task 29（binary plan artifact） | Task 34 |
| B-022 | P0 | Task 29（TF_VAR_*/SSM/Secrets 供給）, Task 31（parameter sheet） | Task 34 |
| B-023 | P0 | Task 13（EKS version 1.36）, Task 14（Fargate logging）, Task 32（version 再確認手順） | Task 34 |
| B-024 | P0 | Task 27（EKS access entry） | Task 34 |

**P0 合計 = 24 件**（B-001〜B-024）。全件が上記 Task で静的/mock レベル解消を確認し、Task 34 で総合確認、Task 35 でゼロ P0 報告。

### P1 / P2 阻害要因マッピング（欠落なし確認）

| 阻害要因 | Priority | 解消を確認する Task | 総合確認 |
| --- | --- | --- | --- |
| B-025 | P1 | Task 13（public_access_cidrs 必須 + 0.0.0.0/0 禁止 validation） | Task 34/35 |
| B-026 | P1 | Task 7（ALB TLS + HTTP redirect）, Task 6（network SG ALB→ECS 8080） | Task 34/35 |
| B-027 | P1 | Task 24（frontend token 保存 / config 生成 / placeholder） | Task 34/35 |
| B-028 | P1 | Task 15（deploy-eks.sh --platform）, Task 24（deploy scripts docker build 静的チェック） | Task 34/35 |
| B-029 | P1 | Task 26（VPC Flow Logs） | Task 34/35 |
| B-030 | P1 | Task 25（monitoring/SNS）, Task 31（cost/endpoint 記載） | Task 34/35 |
| B-031 | P1 | Task 30（CI 静的検証） | Task 34/35 |
| B-032 | P1 | Task 4（最小権限）, Task 5（PassRole allowlist）, Task 27（launcher PassRole 2 ARN） | Task 34/35 |
| B-033 | P1 | Task 3（Bearer 非出力）, Task 10（DB secret 非出力）, Task 34（secret hygiene） | Task 34/35 |
| B-034 | P2 | Task 33（README / docs 整合） | Task 34/35 |

**P1 合計 = 9 件**（B-025, B-026, B-027, B-028, B-029, B-030, B-031, B-032, B-033）+ **P2 = 1 件**（B-034）。P0 24 + P1 9 + P2 1 = **34 件、欠落なし**。

## Requirement ↔ Task 対応表

| Requirement | 対応 Task |
| --- | --- |
| Requirement 1: dev root 全モジュール配線 | 27, 32（1.8） |
| Requirement 2: IAM ロールと最小権限 | 4, 5, 27, 34 |
| Requirement 3: Backend DB シークレット注入と dbname フォールバック | 9, 10 |
| Requirement 4: Backend 内部 Bearer トークン | 3, 9, 10 |
| Requirement 5: DB マイグレーション実行手段 | 11, 12, 6, 32 |
| Requirement 6: メッセージング分離 | 8, 13, 34 |
| Requirement 7: EKS マニフェストレンダリングと Placeholder 検査 | 15 |
| Requirement 8: ECR リポジトリと EKS ワークロード別イメージ | 2, 11, 15 |
| Requirement 9: Docker アーキテクチャ整合 | 15, 24（docker build 静的チェック） |
| Requirement 10: Product_A→Product_B 連携 | 16, 17, 13, 34 |
| Requirement 11: Lambda 再現可能パッケージ | 18, 29 |
| Requirement 12: Cognito 設定 | 19 |
| Requirement 13: Frontend 認証フロー | 24 |
| Requirement 14: API Gateway と CloudFront パス整合 | 20, 22 |
| Requirement 15: S3/CloudFront 循環依存の解消 | 21, 22, 27, 34 |
| Requirement 16: S3 バケット命名の一意化 | 21, 27 |
| Requirement 17: CloudFront 用 WAF の us-east-1 provider | 23, 27 |
| Requirement 18: ALB アクセスログとポリシー | 7, 27 |
| Requirement 19: ALB TLS と HTTP リダイレクト | 7, 6, 31 |
| Requirement 20: EKS バージョン、アクセス、公開範囲 | 13, 27, 32 |
| Requirement 21: VPC Flow Logs | 26 |
| Requirement 22: Monitoring 配線と通知 | 25, 31, 32 |
| Requirement 23: Terraform backend の再現性 | 28, 29 |
| Requirement 24: CodeBuild Terraform バージョン固定 | 1, 29 |
| Requirement 25: Plan artifact と provider lock | 28, 29 |
| Requirement 26: Pipeline 入力の明示供給 | 29, 31 |
| Requirement 27: シークレット衛生 | 3, 10, 25, 28, 34 |
| Requirement 28: CI で Terraform 静的検証 | 30 |
| Requirement 29: 二段階構築手順 | 10（29.1）, 32 |
| Requirement 30: Deploy スクリプトの dry-run 既定と安全性 | 12, 15, 24 |
| Requirement 31: ドキュメント整合 | 33 |
| Requirement 32: 必須静的・単体テストスイート | 34 |
| Requirement 33: スコープ境界と完了条件 | 35 |
| Requirement 34: Security Hub CRITICAL Finding のポータル連携 | 36 |

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2", "3", "6", "8", "9", "17", "18", "19", "21", "23", "26"] },
    { "id": 1, "tasks": ["4", "7", "9.1", "9.2", "13", "20", "21.1"] },
    { "id": 2, "tasks": ["5", "10", "14", "16", "22"] },
    { "id": 3, "tasks": ["11", "15", "16.1", "24", "25"] },
    { "id": 4, "tasks": ["11.1", "12", "24.1"] },
    { "id": 5, "tasks": ["27"] },
    { "id": 6, "tasks": ["28", "30"] },
    { "id": 7, "tasks": ["29"] },
    { "id": 8, "tasks": ["31"] },
    { "id": 9, "tasks": ["32"] },
    { "id": 10, "tasks": ["33"] },
    { "id": 11, "tasks": ["34"] },
    { "id": 12, "tasks": ["35"] },
    { "id": 13, "tasks": ["36"] }
  ]
}
```
