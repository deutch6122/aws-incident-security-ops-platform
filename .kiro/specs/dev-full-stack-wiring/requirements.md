# Requirements Document

## Introduction

本 Feature「dev-full-stack-wiring」は、既存リポジトリ `aws-incident-security-ops-platform` の dev 環境（`infra/environments/dev`）を、検証用 AWS アカウントへ**再現可能に構築できる状態**まで整備・修正することを目的とする。現状 dev root は network / ecr / aurora のみ配線されており、残り 12 モジュール（alb / ecs / eks / messaging / logging / dynamodb / s3-portal / cloudfront / cognito / apigateway / lambda / monitoring）は意図的に未配線であるため、README 記載の完全構成を再現できない。

本 Feature の**スコープはリポジトリ内の設計・実装（IaC / アプリ / スクリプト）・テスト・ドキュメント修正に限定**され、実 AWS 操作（`terraform apply` / AWS CLI / kubectl / docker build・push / deploy script の `--execute`）は一切行わない。本 Feature は、外部で整理された全 34 件の阻害要因 B-001〜B-034（P0=24 / P1=9 / P2=1）を根拠として解消する。阻害要因を記録するパラメータシート `docs/operation/aws-resource-parameter-sheet.xlsx` は既存資料として参照するのではなく、**本 Feature で新規作成する成果物**として扱う（同名ファイルを本 Feature で作成し、阻害要因・パラメータ・供給元・コスト要因を記載する）。二段階構築手順（初回 infra は ECS desired 0 → image push / migration → desired 1 → EKS workload → CloudFront 確定後に Cognito callback 更新 → frontend 配信）を整備する。完了時は「AWS 構築可能」と断定せず「静的検証済み／実 AWS plan・apply・E2E は未実施」と明記する。

各 Acceptance Criterion は Verification_Category（(A) ローカル/CI 必須の静的・単体検証、(B) mock/LocalStack 等での統合検証、(C) Operator 承認後に実施する実行環境検証。実 AWS 操作に加えて Docker build / image inspect / kubectl / 外部デプロイ操作など実行環境を要する検証を含む）に分類される。EKS ワークロードの Running、CloudFront の HTTP 応答、実 SQS 配送、実 DB マイグレーション完了、`docker build` による image architecture inspect など、Operator 承認後に実行環境でのみ確認できる項目は (C) に分類し、本フェーズの Definition of Done とはしない。本フェーズで必須となるのは (A) と、mock/LocalStack で成立する範囲の (B) である。阻害要因 B-001〜B-034 と Requirement の対応は末尾の「Traceability」セクション、各 Requirement の検証分類は「Verification Classification」セクションに示す。

## Glossary

- **Dev_Root**: `infra/environments/dev` 配下の Terraform ルート構成（main.tf / variables.tf / outputs.tf / locals）を指す。
- **Terraform_Module**: `infra/modules/*` 配下の再利用可能な Terraform モジュール（network, ecr, aurora, alb, ecs, eks, messaging, logging, dynamodb, s3-portal, cloudfront, cognito, apigateway, lambda, monitoring, iam, waf）。
- **Backend_API**: ECS Fargate 上で稼働する Product_A の同期 API（FastAPI, X86_64）。
- **Worker_Alarm**: EKS 上で稼働する CloudWatch アラームイベント処理ワーカー（alarm-event-processor）。
- **Worker_Finding**: EKS 上で稼働するセキュリティ Finding 処理ワーカー（security-finding-worker）。
- **Cronjob_Summary**: EKS 上で稼働する月次集計 CronJob（monthly-summary-cronjob）。月次レポートの Product_A→Product_B 連携主体。
- **Portal_API**: Product_B の Lambda 関数（API Gateway 経由で公開）。
- **Portal_Frontend**: Product_B の静的フロントエンド（CloudFront + S3 配信）。
- **Portal_Storage**: Product_B の S3 バケット（静的サイト + `reports/*`、OAC 保護）。
- **Portal_DB**: Product_B の DynamoDB 4 テーブル（public_status_items / report_metadata / page_view_logs / maintenance_windows）。
- **Secrets_Store**: AWS Secrets Manager。DB パスワードや Bearer トークン等の実値の唯一の保管先。
- **Infra_Pipeline**: bootstrap で作成された CodePipeline + CodeBuild による IaC デプロイパイプライン。
- **CI_Workflow**: GitHub Actions のワークフロー（`.github/workflows/ci.yml`）。
- **Deploy_Script**: `scripts/deploy-*.sh` および `scripts/seed_*.py`（デフォルト dry-run、`--execute` で実行）。
- **Parameter_Sheet**: 本 Feature で新規作成する `docs/operation/aws-resource-parameter-sheet.xlsx`。AWS リソース、Terraform 入出力、編集箇所、値の供給元、コスト、検証方法を相互参照できる構築入力台帳。
- **Build_Procedure**: 本 Feature で新規作成する `docs/operation/aws-build-procedure.md`。空の検証用 AWS アカウントから構築、検証、ロールバック、撤去までを順番に実行できる詳細手順書。
- **Two_Phase_Build**: 二段階構築手順（初回 infra → image push / migration → 稼働化 → EKS workload → CloudFront 確定後 Cognito callback 更新 → frontend 配信）。
- **Operator**: dev 環境を構築・運用する担当者。
- **Placeholder**: `${...}` / `REPLACE_WITH_*` 等の未展開の差し込み文字列。
- **Sensitive_Value**: Secret / password / token / 実 AWS アカウント ID / 個人メールアドレス / 実 Connection ARN 等の秘匿情報。
- **Standard_Support_Version**: apply 直前に AWS 公式ドキュメントで再確認する、その時点で EKS が standard support として提供する Kubernetes バージョン。具体版数はハードコードせず、Technical Design の既定値（`1.36`）を出発点とし、apply 直前の再確認で Standard Support 外であればビルドを停止して既定値を更新する（extended support を前提にしない）。
- **Remote_State**: 暗号化・アクセス制限・バージョニングが有効化された S3 バックエンド上の Terraform state。Sensitive_Value が state に含まれ得ることを前提に保護される。
- **Resource_Level_Action**: AWS IAM がリソースレベル権限（特定 ARN への限定）をサポートする Action（例: `secretsmanager:GetSecretValue`, `s3:PutObject`, `dynamodb:PutItem`, `sqs:SendMessage`, `iam:PassRole`）。
- **Wildcard_Exception_Action**: AWS API 仕様上リソースレベル権限に対応せず、Resource 値に `*` を要する Action（例: 一部の `Describe*` / `List*`、`logs:CreateLogGroup` 等）。
- **Wildcard_Exception_Registry**: リポジトリ内に記録された、`Resource: "*"` の使用が許容される Wildcard_Exception_Action の一覧。各エントリは理由・対象 Action・適用する Condition（`aws:RequestedRegion`, `aws:ResourceTag` 等）を含む。
- **Idempotent_Processing**: 同一イベント（`external_id` 等の識別子）が複数回配送されても業務データへの反映が重複しない冪等制御。at-least-once 配信下で effectively-once の業務影響を得る。
- **Verification_Category**: 各 Acceptance Criterion の検証手段の分類。(A) ローカル/CI での静的・単体検証、(B) mock または LocalStack 等での統合検証、(C) Operator の明示承認後に実施する実行環境検証（実 AWS 操作に加えて Docker build / image inspect / kubectl / 外部デプロイ操作など、実行環境を要する検証を含む）。

## Requirements

### Requirement 1: dev root への全モジュール配線（B-001）

**User Story:** As an Operator, I want the dev Terraform root to wire all platform modules with a correct dependency graph, so that the complete dev environment can be planned as a single reproducible configuration.

#### Acceptance Criteria

1. THE Dev_Root SHALL declare all of the following Terraform_Modules (network, ecr, aurora, alb, ecs, eks, messaging, logging, dynamodb, s3-portal, cloudfront, cognito, apigateway, lambda, monitoring, iam, waf) and SHALL establish the correct dependency graph among them through module output references and the minimum necessary `depends_on` declarations, without relying on declaration order. [Verification: A]
2. WHERE a Terraform_Module requires an output of another module as input, THE Dev_Root SHALL pass that output as the consuming module's input. [Verification: A]
3. THE Dev_Root SHALL define, in variables.tf, every input variable required by the wired modules, with no wired-module input left undeclared. [Verification: A]
4. THE Dev_Root SHALL pass values consumed as inputs between wired modules through direct `module.<producer>.<output>` references without re-exposing them as root outputs, SHALL expose in outputs.tf only the non-sensitive values that a Deploy_Script, the Infra_Pipeline, the build procedure, or the Operator consumes externally, SHALL NOT emit any secret value as an output, and SHALL expose a secret ARN as an output only when that ARN is required for external Deploy_Script or manifest generation. [Verification: A]
5. WHERE a local Terraform provider cache is present, WHEN the Operator runs `terraform init -backend=false` followed by `terraform validate` against the Dev_Root without credentials, THE Dev_Root SHALL cause both commands to complete with a zero exit code. [Verification: A]
6. WHERE a local Terraform provider cache is absent, WHEN the Operator runs `terraform init -backend=false`, THE Operator SHALL be permitted to use network access solely to fetch providers, and this network use SHALL NOT be treated as a validation failure. [Verification: A]
7. THE credential-free static verification scope for the Dev_Root SHALL comprise `terraform fmt`, HCL syntax validity, variable and output reference resolution, and `terraform validate` under a present provider cache. [Verification: A]
8. IF `terraform validate` returns a non-zero exit code solely because of a network-access or credential requirement, THEN THE Operator SHALL record, in the build procedure documentation, the failure reason and the specific modules or resources whose validation was not performed. [Verification: A]

### Requirement 2: IAM ロールと最小権限（B-002, B-032）

**User Story:** As a security-conscious Operator, I want least-privilege IAM roles implemented and wired, so that the platform runs without administrator privileges.

#### Acceptance Criteria

1. THE iam Terraform_Module SHALL implement five roles as Terraform resources: the Backend ECS task execution role, the Backend ECS task role, the migration execution role, the migration task role, and the migration-launcher role. [Verification: A]
2. THE Dev_Root SHALL pass the iam module role outputs to the ecs module inputs so that the Backend task definition receives the Backend ECS task execution role and the Backend ECS task role, and the migration task definition receives the migration execution role and the migration task role. [Verification: A]
3. THE ECS task role SHALL grant `secretsmanager:GetSecretValue` scoped to the specific Secrets_Store secret ARNs required by Backend_API, with no other resource ARNs in scope for that action. [Verification: A]
4. THE iam Terraform_Module SHALL scope every Resource_Level_Action to specific secret, table, queue, bucket, or role ARNs, and SHALL NOT use a resource value of `*` for any Resource_Level_Action. [Verification: A]
5. WHERE an IAM statement uses a Wildcard_Exception_Action that AWS does not support at the resource level, THE iam Terraform_Module SHALL be permitted to set the Resource value to `*`, and SHALL constrain that statement with the applicable Condition keys (e.g., `aws:RequestedRegion`, `aws:ResourceTag`) available for that Action. [Verification: A]
6. WHERE a statement sets Resource to `*` for a Wildcard_Exception_Action, THE repository SHALL record that Action in the Wildcard_Exception_Registry with the reason, the target Action, and the applied Condition constraints. [Verification: A]
7. WHERE a Terraform_Module requires `Create*WithTags` or other action-level permissions for the complete configuration, THE iam Terraform_Module SHALL grant those actions scoped to the specific resource ARNs the configuration operates on when the Action supports resource-level scoping. [Verification: A]
8. THE static IAM policy tests SHALL fail if any statement uses a resource value of `*` for a Resource_Level_Action, if a statement uses `*` for an Action not present in the Wildcard_Exception_Registry, if `PassRole` is granted to any role ARN outside the explicitly enumerated PassRole allowlist (the Backend ECS task execution role, the Backend ECS task role, the migration execution role, and the migration task role ARNs), if any `PassRole` statement lacks the `iam:PassedToService = ecs-tasks.amazonaws.com` condition, if the migration-launcher role's `PassRole` targets any role other than the migration execution role and the migration task role, or if any secret, table, or queue permission is granted to an ARN outside the required set. [Verification: A]
9. IF a required iam module role output is absent when the ecs module is wired, THEN THE Dev_Root SHALL fail validation with a non-zero exit code and an error indicating the missing role output. [Verification: A]
10. THE bootstrap Terraform root SHALL derive the four `iam:PassRole` target ARNs without reading Dev_Root state or outputs, using the current AWS partition, current account id, shared `name_prefix`, and the four deterministic role names; AND a contract test SHALL verify that those names match the role names created by the iam Terraform_Module. [Verification: A]

### Requirement 3: Backend DB シークレット注入と dbname フォールバック（B-003, B-004）

**User Story:** As an Operator, I want Backend_API to receive its database secret by ARN and safely resolve the database name, so that Aurora connectivity works with an RDS-managed secret.

#### Acceptance Criteria

1. THE ecs module SHALL inject the Aurora database secret into Backend_API using a single environment variable `BACKEND_DB_SECRET_ARN` whose value is a non-empty Secrets Manager secret ARN, and SHALL NOT inject the secret's plaintext payload into any other environment variable. [Verification: A]
2. THE ecs module SHALL NOT emit the database secret's plaintext value into any Terraform output, log, plaintext environment definition, or repository file, and any generated secret material SHALL reside in Remote_State only under the protection described for Terraform state. [Verification: A]
3. THE ECS task role SHALL be granted `secretsmanager:GetSecretValue` scoped to the specific ARN referenced by `BACKEND_DB_SECRET_ARN`, and SHALL NOT be granted that action on any other secret resource. [Verification: A]
4. IF the resolved secret payload does not contain a non-empty `dbname` field, THEN THE Backend_API SHALL resolve the database name from the separately configured environment variable `BACKEND_DB_NAME`. [Verification: A]
5. IF the secret payload lacks a non-empty `dbname` field AND `BACKEND_DB_NAME` is unset or empty, THEN THE Backend_API SHALL fail startup and SHALL surface a configuration error that does not include any secret field value. [Verification: A]
6. THE Backend_API SHALL pass an automated test that supplies an RDS-managed-secret-shaped payload (containing `username`, `password`, `host`, `port` and omitting `dbname`) and asserts the resolved database name equals the value of `BACKEND_DB_NAME`. [Verification: A]

### Requirement 4: Backend 内部 Bearer トークン（B-005）

**User Story:** As an Operator, I want an internal bearer token generated and injected securely, so that internal callers are authenticated.

#### Acceptance Criteria

1. THE Terraform configuration SHALL generate a random `BACKEND_INTERNAL_BEARER_TOKEN` value of at least 32 characters, SHALL store its real value in Secrets_Store as the value's storage location, and SHALL NOT emit that value into any Terraform output, log, plaintext environment definition, or repository file. [Verification: A]
2. THE generated bearer token value, where present in Terraform state, SHALL reside in Remote_State only under encryption, access restriction, and versioning. [Verification: A]
3. THE ecs module SHALL inject the bearer token into Backend_API as a Secrets_Store secret reference rather than a plaintext environment value. [Verification: A]
4. WHEN a request to a protected route carries an `Authorization` header of the form `Bearer <token>` whose token exactly matches the injected `BACKEND_INTERNAL_BEARER_TOKEN`, THE Backend_API SHALL NOT respond with HTTP 401 or 403 and SHALL return the target test endpoint's expected success status. [Verification: A]
5. IF a request to a protected route omits the `Authorization` header, uses a non-`Bearer` scheme, or presents a token that does not exactly match the injected token, THEN THE Backend_API SHALL respond with HTTP 401 and SHALL include a `WWW-Authenticate: Bearer` response header. [Verification: A]

### Requirement 5: DB マイグレーション実行手段（B-006）

**User Story:** As an Operator, I want an AWS-targeted migration runner, so that the seven business tables are created in the Aurora database inside the VPC.

#### Acceptance Criteria

1. THE repository SHALL provide a one-off migration task or job definition that executes within the VPC and targets the Aurora database, without exposing the migration entry point on any public network path. [Verification: A]
2. THE build procedure documentation SHALL describe the migration execution steps as an ordered, reproducible sequence sufficient for an Operator to run the migration without additional undocumented steps. [Verification: A]
3. WHEN the migration completes successfully, THE Aurora database SHALL contain the seven defined business tables, each with its defined primary keys, foreign keys, and unique constraints, and this SHALL be verifiable by an automated schema test that asserts the presence of all seven business table names and each declared constraint, WHERE the Verification: A schema test runs without Docker by statically parsing the migration SQL or by using a Docker-independent fixture (e.g., an in-memory or file-based database). [Verification: A for the Docker-independent local/CI schema test; C for the real Aurora migration run pending Operator approval]
4. THE automated schema test SHALL exclude migration-management and system tables (e.g., `alembic_version`) from any table-count judgement and SHALL NOT require the total table count to equal seven. [Verification: A]
5. IF the migration fails before completion, THEN THE migration runner SHALL exit with a non-zero status and SHALL leave the schema in its pre-migration state or a re-runnable state, such that re-executing the migration reaches the same successful end state. [Verification: A for the runner's exit and re-runnability logic; C for the real Aurora run pending Operator approval]

### Requirement 6: メッセージング分離（B-007）

**User Story:** As an Operator, I want alarm and finding events routed to separate queues under at-least-once delivery with idempotent processing, so that each worker consumes only its own events and the business-data effect is effectively-once.

#### Acceptance Criteria

1. THE messaging Terraform_Module SHALL define a separate EventBridge rule, SQS Standard queue, and DLQ for alarm detail-type events and for finding detail-type events. [Verification: A]
2. THE messaging configuration SHALL assume SQS Standard at-least-once delivery, under which duplicate delivery of the same event can occur. [Verification: A]
3. WHEN an alarm event is published, THE messaging configuration SHALL deliver it only to the alarm queue consumed by Worker_Alarm and SHALL NOT deliver it to the finding queue. [Verification: B via mock/LocalStack; C for real EventBridge/SQS routing pending Operator approval]
4. WHEN a finding event is published, THE messaging configuration SHALL deliver it only to the finding queue consumed by Worker_Finding and SHALL NOT deliver it to the alarm queue. [Verification: B via mock/LocalStack; C for real EventBridge/SQS routing pending Operator approval]
5. THE workers SHALL apply Idempotent_Processing keyed on an event identifier (e.g., `external_id`) such that, under at-least-once delivery with possible duplicates, the effect on business data is effectively-once and no duplicate business record is created. [Verification: A for the worker idempotency unit test]
6. THE isolation tests SHALL verify that each event type is routed only to its dedicated worker's queue and that re-delivering the same event to that worker yields no additional business-data record beyond the first processing. [Verification: A for idempotency; B via mock/LocalStack for routing isolation]
7. IF a worker fails to process a message after the configured maximum receive count of 5 attempts, THEN THE messaging configuration SHALL move the message to that queue's dedicated DLQ and SHALL NOT deliver it to the other worker's queue. [Verification: A for the queue/DLQ configuration; C for the real max-receive-count behavior pending Operator approval]

### Requirement 7: EKS マニフェストレンダリングと Placeholder 検査（B-008）

**User Story:** As an Operator, I want EKS manifests fully rendered before apply, so that no unexpanded placeholders reach the cluster.

#### Acceptance Criteria

1. THE Deploy_Script for EKS SHALL render manifests by substituting variables (e.g., via envsubst) into a temporary generated manifest before applying. [Verification: A]
2. WHEN a manifest is rendered, THE Deploy_Script SHALL scan the rendered output for `${...}` and `REPLACE_WITH_*` Placeholders. [Verification: A]
3. IF a rendered manifest contains any Placeholder, THEN THE Deploy_Script SHALL fail with an explicit error. [Verification: A]

### Requirement 8: ECR リポジトリと EKS ワークロード別イメージ（B-009）

**User Story:** As an Operator, I want ECR repositories aligned one-to-one with each container workload, so that Backend_API, each EKS worker, and the migration runner use their own image consistently.

#### Acceptance Criteria

1. THE ecr Terraform_Module SHALL maintain five repositories: one for Backend_API, three for the worker workloads (Worker_Alarm, Worker_Finding, Cronjob_Summary), and one for the DB migration runner. [Verification: A]
2. THE EKS Deploy_Script SHALL reference the existing three worker repositories rather than a nonexistent single `eks-workers` repository. [Verification: A]
3. THE EKS manifests SHALL reference a distinct image per workload (Worker_Alarm, Worker_Finding, Cronjob_Summary), such that no two workloads reference the same repository, and the migration runner SHALL reference its own dedicated migration repository distinct from the Backend_API and worker repositories. [Verification: A]
4. WHEN the three workloads are deployed to a real cluster, THE workload tests SHALL verify that each reaches a Running or Job-complete state within 300 seconds using its respective image. [Verification: C pending Operator approval; static/manifest checks in Verification: A are mandatory for this phase]
5. IF a workload or the migration runner references a repository or image tag that does not exist, THEN THE workload tests SHALL report the affected workload as failed with an indication that the image could not be pulled, and the deployment SHALL NOT be marked successful. [Verification: A for the manifest-to-repository reference check; C for the real image-pull outcome pending Operator approval]

### Requirement 9: Docker アーキテクチャ整合（B-028）

**User Story:** As an Operator building on non-x86 hardware, I want images pinned to linux/amd64, so that they match the ECS X86_64 runtime.

#### Acceptance Criteria

1. THE Deploy_Script that builds container images SHALL specify `--platform linux/amd64` for every docker build. [Verification: A for the script static check]
2. THE image architecture tests SHALL verify that the produced image architecture matches the ECS task X86_64 runtime. [Verification: C pending Operator approval, since a real build/inspect is required]

### Requirement 10: Product_A→Product_B 連携（B-010）

**User Story:** As an Operator, I want Cronjob_Summary configured with portal targets and scoped write permissions, so that monthly reports flow one-way from Product_A to Product_B.

#### Acceptance Criteria

1. THE Cronjob_Summary manifest SHALL define the three portal integration environment values (reports bucket, report_metadata table, public_status_items table). [Verification: A]
2. THE Cronjob_Summary IRSA role SHALL grant `s3:PutObject` scoped to `reports/*` of Portal_Storage and `dynamodb:PutItem` scoped to the report_metadata and public_status_items tables, and SHALL NOT grant read or write permission to any other Portal_Storage prefix or table. [Verification: A]
3. THE Cronjob_Summary SHALL derive a deterministic S3 object key (e.g., from the reporting period) and deterministic DynamoDB item keys, and SHALL write using a conditional put or upsert (e.g., `PutItem`) so that the operation is idempotent. [Verification: A for the key-derivation and write-mode unit test]
4. WHEN Cronjob_Summary is retried after a prior run, THE integration SHALL converge, via upsert to the deterministic keys, to a final state equivalent to one S3 report object under `reports/*` and one item in each of the two target tables, without creating duplicate objects or items. [Verification: A for the idempotency unit test; B via mock/LocalStack; C for the real S3/DynamoDB run pending Operator approval]
5. THE boundary tests SHALL verify that Product_B components cannot read from or write to the Product_A Aurora database. [Verification: A for the permission/network-boundary static test]
6. IF Cronjob_Summary fails to write any one of the three target outputs, THEN THE integration SHALL report the run as failed with an indication of which target write failed, and SHALL NOT report the run as successful. [Verification: A for the failure-reporting unit test; C for the real run pending Operator approval]

### Requirement 11: Lambda 再現可能パッケージ（B-011）

**User Story:** As an Operator, I want the Lambda package built reproducibly, so that its deployment is verifiable and consistent.

#### Acceptance Criteria

1. THE lambda Terraform_Module SHALL be provided the package produced by a reproducible build step as a versioned S3 object reference (`package_s3_bucket`, `package_s3_key`, and `package_s3_object_version`) rather than as a local package filename, WHERE the reproducible build step uploads the deterministic package to a versioning-enabled artifact bucket under an immutable key and retrieves the resulting object version. [Verification: A for the S3-reference wiring; C for the real package upload pending Operator approval]
2. THE lambda Terraform_Module SHALL set both `source_code_hash` and the S3 `package_s3_object_version` from the built package so that plan and apply reference the identical package. [Verification: A]
3. THE reproducible-package tests SHALL verify that repeated builds of the same source produce the same package hash. [Verification: A]
4. THE build procedure documentation SHALL describe a Lambda invoke smoke check to be run after apply. [Verification: A for documenting the check; C for executing the real invoke pending Operator approval]

### Requirement 12: Cognito 設定（B-012）

**User Story:** As a Viewer, I want Cognito configured with a hosted domain and OAuth code + PKCE, so that I can sign in to the portal.

#### Acceptance Criteria

1. THE cognito Terraform_Module SHALL configure a User Pool domain, at least one app client callback URL, at least one logout URL, the allowed OAuth flows, and the allowed OAuth scopes. [Verification: A]
2. THE cognito app client SHALL enable the authorization code grant with PKCE and SHALL NOT enable the implicit grant. [Verification: A]
3. THE cognito Terraform_Module SHALL expose the issuer URL and app client id as non-empty string outputs for the apigateway JWT authorizer. [Verification: A]
4. IF the configured callback URLs or logout URLs list is empty, THEN THE cognito Terraform_Module SHALL fail during plan or apply with an error indicating the missing URL configuration. [Verification: A via validation/precondition]

### Requirement 13: Frontend 認証フロー（B-013, B-027）

**User Story:** As a Viewer, I want the frontend to complete the OAuth callback and retain tokens securely, so that I can access the portal APIs.

#### Acceptance Criteria

1. WHEN the OAuth callback is invoked, THE Portal_Frontend SHALL complete the authorization code grant with PKCE and SHALL validate that the returned `state` value equals the `state` value sent in the authorization request. [Verification: A]
2. IF the returned `state` value does not equal the sent `state` value, THEN THE Portal_Frontend SHALL reject the callback, SHALL NOT store any token, and SHALL present an error indication to the Viewer. [Verification: A]
3. WHEN valid tokens are obtained, THE Portal_Frontend SHALL retain the tokens using a token-storage mechanism that accounts for XSS risk and enforces token expiry, where the concrete mechanism (in-memory, sessionStorage, httpOnly cookie, or equivalent) is selected in the Technical Design. [Verification: A]
4. WHEN the Viewer initiates logout, THE Portal_Frontend SHALL remove the retained tokens and redirect to the Cognito logout URL. [Verification: A]
5. THE Deploy_Script for the frontend SHALL generate a temporary `config.js` from Terraform outputs and SHALL scan the generated frontend artifacts for Placeholders, where a Placeholder is any unresolved template token remaining after Terraform output substitution, before sync. [Verification: A]
6. IF the generated frontend artifacts contain any Placeholder, THEN THE Deploy_Script SHALL exit with a non-zero status and SHALL NOT publish the artifacts. [Verification: A]
7. WHEN a Viewer signs in successfully against the deployed portal, THE Portal_Frontend SHALL receive a response from each of the four portal APIs. [Verification: C pending Operator approval; component-level unit tests in Verification: A are mandatory for this phase]

### Requirement 14: API Gateway と CloudFront パス整合（B-014）

**User Story:** As an Operator, I want the API Gateway on the default stage with a proxy route, so that CloudFront forwards `/api/*` unchanged.

#### Acceptance Criteria

1. THE apigateway Terraform_Module SHALL use the `$default` stage with route `/api/{proxy+}`. [Verification: A]
2. THE cloudfront Terraform_Module SHALL forward `/api/*` requests to the API origin with the request path preserved unchanged. [Verification: A for the origin/behavior configuration]
3. WHEN a request is sent to CloudFront `/api/status` with a token that passes the JWT authorizer, THE integration SHALL respond with HTTP 200. [Verification: C pending Operator approval; the JWT authorizer logic is covered by Verification: A/B]
4. IF a request is sent to CloudFront `/api/status` without a token or with a token that fails the JWT authorizer, THEN THE integration SHALL respond with HTTP 401. [Verification: C pending Operator approval; the authorizer rejection logic is covered by Verification: A/B]

### Requirement 15: S3/CloudFront 循環依存の解消（B-015）

**User Story:** As an Operator, I want the S3–CloudFront dependency broken into resource-level references, so that the plan has no dependency cycle.

#### Acceptance Criteria

1. THE Dev_Root SHALL structure the S3–CloudFront relationship as bucket creation, then distribution creation, then bucket policy attachment referencing the distribution ARN. [Verification: A]
2. THE Terraform graph for the Dev_Root SHALL contain no dependency cycle involving s3-portal and cloudfront. [Verification: A via `terraform graph`]
3. WHEN `terraform plan` is run against the Dev_Root, THE Dev_Root SHALL complete without emitting a cycle error. [Verification: B/C, since `terraform plan` requires provider/credential access; the cycle-free graph is verifiable in Verification: A]

### Requirement 16: S3 バケット命名の一意化（B-016, B-018）

**User Story:** As an Operator, I want portal and ALB log bucket names to include account id and region, so that names are globally unique.

#### Acceptance Criteria

1. THE Portal_Storage bucket name SHALL include the AWS account id and region as a suffix. [Verification: A]
2. THE ALB access-logs bucket name SHALL include the AWS account id and region as a suffix. [Verification: A]
3. THE generated bucket names SHALL be at most 63 characters. [Verification: A]
4. THE plan SHALL show unique bucket names for Portal_Storage and the ALB access-logs bucket. [Verification: A for the naming-expression uniqueness check; C for the real plan output pending Operator approval]

### Requirement 17: CloudFront 用 WAF の us-east-1 provider（B-017）

**User Story:** As an Operator, I want the CLOUDFRONT-scope WAF created in us-east-1, so that CloudFront can associate it.

#### Acceptance Criteria

1. THE Dev_Root SHALL define an `aws.us_east_1` aliased provider and pass it to the WAF module used by CloudFront. [Verification: A]
2. WHERE the WAF scope is CLOUDFRONT, THE plan SHALL show the WAF Web ACL created under the us-east-1 provider. [Verification: A for the provider-alias wiring; C for the real plan output pending Operator approval]

### Requirement 18: ALB アクセスログとポリシー（B-018）

**User Story:** As an Operator, I want an ALB access-logs bucket with the correct delivery policy, so that ALB logging is enabled.

#### Acceptance Criteria

1. THE Dev_Root SHALL create an ALB access-logs S3 bucket with the ALB log-delivery bucket policy. [Verification: A]
2. WHEN the alb module is planned, THE ALB attributes SHALL show access logging enabled targeting that bucket. [Verification: A for the access-logging configuration; C for the real plan output pending Operator approval]

### Requirement 19: ALB TLS と HTTP リダイレクト（B-026）

**User Story:** As a security-conscious Operator, I want ALB to require TLS and redirect HTTP, so that backend traffic is encrypted.

#### Acceptance Criteria

1. THE alb Terraform_Module SHALL require an ACM certificate as a mandatory input. [Verification: A]
2. WHEN a request arrives on the HTTP listener, THE alb SHALL respond with an HTTP 301 or 302 redirect to HTTPS. [Verification: A for the listener redirect-action configuration; C for the real HTTP response pending Operator approval]
3. THE alb SHALL terminate TLS at the load balancer, SHALL serve viewer traffic only over the HTTPS listener bound to the ACM certificate, and SHALL forward to the backend target group over HTTP on the backend application port within the private subnets, with the ALB security group permitting only that backend port egress to the ECS security group. [Verification: A]

### Requirement 20: EKS バージョン、アクセス、公開範囲（B-023, B-024, B-025）

**User Story:** As a security-conscious Operator, I want EKS pinned to a supported version with scoped access, so that the cluster is operable and not publicly exposed.

#### Acceptance Criteria

1. THE eks Terraform_Module SHALL default the Kubernetes version to a Standard_Support_Version, using the Technical Design default of `1.36` as the starting value rather than any hardcoded lower bound. [Verification: A]
2. THE build procedure documentation SHALL instruct the Operator to re-confirm, against the official AWS documentation, that the configured version is still within Standard Support immediately before apply, and IF the configured version is outside Standard Support THEN THE Operator SHALL halt the plan or apply and update the version before proceeding, without relying on extended support. [Verification: A]
3. THE Dev_Root SHALL create an `aws_eks_access_entry` and access policy association for the kubectl-executing principal. [Verification: A]
4. WHEN the operator role runs `kubectl auth can-i`, THE EKS access configuration SHALL grant the expected authorization. [Verification: C pending Operator approval; the access-entry configuration is verifiable in Verification: A]
5. THE eks module `public_access_cidrs` input SHALL be a mandatory input restricted to operator CIDRs, and the plan SHALL NOT contain `0.0.0.0/0`. [Verification: A for the input/validation static check]

### Requirement 21: VPC Flow Logs（B-029）

**User Story:** As an Operator, I want VPC Flow Logs enabled, so that network traffic is recorded.

#### Acceptance Criteria

1. THE logging Terraform_Module SHALL implement an `aws_flow_log` resource and its associated IAM role in addition to the log group. [Verification: A]
2. WHEN VPC Flow Logs are enabled, THE configuration SHALL record entries to a log stream, verifiable by the build procedure check. [Verification: C pending Operator approval; the flow-log resource wiring is verifiable in Verification: A]

### Requirement 22: Monitoring 配線と通知（B-030）

**User Story:** As an Operator, I want monitoring fully wired with two DLQ alarms and notifications, so that failures are observable.

#### Acceptance Criteria

1. THE Dev_Root SHALL wire all monitoring inputs from ecs, eks, alb, lambda, aurora, and messaging outputs. [Verification: A]
2. THE monitoring Terraform_Module SHALL define a DLQ alarm for each of the two DLQs (alarm and finding). [Verification: A]
3. THE monitoring Terraform_Module SHALL configure an SNS subscription for notifications whose enablement is controlled by a variable, SHALL source the subscription endpoint from a parameter supply mechanism (e.g., SSM Parameter Store) rather than a literal, and SHALL NOT record any real email address or endpoint value in any tfvars example, this Spec, a README, or a Terraform output. [Verification: A]
4. THE build procedure documentation SHALL describe an alarm-state and notification test, SHALL note that an email subscription confirmation is a Verification: C step, and SHALL state that an unconfirmed subscription does not cause the Terraform configuration itself to fail. [Verification: A for documenting the test; C for executing the real alarm/notification and the subscription confirmation pending Operator approval]

### Requirement 23: Terraform backend の再現性（B-019）

**User Story:** As an Operator, I want a committed partial backend, so that pipeline and local use the same remote state.

#### Acceptance Criteria

1. THE Dev_Root SHALL commit a partial `backend.tf` (without Sensitive_Values) to version control. [Verification: A]
2. THE Infra_Pipeline SHALL supply the state bucket via CodeBuild environment variables or `-backend-config`. [Verification: A]
3. WHEN plan or apply runs, THE Dev_Root SHALL use the same S3 state bucket and key and SHALL NOT fall back to local state. [Verification: A for the backend configuration static check; C for the real plan/apply pending Operator approval]

### Requirement 24: CodeBuild Terraform バージョン固定（B-020）

**User Story:** As an Operator, I want Terraform installed with a pinned version and checksum, so that all pipeline stages use the same version.

#### Acceptance Criteria

1. THE Infra_Pipeline buildspec SHALL install Terraform pinned to a specific version verified by checksum, rather than an echo placeholder. [Verification: A]
2. WHEN each pipeline stage runs, THE stages SHALL report the same Terraform version. [Verification: A for the buildspec static check; C for the real pipeline run pending Operator approval]

### Requirement 25: Plan artifact と provider lock（B-021）

**User Story:** As an Operator, I want binary plan artifacts and a committed lock file, so that only the approved plan is applied.

#### Acceptance Criteria

1. THE Infra_Pipeline SHALL produce a binary `tfplan` and a human-readable summary as stage-scoped artifacts across all stages. [Verification: A for the buildspec/artifact configuration; C for the real artifact production pending Operator approval]
2. THE Dev_Root SHALL commit the Terraform dependency lock file for the dev configuration. [Verification: A]
3. WHEN apply runs, THE Infra_Pipeline SHALL apply only the approved binary plan produced with the same Terraform version and provider versions. [Verification: C pending Operator approval; the pipeline configuration is verifiable in Verification: A]

### Requirement 26: Pipeline 入力の明示供給（B-022）

**User Story:** As an Operator, I want dev variable inputs supplied explicitly, so that plan summaries match approved values without committing ignored tfvars.

#### Acceptance Criteria

1. THE Infra_Pipeline SHALL supply dev variable values by source type: safe non-sensitive defaults declared in `variables.tf`, environment-specific non-sensitive values and operational parameters such as operator CIDRs and notification endpoints via SSM Parameter Store, and secret values via Secrets Manager, since `terraform.tfvars` is Git-ignored; THE CodeBuild build SHALL assign retrieved values to transient `TF_VAR_*` environment variables; and THE supply source for each parameter SHALL be recorded one-to-one in the parameter sheet. [Verification: A]
2. THE Infra_Pipeline SHALL NOT commit or transcribe Git-ignored tfvars values into any artifact, SHALL NOT place any Terraform-generated secret into Git or a pipeline input, and WHERE a transient tfvars file is used it SHALL NOT be turned into an artifact and SHALL be discarded at the end of the build. [Verification: A]
3. WHEN plan runs, THE plan summary SHALL match the approved input values. [Verification: C pending Operator approval; the input-supply configuration is verifiable in Verification: A]
4. THE Parameter_Sheet SHALL contain separate worksheets for usage/prerequisites, AWS resources, Terraform inputs, file-edit mapping, Terraform outputs and derived values, Deploy_Script environment variables, cost and retention settings, Verification: C checks, and pre-destroy checks. [Verification: A]
5. FOR every configurable parameter, THE Parameter_Sheet SHALL record the AWS service/resource, Terraform module, resource or data block, variable/output name, target file, configuration location, type, required/optional status, default value, recommended dev value, whether an environment-specific replacement is required, value source, SSM or Secrets Manager supply method, sensitivity classification, effect when unset, cost effect, post-apply verification method, and related Build_Procedure step number. [Verification: A]

### Requirement 27: シークレット衛生（B-033）

**User Story:** As a security-conscious Operator, I want no sensitive values in Git, so that secrets and account details are never committed.

#### Acceptance Criteria

1. THE repository SHALL keep `bootstrap/terraform.tfvars` and other Sensitive_Value-bearing files untracked by Git. [Verification: A]
2. THE Dev_Root and its deliverables SHALL NOT emit or transcribe real account ids, connection ARNs, secret values, or other Sensitive_Values into any output, log, plaintext environment definition, or repository file. [Verification: A]
3. WHERE a Sensitive_Value is present in Terraform state, THE state SHALL be held in Remote_State only under encryption, access restriction, and versioning, rather than being assumed absent from state. [Verification: A]
4. WHEN `git ls-files` is run, THE Sensitive_Value-bearing files SHALL NOT appear as tracked. [Verification: A]

### Requirement 28: CI で Terraform 静的検証（B-031）

**User Story:** As a maintainer, I want CI to run Terraform static checks, so that pull requests are validated without AWS access.

#### Acceptance Criteria

1. THE CI_Workflow SHALL run `terraform fmt`, `terraform init -backend=false`, and `terraform validate` for the Dev_Root and each Terraform_Module, WHERE `init` reuses a provider cache when one is present and is permitted to fetch providers over the network when the cache is absent, without supplying AWS credentials and without running `terraform plan` or `terraform apply`. [Verification: A]
2. THE CI_Workflow SHALL NOT perform any real AWS operation (terraform apply, AWS CLI, kubectl, docker build/push, s3 sync, CloudFront invalidation). [Verification: A]
3. WHEN CI runs on a pull request, THE CI_Workflow SHALL complete successfully. [Verification: A]

### Requirement 29: 二段階構築手順（Two_Phase_Build）

**User Story:** As an Operator, I want a documented two-phase build sequence, so that the environment can be built from scratch reproducibly.

#### Acceptance Criteria

1. THE ecs module SHALL allow `ecs_desired_count` to be set to 0 for the initial build. [Verification: A]
2. THE build procedure documentation SHALL describe the sequence: first produce the reproducible Lambda package before the initial apply, then initial infra with ECS desired 0, then image push and DB migration, then set ECS desired to 1, then deploy EKS workloads, then update the Cognito callback and logout URLs after the CloudFront domain is determined, then publish the frontend. [Verification: A]
3. WHERE the CloudFront domain is required for the Cognito callback URL, THE build procedure SHALL specify updating the Cognito callback after the CloudFront distribution is created. [Verification: A]
4. THE `docs/operation/aws-build-procedure.md` SHALL present the steps in an order the Operator can execute sequentially. [Verification: A]
5. FOR every file-edit operation, THE Build_Procedure SHALL identify the target file, configuration block or key, placeholder example, authoritative value source, and the condition that must be satisfied before the edit is considered complete. [Verification: A]
6. FOR every command operation, THE Build_Procedure SHALL identify the step number, purpose, working directory, prerequisites, exact command, dry-run or plan review method, expected successful result, failure stop condition, log or output to inspect, rollback method, and condition for continuing to the next step. [Verification: A]
7. THE Build_Procedure SHALL include the full sequence from account and cost prerequisites through Bootstrap, pipeline input preparation, Lambda package publication, two-phase infrastructure deployment, application deployment, sample data, monitoring verification, rollback, cost shutdown, and destroy, without relying on any undocumented operation. [Verification: A]

### Requirement 30: Deploy スクリプトの dry-run 既定と安全性

**User Story:** As an Operator, I want deploy scripts to default to dry-run, so that no external change happens without explicit intent.

#### Acceptance Criteria

1. THE Deploy_Script SHALL default to dry-run (print-only) and SHALL perform external changes (docker, aws, kubectl, s3 sync, invalidation) only when `--execute` is explicitly passed. [Verification: A]
2. THE Deploy_Script SHALL read required values from environment variables and SHALL NOT embed real ARNs, account ids, domains, or secrets. [Verification: A]
3. THE Deploy_Script SHALL NOT invoke terraform. [Verification: A]

### Requirement 31: ドキュメント整合（B-034）

**User Story:** As a maintainer, I want documentation synchronized with the implementation, so that instructions and parameters are consistent.

#### Acceptance Criteria

1. WHEN the implementation is complete, THE Backend_API README SHALL reflect that the router is implemented rather than stating the task is unimplemented. [Verification: A]
2. THE documentation, procedure, and parameter references SHALL be synchronized with the implemented configuration, verifiable by a docs-consistency test. [Verification: A]
3. THE documentation synchronization scope SHALL explicitly include `README.md`, `bootstrap/README.md`, `scripts/README.md`, `infra/environments/dev/README.md`, `docs/operation/operation.md`, `docs/runbook/runbook.md`, every README of a modified Terraform_Module, and every README of a modified application. [Verification: A]

### Requirement 32: 必須静的・単体テストスイート

**User Story:** As a maintainer, I want a comprehensive static and unit test suite, so that correctness is verified without real AWS operations.

#### Acceptance Criteria

1. THE test suite SHALL include the existing unit tests, `terraform fmt`, and per-root/per-module `terraform init -backend=false` and `terraform validate`. [Verification: A]
2. THE test suite SHALL include module output-input contract tests, IAM policy static tests (Resource_Level_Action wildcard, Wildcard_Exception_Registry membership, PassRole, secret/table/queue scope), manifest and config Placeholder tests, EventBridge rule and queue isolation tests, worker idempotency tests, OAuth code+PKCE and state frontend tests, Lambda reproducible-package and hash tests, shell syntax and dry-run snapshot tests, and a Product_B-to-Product_A boundary test. [Verification: A; the routing-isolation portion may run in Verification: B via mock/LocalStack]
3. IF a test is skipped, THEN THE test result SHALL NOT be reported as success and the report SHALL state the skip reason, the required environment, and the residual risk. [Verification: A]
4. WHERE an Acceptance Criterion is classified as Verification: C, THE test suite SHALL treat that criterion as pending real-AWS verification and SHALL NOT count it toward this phase's Definition of Done. [Verification: A]

### Requirement 33: スコープ境界と完了条件（Definition of Done）

**User Story:** As a stakeholder, I want the feature scope and completion criteria enforced, so that the deliverable is accurate about what was and was not verified.

#### Acceptance Criteria

1. THE Feature SHALL NOT perform any real AWS operation (terraform apply, AWS CLI, kubectl, docker build/push, deploy script `--execute`). [Verification: A]
2. THE Feature's Definition of Done SHALL comprise only Verification: A criteria and the mock/LocalStack portion of Verification: B criteria, and SHALL NOT require any Verification: C criterion (e.g., EKS Running, CloudFront HTTP response, real SQS delivery, real DB migration completion) as a completion condition. [Verification: A]
3. WHERE all P0 items are resolved at the static/mock verification level, THE Feature SHALL report zero remaining P0 items. [Verification: A]
4. WHERE any P1 item remains, THE Feature SHALL leave only P1 items that the stakeholder has accepted in writing. [Verification: A]
5. THE region SHALL be `ap-northeast-1` for all resources except the CLOUDFRONT-scope WAF, which SHALL use the us-east-1 aliased provider. [Verification: A]
6. WHEN the Feature reports completion, THE completion statement SHALL state "statically verified; real AWS plan, apply, and E2E are not performed" and SHALL NOT assert "AWS build is possible". [Verification: A]
7. WHERE Verification: C criteria remain, THE completion report SHALL list them as pending real-AWS verification to be performed after explicit Operator approval. [Verification: A]

### Requirement 34: Security Hub CRITICAL Finding のポータル連携

**User Story:** As an Operator, I want CRITICAL Security Hub findings reflected in the authenticated status portal, so that viewers can confirm the most urgent security detections without accessing Product_A directly.

#### Acceptance Criteria

1. WHEN Security Hub publishes a `Security Hub Findings - Imported` event containing a Finding whose `Severity.Label` is `CRITICAL`, THE EventBridge configuration SHALL deliver that event to the finding queue. [Verification: A for event-pattern/static test; C for real Security Hub delivery]
2. THE Worker_Finding SHALL parse native AWS Security Finding Format events containing one or more findings, and SHALL register every finding in Product_A Aurora using the existing idempotent finding/triage path. [Verification: A]
3. THE Worker_Finding SHALL write only findings assessed as `critical` to Product_B `public_status_items`, using a deterministic `status_id`; non-critical findings SHALL NOT be written to Product_B. [Verification: A; C for real DynamoDB write]
4. THE Worker_Finding IRSA role SHALL grant only `dynamodb:PutItem` on the `public_status_items` table for this projection and SHALL NOT grant Product_B read permission or access to another Product_B table. [Verification: A]
5. THE status portal SHALL display the CRITICAL finding title and state in the existing list and SHALL display its severity and resource type in the detail view. [Verification: A for frontend static test; C for live CloudFront view]
6. THE integration SHALL remain Product_A-to-Product_B only; no Product_B component SHALL receive permission or code to read Product_A Aurora, queues, or worker APIs. [Verification: A]
7. IF the Product_B PutItem fails, THEN THE SQS message SHALL NOT be deleted, allowing the existing visibility-timeout and DLQ policy to retry it. [Verification: A]

## Traceability（阻害要因マッピング）

The following table maps each obstruction item (B-001〜B-034) recorded in the「05_阻害要因」sheet to the Requirement number and the Acceptance Criteria numbers that address it. All 34 items map to at least one Requirement; no item is left unmapped, duplicated, or misnumbered.

| 阻害要因 | Priority | Requirement | Acceptance Criteria |
| --- | --- | --- | --- |
| B-001 | P0 | Requirement 1 | 1, 2, 3, 4, 5, 6, 7, 8 |
| B-002 | P0 | Requirement 2 | 1, 2, 3, 4, 7, 8, 9, 10 |
| B-003 | P0 | Requirement 3 | 1, 2, 3 |
| B-004 | P0 | Requirement 3 | 4, 5, 6 |
| B-005 | P0 | Requirement 4 | 1, 2, 3, 4, 5 |
| B-006 | P0 | Requirement 5 | 1, 2, 3, 4, 5 |
| B-007 | P0 | Requirement 6 | 1, 2, 3, 4, 5, 6, 7 |
| B-008 | P0 | Requirement 7 | 1, 2, 3 |
| B-009 | P0 | Requirement 8 | 1, 2, 3, 4, 5 |
| B-010 | P0 | Requirement 10 | 1, 2, 3, 4, 5, 6 |
| B-011 | P0 | Requirement 11 | 1, 2, 3, 4 |
| B-012 | P0 | Requirement 12 | 1, 2, 3, 4 |
| B-013 | P0 | Requirement 13 | 1, 2, 3, 4, 6, 7 |
| B-014 | P0 | Requirement 14 | 1, 2, 3, 4 |
| B-015 | P0 | Requirement 15 | 1, 2, 3 |
| B-016 | P0 | Requirement 16 | 1, 3, 4 |
| B-017 | P0 | Requirement 17 | 1, 2 |
| B-018 | P0 | Requirement 16, Requirement 18 | Requirement 16: 2, 3, 4; Requirement 18: 1, 2 |
| B-019 | P0 | Requirement 23 | 1, 2, 3 |
| B-020 | P0 | Requirement 24 | 1, 2 |
| B-021 | P0 | Requirement 25 | 1, 2, 3 |
| B-022 | P0 | Requirement 26 | 1, 2, 3, 4, 5 |
| B-023 | P0 | Requirement 20 | 1, 2 |
| B-024 | P0 | Requirement 20 | 3, 4 |
| B-025 | P1 | Requirement 20 | 5 |
| B-026 | P1 | Requirement 19 | 1, 2, 3 |
| B-027 | P1 | Requirement 13 | 1, 2, 3, 4, 5 |
| B-028 | P1 | Requirement 9 | 1, 2 |
| B-029 | P1 | Requirement 21 | 1, 2 |
| B-030 | P1 | Requirement 22 | 1, 2, 3, 4 |
| B-031 | P1 | Requirement 28 | 1, 2, 3 |
| B-032 | P1 | Requirement 2 | 4, 5, 6, 8, 10 |
| B-033 | P1 | Requirement 27 | 1, 2, 3, 4 |
| B-034 | P2 | Requirement 31 | 1, 2, 3 |

Coverage check: 24 P0 items (B-001〜B-024) + 9 P1 items (B-025, B-026, B-027, B-028, B-029, B-030, B-031, B-032, B-033) + 1 P2 item (B-034) = 34 total. Requirements 29, 30, 32, and 33 are cross-cutting (Two_Phase_Build sequencing, deploy-script safety, test-suite composition, and scope/Definition-of-Done) and reinforce multiple obstruction items rather than mapping to a single one.

## Verification Classification

Each Requirement is classified by whether all of its Acceptance Criteria are verifiable locally/in CI (categories A/B) or whether it contains at least one criterion that can only be confirmed against real AWS (category C). Category C criteria are pending real-AWS verification after explicit Operator approval and are not part of this phase's Definition of Done.

| Requirement | 分類 | 備考 |
| --- | --- | --- |
| Requirement 1: dev root への全モジュール配線 | A/B のみ | All criteria are static (fmt / validate / reference resolution). |
| Requirement 2: IAM ロールと最小権限 | A/B のみ | Static IAM policy tests, including Wildcard_Exception_Registry membership. |
| Requirement 3: Backend DB シークレット注入 | A/B のみ | Config-resolution unit test with fixture payloads. |
| Requirement 4: Backend 内部 Bearer トークン | A/B のみ | Auth unit tests against the injected token. |
| Requirement 5: DB マイグレーション実行手段 | C を含む | Real Aurora migration run is category C; the Category A schema test is Docker-independent (SQL static parse or in-memory/file fixture); a testcontainers-based check is Category C / optional. |
| Requirement 6: メッセージング分離 | C を含む | Idempotency is A; real EventBridge/SQS routing and max-receive behavior are B/C. |
| Requirement 7: EKS マニフェストレンダリングと Placeholder 検査 | A/B のみ | Render-and-scan runs locally. |
| Requirement 8: ECR リポジトリと EKS ワークロード別イメージ | C を含む | Manifest/repository checks are A; workload Running/pull outcome is C. |
| Requirement 9: Docker アーキテクチャ整合 | C を含む | Script static check is A; real image inspect is C. |
| Requirement 10: Product_A→Product_B 連携 | C を含む | Idempotency/permission tests are A/B; real S3/DynamoDB write is C. |
| Requirement 11: Lambda 再現可能パッケージ | C を含む | Reproducible-hash test and S3-reference wiring are A; real package upload and invoke smoke check are C. |
| Requirement 12: Cognito 設定 | A/B のみ | Configuration and validation static checks. |
| Requirement 13: Frontend 認証フロー | C を含む | Callback/state/PKCE/storage/placeholder are A; live 4-API sign-in is C. |
| Requirement 14: API Gateway と CloudFront パス整合 | C を含む | Route/behavior config is A; live /api HTTP 200/401 is C. |
| Requirement 15: S3/CloudFront 循環依存の解消 | C を含む | Graph cycle-free check is A; real `terraform plan` is B/C. |
| Requirement 16: S3 バケット命名の一意化 | C を含む | Naming-expression checks are A; real plan output is C. |
| Requirement 17: CloudFront 用 WAF の us-east-1 provider | C を含む | Provider-alias wiring is A; real plan output is C. |
| Requirement 18: ALB アクセスログとポリシー | C を含む | Access-logging config is A; real plan output is C. |
| Requirement 19: ALB TLS と HTTP リダイレクト | C を含む | Listener redirect config is A; live HTTP redirect is C. |
| Requirement 20: EKS バージョン、アクセス、公開範囲 | C を含む | Version/CIDR/access-entry config is A; `kubectl auth can-i` is C. |
| Requirement 21: VPC Flow Logs | C を含む | Flow-log resource wiring is A; real log-stream entries are C. |
| Requirement 22: Monitoring 配線と通知 | C を含む | Alarm/SNS config is A; real alarm-state/notification is C. |
| Requirement 23: Terraform backend の再現性 | C を含む | backend.tf static check is A; real plan/apply is C. |
| Requirement 24: CodeBuild Terraform バージョン固定 | C を含む | Buildspec static check is A; real pipeline run is C. |
| Requirement 25: Plan artifact と provider lock | C を含む | Buildspec/artifact and lock file are A; real apply-approved-plan is C. |
| Requirement 26: Pipeline 入力の明示供給 | C を含む | Input-supply config is A; real plan summary match is C. |
| Requirement 27: シークレット衛生 | A/B のみ | Git-tracking and transcription static checks. |
| Requirement 28: CI で Terraform 静的検証 | A/B のみ | CI runs static checks only. |
| Requirement 29: 二段階構築手順 | A/B のみ | Module input and documentation checks. |
| Requirement 30: Deploy スクリプトの dry-run 既定と安全性 | A/B のみ | Script static and snapshot tests. |
| Requirement 31: ドキュメント整合 | A/B のみ | Docs-consistency test. |
| Requirement 32: 必須静的・単体テストスイート | A/B のみ | Composition of the local/CI test suite. |
| Requirement 33: スコープ境界と完了条件 | A/B のみ | Scope and Definition-of-Done enforcement (no real AWS operation). |
| Requirement 34: Security Hub CRITICAL Finding のポータル連携 | C を含む | Event pattern/parser/IAM/frontend are A; real Security Hub→EventBridge→SQS→EKS→DynamoDB→CloudFront is C. |
