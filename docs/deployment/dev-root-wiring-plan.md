# dev root 配線計画

本ドキュメントは `infra/environments/dev` へのモジュール配線計画を記録します。Terraform apply や AWS CLI 実行は行わず、調査とドキュメント作成のみを対象とします。

---

## 1. dev root に現在配線済みの module

| Module | 配線時期 | 主要入力 | 主要出力 |
| --- | --- | --- | --- |
| **network** | Task 4 | vpc_cidr, subnet_cidrs, azs, nat_gateway など | vpc_id, subnet_ids, security_group_ids |
| **ecr** | Task 4 | image_tag_mutability, retention settings | repository_urls, arns |
| **aurora** | Task 6.1 | database_subnet_ids, db_security_group_id, secret_kms_key_id | cluster_arn, endpoint, master_user_secret_arn |

---

## 2. dev root に未配線の module

| Module | 配線時期（予定） | 未配線の理由 |
| --- | --- | --- |
| **alb** | Task 7.1 | network 出力依存、ecs への target group 接続 |
| **ecs** | Task 8.1 | network 出力、ecr image URI、alb target group、IAM role 依存 |
| **eks** | Task 10.1 | network 出力、messaging (SQS) ARN、Aurora secret ARN 依存 |
| **messaging** | Task 11 | 独立しているが eks / EKS workers への queue ARN 渡しが確定後 |
| **dynamodb** | Task 14 | 独立している、lambda への table ARN 渡しが確定後 |
| **lambda** | Task 15 | dynamodb table ARN、package artifact 依存 |
| **cognito** | Task 14.1 | 独立しているが apigateway JWT authorizer 依存 |
| **apigateway** | Task 14 | cognito issuer_url、lambda invoke ARN 依存 |
| **cloudfront** | Task 13.2/13.3 | s3-portal bucket ARN、API Gateway domain、waf acl ARN 依存 |
| **s3-portal** | Task 13.2 | OAC 保護、cloudfront への bucket ARN 渡し |
| **logging** | Task 9 | lambda log group、vpc flow logs 向け |
| **monitoring** | Task 18.2 | ecs/eks/alb/lambda/aurora/messaging の識別子依存 |

---

## 3. 未配線 module ごとの主要 input

### alb
- `vpc_id`, `public_subnet_ids`, `private_subnet_ids`
- `alb_access_logs_bucket`（既存の S3 bucket、access_logs 用）
- `ssl_certificate_arn`（ACM 証明書 ARN）
- `alb_name`, `target_port`, `health_check_path`

### ecs
- `private_subnet_ids`, `ecs_security_group_id`
- `ecs_cluster_name`（通常は network 出力や固定値）
- `ecr_repository_url`（backend-api 用）
- `task_cpu`, `task_memory`, `desired_count`
- `alb_target_group_arn`
- `db_secret_arn`（aurora 出力）
- `execution_role_arn`, `task_role_arn`（iam 出力）
- `container_image_tag`

### eks
- `vpc_id`, `private_subnet_ids`
- `cluster_name`, `cluster_version`
- `sqs_queue_arns`（messaging 出力）
- `db_secret_arn`（aurora 出力）
- `worker_role_arn`, `cronjob_role_arn`（iam 出力）

### messaging
- `name_prefix`, `common_tags`
- `eventbridge_event_pattern`
- 他の module への依存なし（独立している）

### dynamodb
- `name_prefix`, `common_tags`
- `ttl_attribute_name`
- 他の module への依存なし（独立している）

### lambda
- `runtime`, `handler`, `package_filename`
- `memory_size`, `timeout`, `log_retention_days`
- `public_status_items_table_arn`, `report_metadata_table_arn`, `maintenance_windows_table_arn`, `page_view_logs_table_arn`（dynamodb 出力）
- `lambda_log_group_name`（logging 出力）

### cognito
- `user_pool_name`, `callback_urls`, `logout_urls`
- `allowed_oauth_flows`, `supported_identity_providers`

### apigateway
- `lambda_function_arn`（lambda 出力）
- `cognito_authorizer_issuer_url`, `cognito_authorizer_audience`（cognito 出力）
- `api_name`, `stage_name`

### cloudfront
- `s3_origin_bucket_arn`, `s3_origin_bucket_regional_domain_name`（s3-portal 出力）
- `api_origin_domain`（apigateway 出力）
- `waf_web_acl_arn`（waf 出力、または cloudfront 内で作成）
- `price_class`, `default_root_object`

### s3-portal
- `cloudfront_distribution_arn`（cloudfront 出力）- **循環依存リスクあり**

### logging
- `vpc_id`, `vpc_flowlogs_group_name`（network 出力）
- `lambda_log_retention_days`

### monitoring
- `dlq_queue_name`（messaging 出力）
- `ecs_cluster_name`, `ecs_service_name`（ecs 出力）
- `alb_arn_suffix`（alb 出力）
- `aurora_db_cluster_identifier`（aurora 出力）
- `lambda_function_name`（lambda 出力）

---

## 4. 未配線 module ごとの主要 output

### alb
- `alb_arn`, `alb_dns_name`, `alb_zone_id`
- `target_group_arn`, `listener_arn`
- `security_group_id`

### ecs
- `cluster_arn`, `cluster_name`
- `service_name`, `task_definition_arn`
- `log_group_name`

### eks
- `cluster_name`, `cluster_arn`, `cluster_endpoint`
- `cluster_oidc_issuer_url`, `oidc_provider_arn`
- `fargate_profile_arn`, `worker_role_arn`, `cronjob_role_arn`
- `worker_log_group_name`

### messaging
- `queue_arn`, `queue_url`, `queue_name`
- `dlq_arn`, `dlq_url`, `dlq_name`
- `event_rule_arn`

### dynamodb
- `public_status_items_table_name`, `public_status_items_table_arn`
- `report_metadata_table_name`, `report_metadata_table_arn`
- `page_view_logs_table_name`, `page_view_logs_table_arn`
- `maintenance_windows_table_name`, `maintenance_windows_table_arn`

### lambda
- `lambda_function_name`, `lambda_function_arn`
- `lambda_invoke_arn`, `lambda_role_arn`
- `log_group_name`

### cognito
- `user_pool_id`, `user_pool_arn`
- `client_id`, `client_secret`（output には含まない場合あり）
- `issuer_url`

### apigateway
- `api_id`, `api_endpoint`, `api_execution_arn`
- `api_domain_name`
- `authorizer_id`, `stage_name`

### cloudfront
- `distribution_id`, `distribution_arn`, `distribution_domain_name`
- `oac_id`, `web_acl_arn`, `price_class`

### s3-portal
- `bucket_name`, `bucket_arn`, `bucket_regional_domain_name`
- `reports_prefix`

### logging
- `lambda_log_group_name`, `lambda_log_group_arn`
- `vpc_flowlogs_log_group_name`, `vpc_flowlogs_log_group_arn`

### monitoring
- `sns_topic_arn`, `sns_topic_name`
- `alarm_names`, `dlq_alarm_name`
- `product_a_dashboard_name`, `product_b_dashboard_name`

---

## 5. どの module output をどの module input へ渡す必要があるか

| From Module | Output | To Module | Input |
| --- | --- | --- | --- |
| network | `private_app_subnet_ids` | ecs | `private_subnet_ids` |
| network | `security_group_ids.ecs` | ecs | `ecs_security_group_id` |
| network | `isolated_db_subnet_ids` | aurora | `database_subnet_ids` |
| network | `security_group_ids.db` | aurora | `db_security_group_id` |
| ecr | `backend_api_repository_url` | ecs | `ecr_repository_url` |
| aurora | `master_user_secret_arn` | ecs, eks | `db_secret_arn` |
| network | `public_subnet_ids` | alb | `public_subnet_ids` |
| network | `vpc_id` | alb | `vpc_id` |
| alb | `target_group_arn` | ecs | `alb_target_group_arn` |
| network | `private_app_subnet_ids` | eks | `private_subnet_ids` |
| network | `vpc_id` | eks | `vpc_id` |
| messaging | `queue_arn` | eks | `sqs_queue_arns` |
| messaging | `dlq_name` | monitoring | `dlq_queue_name` |
| ecs | `cluster_name`, `service_name` | monitoring | `ecs_cluster_name`, `ecs_service_name` |
| aurora | `cluster_identifier` | monitoring | `aurora_db_cluster_identifier` |
| lambda | `lambda_function_name` | monitoring | `lambda_function_name` |
| alb | `alb_arn_suffix` | monitoring | `alb_arn_suffix` |
| dynamodb | 各 table_arn | lambda | 各 dynamodb table_arn inputs |
| lambda | `lambda_invoke_arn` | apigateway | `lambda_function_arn` |
| cognito | `issuer_url` | apigateway | `cognito_authorizer_issuer_url` |
| cognito | `user_pool_id` | apigateway | `cognito_authorizer_user_pool_id` |
| s3-portal | `bucket_arn`, `bucket_regional_domain_name` | cloudfront | `s3_origin_bucket_arn`, `s3_origin_bucket_regional_domain_name` |
| apigateway | `api_domain_name` | cloudfront | `api_origin_domain` |
| cloudfront | `distribution_arn` | s3-portal | `cloudfront_distribution_arn` |
| logging | `lambda_log_group_name` | lambda | （lambda 内で log_group を参照する場合あり） |
| apigateway | `api_endpoint` | cloudfront | `api_origin_domain` |

---

## 6. 配線順序

### Phase 1: 基盤（既に配線済み）
1. **network** → 2. **ecr** → 3. **aurora**

### Phase 2: Product_A 基盤
4. **alb** - network 依存解消後
5. **messaging** - 独立しているが先に配線しておくと eks で利用可
6. **iam** - execution/task roles を提供（ecs/eks 用）
7. **ecs** - network/ecr/alb/aurora/iam 依存解消後
8. **eks** - network/messaging/aurora/iam 依存解消後
9. **logging** - network 依存

### Phase 3: Product_B 基盤
10. **dynamodb** - 独立している
11. **cognito** - 独立している
12. **lambda** - dynamodb/logging 依存解消後
13. **apigateway** - cognito/lambda 依存解消後

### Phase 4: CDN と連携
14. **s3-portal** - cloudfront 依存（循環注意）
15. **cloudfront** - s3-portal/apigateway 依存解消後
    - ※ s3-portal と cloudfront は相互依存関係にあるため、**両方を同時に配線**するか、一方を variable で受ける設計が必要

### Phase 5: 監視
16. **monitoring** - ecs/eks/alb/aurora/lambda/messaging すべて完成後

---

## 7. 循環参照や注意点

### 循環参照リスク

#### s3-portal ↔ cloudfront
- **s3-portal** は `cloudfront_distribution_arn` を bucket policy の SourceArn 条件に渡す
- **cloudfront** は s3-portal の bucket ARN/domain を origin として使う

**解決方法**:
1. **方法A**: 両 module を同時に `terraform apply` する（s3-portal が null な cloudfront_arn を受け取り、作成後に policy 更新は不可 → 実現不可能）
2. **方法B**: s3-portal の `cloudfront_distribution_arn` を **optional** とし、初回の Terraform apply では省略して OAC 保護なしで作成、2回目の apply で cloudfront_arn を渡して policy 更新
3. **方法C**: s3-portal 内で bucket policy を conditional で記述し、cloudfront_arn が null の場合は OAC なしで作成

**推奨**: 方法B（2段階 apply）が現実的

#### logging → lambda → monitoring
- logging の出力を lambda が使うが、logging 自体は独立している
- 循環はなし

#### monitoring の依存
- monitoring は最も最後に配線（全リソースの識別子が確定後）

### その他の注意点

1. **aurora secret ARN**: ecs/eks の task/execution role に IRSA で Secrets Manager への参照権限を与えるには、secret ARN が必要
2. **ecr image URI**: ecs の task definition に image URI を渡す必要あり。App_Deploy で build/push 後の値が必要
3. **Cognito User Pool 作成前の API Gateway 配線**: cognito が未作成の状態では authorizer 設定が困難
4. **WAF Web ACL**: cloudfront 内で作成する場合、scope = CLOUDFRONT で us-east-1 が必須

---

## 8. 実AWS apply 前に決定する必要がある値

| 値 | 種類 | 決定方法 |
| --- | --- | --- |
| **AWS アカウント ID** | 必須 | 実環境のアカウント |
| **リージョン** | 必須 | `ap-northeast-1`（固定） |
| **SSL 証明書 ARN** | alb 用 | ACM で発行した証明書（または ACM を使わず http only の場合は null） |
| **CloudFront 独自ドメイン + ACM** | cloudfront 用 | MVP ではデフォルト証明書でスキップ（後続 Phase で導入） |
| **Cognito callback/logout URLs** | cognito 用 | 実際の Callback URL（開発用は localhost 可） |
| **alb_access_logs_bucket** | alb 用 | 既存の S3 bucket（access logs 用）を作成または指定 |
| **KMS key ID** | aurora secret 用 | 顧客管理 KMS key の ARN（null の場合は AWS managed key） |
| **Terraform state backend** | 必須 | S3 + DynamoDB（bootstrap で作成済み） |

---

## 9. コストが大きい module

| Module | コスト影響要因 | 推奨対応 |
| --- | --- | --- |
| **Aurora** | Serverless v2 ACU（max 2 まで） | `aurora_max_capacity = 2`、`aurora_min_capacity = 0.5` 程度に設定 |
| **NAT Gateway** | データ転送量 | `network_enable_nat_gateway = false` にすると ECR/Secrets Manager/SQS への interface endpoint が必要（コストのトレードオフあり） |
| **EKS** | Fargate vCPU/メモリ | MVP では最小構成（worker 1 Pod 程度） |
| **CloudFront** | リクエスト数 | `price_class = PriceClass_100`（日本東京のみ） |
| **WAF** | リクエスト数 | Rate-based rule で過剰なリクエストをブロック |
| **CloudWatch Logs** | ログ量 × 保持期間 | `log_retention_days = 14`（MVP） |

---

## 10. 最小構成で apply する場合の候補

MVP の最小構成で配線する場合、以下の module のみ配線することを推奨します。

### 必須（動作に必要な最小構成）
1. **network** - VPC/Subnet/SG/NAT（有無を選択）
2. **ecr** - container repository
3. **aurora** - database
4. **ecs** - Backend API 動作用
5. **alb** - API への入口

### 推奨する最小追加
6. **messaging** - SQS/EventBridge（worker 連動用）
7. **iam** - execution/task roles

### 省略可（後続 Phase で）
- **eks** - 完全な Worker 連動は後続
- **dynamodb** / **lambda** / **apigateway** / **cognito** / **cloudfront** / **s3-portal** - Product_B は後続
- **logging** / **monitoring** - MVP では無効または最小

---

## 11. 全部構成する場合の候補

完全構成（Product_A + Product_B + 監視）を目指す場合の順序です。

### Step 1: 基盤
- network → ecr → aurora

### Step 2: Product_A
- alb → iam → messaging → ecs → eks → logging

### Step 3: Product_B
- dynamodb → cognito → lambda → apigateway → s3-portal → cloudfront
  - **注意**: s3-portal と cloudfront は同時配線または2段階 apply

### Step 4: 監視
- monitoring

---

## 12. 次に Terraform コードを変更する場合の作業手順

### 手順1: 依存関係の確認
- 配線しようとする module が依存する他の module の出力が既に存在するか確認
- 循環参照リスクがないか確認

### 手順2: variables.tf の確認
- 必要となる変数が variables.tf に定義済みか確認
- 未定義の場合は variables.tf に変数を追加（tfvars で値を渡すため）

### 手順3: main.tf への module 追加
- `module "xxx"` ブロックを追加
- 各 module の source、name_prefix、common_tags を設定
- 依存 module の出力を input として渡す

### 手順4: outputs.tf の更新（必要なら）
- 新しく作成したリソースの出力を追加
- 後続 module で必要となる値を output に追加

### 手順5: terraform validate
- `terraform -chdir=infra/environments/dev validate` で構文エラーを確認
- （本タスクの制約により実際には実行しないが、概念として）

### 手順6: terraform plan で確認
- `terraform plan` で作成/変更/削除予定のリソースを確認
- コスト影響が大きいリソース（Aurora/NAT/EKS/CloudFront）を特に注意
- （本タスクの制約により実際には実行しない）

### 手順7: ユーザーの確認と承認
- plan の結果をユーザーに報告し、承認を得た後に `terraform apply` を実行

---

## 付録: module wiring 依存図

```
network ──┬──► alb ──► ecs ──► monitoring
           │       │
           │       └──► eks ──► monitoring
           │
           ├──► aurora ──► ecs ──► monitoring
           │            │
           │            └──► eks ──► monitoring
           │
           ├──► messaging ──► eks ──► monitoring
           │
           └──► logging ──► lambda ──► apigateway ──► cloudfront
                                    │                ▲
                                    ▼                │
                             dynamodb ◄──────────────┘
                                    ▲
                                    │
cognito ──► apigateway ──► cloudfront ◄── s3-portal
                              │                ▲
                              └────────────────┘
                                    (循環: 同時配線または2段階 apply)
```

---

このドキュメントは配線作業の参考として使用してください。実際の Terraform apply は plan で確認したうえで、ユーザーの承認後に行ってください。
