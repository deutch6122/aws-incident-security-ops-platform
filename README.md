# AWS Incident & Security Operations Platform

![CI](https://github.com/deutch6122/aws-incident-security-ops-platform/actions/workflows/ci.yml/badge.svg)

社内運用向け内部基盤（**Product_A**）と関係者向け公開ポータル（**Product_B**）を、AWS 上に疎結合で構築するポートフォリオ兼実務想定の成果物です。両者は単一システムへ統合せず、**A→B の一方向・非同期連携のみ**を許容します。

- **Product_A（内部運用・処理基盤）**: ECS Fargate による同期 API（Backend_API / FastAPI）、EKS による非同期ワーカー・CronJob（Worker_Alarm / Worker_Finding / Cronjob_Summary）、Aurora PostgreSQL による永続化。Operator がインシデント・アラーム・セキュリティ Finding・対応履歴・月次集計を管理します。
- **Product_B（公開・配信ポータル）**: CloudFront + S3(OAC) + WAF + Cognito + API Gateway + Lambda + DynamoDB。Viewer が障害ステータス・メンテナンス情報・月次レポートを閲覧します。
- **A→B 連携**: Cronjob_Summary が月次レポートを Portal_Storage(S3 `reports/*`) へ配置し、メタ情報を `report_metadata`、公開ステータスを `public_status_items`（DynamoDB）へ反映します。Product_B から Product_A への書き込みは行いません。

対象は **dev 環境の MVP** です。リージョンは `ap-northeast-1`、命名規則は `ops-platform-dev-<resource>`。

---

## ポートフォリオ資料

面接・案件担当者向けに、以下の資料を用意しています。

| ドキュメント | 内容 |
| --- | --- |
| [docs/portfolio/overview.md](docs/portfolio/overview.md) | プロジェクト概要、ユースケース、AWSサービス一覧 |
| [docs/portfolio/architecture-explanation.md](docs/portfolio/architecture-explanation.md) | アーキテクチャ詳細、各コンポーネントの説明 |
| [docs/portfolio/demo-talk-track.md](docs/portfolio/demo-talk-track.md) | 30秒/1分/3分説明台本、GitHubの見せ順 |
| [docs/portfolio/interview-q-and-a.md](docs/portfolio/interview-q-and-a.md) | 想定質問と回答例（14項目） |
| [docs/portfolio/career-summary.md](docs/portfolio/career-summary.md) | 職務経歴書転用文、実績文、技術一覧 |

---

## ディレクトリ構成

```
.
├─ infra/
│  ├─ environments/dev/     # dev 環境の Terraform ルート（backend/provider/共通変数/命名helper）
│  └─ modules/              # 再利用可能な Terraform モジュール群
│     ├─ network/           # VPC/Subnet/SG/NAT/IGW/VPCエンドポイント
│     ├─ ecr/               # ECR リポジトリ
│     ├─ alb/               # ALB / Target Group / リスナー
│     ├─ ecs/               # ECS cluster / task / service
│     ├─ eks/               # EKS / Fargate Profile / IRSA
│     ├─ aurora/            # Aurora Serverless v2 (PostgreSQL)
│     ├─ messaging/         # SQS + DLQ + EventBridge
│     ├─ s3-portal/         # Portal_Storage (OAC 保護)
│     ├─ cloudfront/        # CloudFront + OAC + WAF
│     ├─ waf/               # WAF Web ACL（cloudfront と統合可）
│     ├─ cognito/           # Cognito User Pool / App Client
│     ├─ apigateway/        # API Gateway (Cognito JWT Authorizer)
│     ├─ lambda/            # Portal_API Lambda
│     ├─ dynamodb/          # Portal_DB 4テーブル
│     ├─ logging/           # CloudWatch Logs グループ
│     ├─ monitoring/        # CloudWatch Alarm / Dashboard / SNS
│     └─ iam/               # 最小権限 IAM ロール群
├─ apps/
│  ├─ backend-api/          # ECS Backend_API (FastAPI, Python) + app/ + Dockerfile
│  ├─ eks-workers/          # EKS ワーカー3種 + k8s manifest
│  │  ├─ alarm-event-processor/
│  │  ├─ security-finding-worker/
│  │  ├─ monthly-summary-cronjob/
│  │  └─ k8s/
│  ├─ portal-frontend/      # Product_B 静的フロント (src/, public/)
│  └─ portal-lambda/        # Product_B Portal_API (Lambda, Python)
├─ docs/                    # 設計・運用ドキュメント（architecture/db/api/operation/security/runbook）
├─ bootstrap/               # 初回のみローカル apply する土台（state/pipeline/exec-role）
├─ scripts/                 # デプロイ・サンプルデータ投入スクリプト
└─ .gitignore
```

---

## 構築手順（Bootstrap → Infra_Pipeline → App_Deploy → Sample Data → Monitoring）

インフラは 3 層に分離しています。**実際の `terraform apply` / デプロイは、変更内容（plan）をユーザーが確認・承認した後にのみ実行してください。** 本 README のコマンドは手順を示すものであり、承認前の自動 apply は行いません。

### 1. Bootstrap（ローカル初回のみ）

パイプライン自身を作るための「鶏卵問題」を回避するため、remote state / CI/CD 土台 / 実行用 IAM Role を初回だけローカルから作成します。

```bash
# bootstrap/ で（内容確認後、ユーザー承認のうえで）
terraform -chdir=bootstrap init
terraform -chdir=bootstrap plan     # 作成予定リソースを必ず確認
terraform -chdir=bootstrap apply    # ← 承認後にのみ実行
```

作成物: remote state 用 S3（バージョニング/暗号化/public access block）、state lock（`use_lockfile=true` を第一候補、DynamoDB lock は代替案）、CodePipeline / CodeBuild、artifact 用 S3、terraform-exec-role。

### 2. Infra_Pipeline（本体インフラ / CodePipeline + CodeBuild）

main への merge/push でパイプラインが起動し、次の順で実行します。

```
terraform fmt → terraform validate → terraform plan → 手動承認 → terraform apply
```

- `terraform plan` で作成/変更/削除予定リソースと、**コスト影響が大きいリソース（Aurora / NAT / EKS / CloudFront）** を明示します。
- **手動承認が無い限り `terraform apply` は実行しません**。ローカル端末からの継続 apply は行いません。

### 3. App_Deploy（インフラ apply と分離）

アプリのデプロイはインフラ apply から分離しています（Req 22.1）。3 スクリプトはいずれも**既定 dry-run（print-only）**で、実コマンド（docker / aws / kubectl）は `--execute` を明示したときのみ実行します。必須値はすべて環境変数で渡し、実 ARN・実アカウント ID・実ドメイン・実 Secret は埋め込みません。App_Deploy は terraform を呼びません。

```bash
# ECS: docker build → ECR push → ECS service update（force new deployment, Req 22.2）
AWS_REGION=ap-northeast-1 AWS_ACCOUNT_ID=<account-id> \
  ECR_REPO=ops-platform-dev-backend-api \
  ECS_CLUSTER=ops-platform-dev-cluster \
  ECS_SERVICE=ops-platform-dev-backend-api \
  scripts/deploy-ecs.sh --tag v1            # dry-run（既定）。実行は末尾に --execute

# EKS: docker build → ECR push → kubectl apply（Req 22.3）
AWS_REGION=ap-northeast-1 AWS_ACCOUNT_ID=<account-id> \
  ECR_REPO=ops-platform-dev-eks-workers \
  EKS_CLUSTER=ops-platform-dev-eks \
  scripts/deploy-eks.sh --tag v1            # dry-run（既定）。実行は末尾に --execute

# Frontend: 静的ファイル確認 → S3 sync → CloudFront invalidation（Req 22.4）
AWS_REGION=ap-northeast-1 \
  S3_BUCKET=ops-platform-dev-portal-REPLACE_WITH_SUFFIX \
  CLOUDFRONT_DISTRIBUTION_ID=REPLACE_WITH_DISTRIBUTION_ID \
  scripts/deploy-frontend.sh                # dry-run（既定）。実行は末尾に --execute
```

各スクリプトは `--help` / `-h` で使い方と必須環境変数を表示します。必須環境変数が未設定なら明確なエラーで終了します。

### 4. Sample Data（サンプルデータ投入）

dev/MVP の非機微・ダミーデータを投入します（Task 18.1）。これも既定 dry-run、実投入は `--execute`。

```bash
python3 scripts/seed_alarm_events.py --execute            # アラーム風イベント（EventBridge→SQS）
python3 scripts/seed_finding_events.py --execute --count 5 # Finding 風イベント
python3 scripts/seed_portal_reports.py --execute \        # Product_B へ非機微レポート/ステータス
  --report-metadata-table ops-platform-dev-report-metadata \
  --public-status-table  ops-platform-dev-public-status-items \
  --reports-bucket       ops-platform-dev-portal-REPLACE_WITH_SUFFIX
```

投入後は Worker 取込 → Backend_API 確認 → 月次集計 → A→B 連携 → Status Portal 閲覧の順で確認できます（[docs/operation/operation.md](docs/operation/operation.md) のデモシナリオ参照）。

### 5. Monitoring（監視の確認）

`infra/modules/monitoring` の CloudWatch Alarm（SQS DLQ>0 / ECS CPU・Mem・タスク数 / ALB 5xx・レイテンシ / Lambda Errors・Throttles・Duration / Aurora ACU・接続数）、Product_A / Product_B を分けた 2 ダッシュボード、SNS 通知を確認します。障害時の一次対応は [docs/runbook/runbook.md](docs/runbook/runbook.md) を参照してください。

---

## 削除（撤去）手順

不要なリソースを削除してコストを止められます。**依存関係の逆順**で撤去してください。撤去も破壊的操作のため、ユーザー承認後にのみ実行します。

> **本タスクでは `terraform destroy` を実行しません。** 下記は撤去を行う際の手順・注意です。実施時は plan（`-destroy`）で削除対象を確認し、ユーザー承認後にのみ destroy してください。削除・停止前の確認は [docs/runbook/runbook.md](docs/runbook/runbook.md#削除停止前の確認) を参照。

1. **App レイヤの停止**（App_Deploy スクリプトではなく停止操作で行う）
   - ECS service の desired_count を 0 に、または service 削除。
   - EKS の Deployment / CronJob を削除（`kubectl delete -f apps/eks-workers/k8s/`）。
   - CloudFront ディストリビューションを無効化。
2. **CloudFront / S3 の注意**
   - CloudFront は無効化 → デプロイ完了後に削除（削除は時間がかかる）。OAC / WAF Web ACL の関連付け解除も確認。
   - Portal_Storage（静的サイト / `reports/*`）の S3 オブジェクトは `terraform destroy` 前に空にする必要があります。
3. **ECR image の削除**
   - `ops-platform-dev-backend-api` / `ops-platform-dev-eks-workers` のイメージを削除（リポジトリを空にしてから撤去）。
4. **DynamoDB / S3 データの削除**
   - DynamoDB 4 テーブル（public_status_items / report_metadata / page_view_logs / maintenance_windows）のデータ要否を確認。
   - artifact / その他 S3 バケットのオブジェクトを削除。
5. **Aurora のスナップショット・final snapshot**
   - 削除前に必要ならスナップショットを取得。削除時は `final snapshot` の要否（`skip_final_snapshot` / `final_snapshot_identifier`）を判断してから撤去。
6. **本体インフラの撤去（terraform destroy は本タスクでは実行しない）**
   ```bash
   terraform -chdir=infra/environments/dev plan -destroy   # 削除対象を確認（本タスクではここまで）
   terraform -chdir=infra/environments/dev destroy          # ← 実施時は承認後にのみ実行
   ```
   - コスト影響が大きい **Aurora / NAT Gateway / EKS / CloudFront** が削除対象に含まれることを確認します。
7. **Bootstrap の手動削除（最後）**
   - remote state / CI/CD 土台は最後に撤去します。state 用 S3 と artifact S3 のオブジェクトを空にしてから削除。
   - DynamoDB lock table を使っている場合は併せて削除。
8. **残存確認**
   - CloudWatch Logs グループ、Secrets Manager シークレット、WAF Web ACL 等の取り残しがないか確認します。

---

## 注意点

- **dev 環境限定**: 本構成は dev 環境の MVP です。prod / staging は対象外です（Req 24.1）。
- **ALB 公開範囲**: Product_A は社内運用基盤です。デモ用に public ALB とする場合でも、**許可 CIDR 限定を強く推奨**します（`sg-alb` の `0.0.0.0/0` はデモ用と明記）。本番想定では **internal ALB もしくは許可 CIDR 限定**とします（Req 15.1）。
- **コスト影響が大きいリソース**: **Aurora / NAT Gateway / EKS / CloudFront・WAF / CloudWatch Logs retention** はコスト影響が大きいため、`terraform plan` で明示し、不要時は上記撤去手順で停止してください（Req 23.2, 24）。代替案（Aurora→RDS t4g.micro、NAT→VPC エンドポイント、CloudFront→PriceClass_100）を設計文書に記載しています。Logs は保持期間 14〜30 日で構成しています。
- **シークレットをコードに直書きしない**: DB パスワード等は Secrets Manager で管理し、ソースコード / IaC / 環境変数へ平文で含めません（Req 16.1/16.2）。`.env` / `*.pem` / `credentials` 等は `.gitignore` で除外済み（Req 16.3）。
- **承認前の terraform apply 禁止**: 本体インフラの作成・更新は Infra_Pipeline の**手動承認後**にのみ実行します。ローカルからの継続 apply は行いません（Req 21.4, 21.5, 23.3）。
- **レポートファイルは MVP ではダミー/非機微のみ**: 機微レポートは後続 Phase で署名付きアクセス（CloudFront signed URL/cookie または API 経由の S3 pre-signed URL）を導入します。
- **Product_A / Product_B の分離と A→B 一方向**: 両者は単一システムへ統合せず、連携は **A→B の一方向・非同期のみ**（実行主体は `monthly-summary-cronjob` に限定）。**Product_B → Product_A への書き込み・参照は設計上排除**しています（Req 14.3 / 非スコープ）。
- **App_Deploy は dry-run 既定**: `scripts/deploy-*.sh` と `scripts/seed_*.py` は既定 dry-run（print-only）。実コマンド（docker / aws / kubectl / s3 sync / invalidation）は `--execute` 明示時のみ実行し、App_Deploy から terraform は呼びません。

---

## dev ルート未配線モジュールと後続配線事項

`infra/environments/dev` ルートは現状 **network / ecr / aurora** のみを配線しています。以下のモジュールは実装済み（`infra/modules/*`）ですが、オリジン間の依存値（ARN / issuer / domain 等）が確定していないため **意図的に dev ルートへ未配線**です。各 module の README に後続配線の依存を明記しています。

| 未配線 module | 後続配線で渡す主な値 |
| --- | --- |
| `alb` / `ecs` / `eks` | network（VPC/Subnet/SG）、ecr（image URI）、aurora（Secrets Manager ARN） |
| `messaging` / `logging` | SQS/DLQ ARN、EventBridge target、Logs group 参照 |
| `dynamodb` | テーブル ARN → `lambda` の読取/書込ポリシー |
| `s3-portal` | `cloudfront` の distribution ARN → OAC 許可 bucket policy |
| `cloudfront` | s3-portal の regional domain（S3 オリジン）、apigateway の domain（API オリジン）、WAF（us-east-1 provider alias） |
| `cognito` | issuer_url / app_client_id → `apigateway` の JWT Authorizer |
| `apigateway` | lambda invoke ARN / function name、CloudFront ルーティング |
| `lambda` | dynamodb テーブル ARN、CloudWatch Logs |
| `monitoring` | 各リソース（SQS/ECS/ALB/Lambda/Aurora）の識別子 → Alarm dimensions |

後続 Phase で上記の実配線（各 module の出力 → 依存 module の入力）を dev ルートに追加します。本タスクでは Terraform module の新規実装・変更・dev ルート配線は行いません。

## ドキュメント

| ドキュメント | 内容 |
| --- | --- |
| [docs/architecture/architecture-overview.md](docs/architecture/architecture-overview.md) | 全体アーキテクチャ、ECS/EKS/CloudFront を分ける理由、A→B 連携 |
| [docs/db/db-design.md](docs/db/db-design.md) | Aurora 7テーブル / DynamoDB 4テーブル、TTL/GSI 設計理由 |
| [docs/api/api-design.md](docs/api/api-design.md) | Product_A / Product_B の API 一覧 |
| [docs/operation/operation.md](docs/operation/operation.md) | 運用手順、デプロイ設計、監視、デモシナリオ |
| [docs/security/security.md](docs/security/security.md) | OAC/WAF/Cognito JWT/Secrets Manager/最小権限 IAM/ALB 公開範囲 |
| [docs/runbook/runbook.md](docs/runbook/runbook.md) | 障害時対応、DLQ 運用、撤去手順 |

補足設計ドキュメント: [terraform-structure](docs/architecture/terraform-structure.md) / [terraform-backend-design](docs/architecture/terraform-backend-design.md) / [deployment-design](docs/operation/deployment-design.md) / [app-deployment-design](docs/operation/app-deployment-design.md) / [cicd-design](docs/operation/cicd-design.md) / [implementation-plan](docs/operation/implementation-plan.md)。

---

## CI（GitHub Actions）

`.github/workflows/ci.yml` が `main` への push / pull_request と `workflow_dispatch` で自動テストを実行します。**CI は実 AWS 操作・デプロイを一切行いません**（terraform / AWS CLI / kubectl / docker build・push / s3 sync / CloudFront invalidation を実行しない。deploy スクリプトは `bash -n` の構文チェックのみ）。

テストは **suite 別のジョブ**に分けて実行します。リポジトリ全体を単一 `pytest` プロセスで収集すると、複数ディレクトリがそれぞれ `conftest.py` / `pytest.ini` を持ち rootdir 下でモジュール名が衝突するため、Task 20 と同じく suite ごとに実行しています。

| ジョブ | 対象 | 備考 |
| --- | --- | --- |
| infra module tests | `bootstrap` / `infra/environments/dev` / `infra/modules/*` の各 tests | Terraform 非実行の静的スナップショット |
| db migration tests | `db/migrations/tests` | psycopg/testcontainers 未導入のため該当ケースは skip（Docker 不使用） |
| backend-api tests | `apps/backend-api/tests` | `requirements-test.txt` から依存導入、`compileall` 実行 |
| eks-workers tests | `apps/eks-workers/tests` | moto 未導入のため moto ケースは skip（fake ベースは実行） |
| portal-lambda tests | `apps/portal-lambda/tests` | Property 10 は fake ベースで skip せず実行 |
| portal-frontend tests | `apps/portal-frontend/tests` | 静的ファイル解析のみ |
| scripts tests + deploy syntax | `scripts/tests` + `bash -n scripts/deploy-*.sh` | deploy スクリプトは実行しない |
| static safety scan | git 管理対象 | 無視対象ファイル（`.venv`/`.env`/`.terraform`/`*.tfstate`/`*.tfvars.local`/`*.pem`/credentials 等）が追跡されていないこと、実 Secret / AWS 認証情報 / 実 ARN 相当が混入していないことを確認。`REPLACE_WITH_*` や `${var.*}`、AWS 公式ドキュメント用のダミーアカウント ID（`123456789012` 等）は許容 |

## 備考
現在の状態:
本リポジトリは、AWS Incident & Security Ops Platform の設計、Terraformモジュール、Bootstrap/CI/CD設計、アプリケーション部品を含みます。
現時点の dev 環境では network/ecr/aurora のみ配線済みで、AWS上への完全な一気通貫構築は次フェーズで対応予定です。