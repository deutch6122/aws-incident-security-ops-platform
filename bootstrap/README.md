# bootstrap（ローカル初回のみ）

パイプラインを作るための state / 権限をパイプライン自身で作れない「鶏卵問題」を回避するため、**初回のみローカルから apply する土台リソース群（Bootstrap_Stack）** を定義する。

対応要件: Req 20.3, 20.4, 21.1, 21.2, 21.3, 21.4, 21.5, 23.1, 23.2, 23.3, 17.2, 19.1〜19.3

関連ドキュメント:
- [terraform-backend-design.md](../docs/architecture/terraform-backend-design.md)（backend / state lock）
- [deployment-design.md](../docs/operation/deployment-design.md)（3 層分離）
- [cicd-design.md](../docs/operation/cicd-design.md)（Infra_Pipeline）

## 作成されるリソース

| 種別 | リソース | 概要 |
| --- | --- | --- |
| remote state | `ops-platform-dev-tfstate-<account_id>`（S3） | バージョニング / SSE(AES256) / public access block 全有効 |
| state lock（第一候補） | S3 backend `use_lockfile = true` | S3 ネイティブロック。Terraform v1.10+ 前提。専用リソース不要 |
| state lock（代替案 / 任意） | `ops-platform-dev-tfstate-lock`（DynamoDB） | `enable_dynamodb_lock=true` のときのみ作成（default=false） |
| CI/CD artifact | `ops-platform-dev-cicd-artifacts-<account_id>`（S3） | バージョニング / SSE / public access block 全有効 |
| CI/CD | `ops-platform-dev-terraform-build`（CodeBuild） | Terraform 実行（小さめコンピュート BUILD_GENERAL1_SMALL） |
| CI/CD | `ops-platform-dev-infra-pipeline`（CodePipeline） | Source→Fmt→Validate→Plan→手動承認→Apply |
| IAM | `ops-platform-dev-terraform-exec-role` | Terraform 実行用（最小権限を意識、Administrator 不使用） |
| IAM | `ops-platform-dev-codebuild-role` / `-codepipeline-role` | 各サービスロール |

## ファイル構成

```
bootstrap/
  versions.tf              # required_version >= 1.10, required_providers, backend 例（コメント）
  providers.tf             # region=ap-northeast-1, default_tags=共通タグ
  variables.tf             # project/env/enable_dynamodb_lock(default=false)/source 設定
  locals.tf                # 命名 helper(name_prefix=ops-platform-dev) / 共通タグ / バケット名
  state.tf                 # remote state S3 + （任意）DynamoDB lock table
  cicd.tf                  # artifact S3 / CodeBuild / CodePipeline（ステージ定義）
  iam.tf                   # terraform-exec-role + codebuild/codepipeline サービスロール
  outputs.tf               # state/artifact/pipeline/role の output
  terraform.tfvars.example # 変数の記入例
  buildspec/
    buildspec.yml          # STAGE(fmt/validate/plan/apply) で分岐するディスパッチャ
    buildspec-fmt.yml      # 個別: terraform fmt -check
    buildspec-validate.yml # 個別: terraform init & validate
    buildspec-plan.yml     # 個別: terraform plan（一覧 + コスト影響大リソース明示）
    buildspec-apply.yml    # 個別: 承認後の terraform apply
  tests/                   # 静的構成テスト（pytest、terraform/AWS 不要） … tests/README.md 参照
```

infra 側の backend 例: [`infra/environments/dev/backend.tf.example`](../infra/environments/dev/backend.tf.example)（`use_lockfile = true`）。

## state lock 方針（重要）

- **第一候補**: S3 backend の **`use_lockfile = true`（S3 ネイティブロック）**。Terraform **v1.10 以降**が前提（`versions.tf` の `required_version >= 1.10`）。DynamoDB テーブルは不要。
- **代替案 / 任意**: 旧方式互換の **DynamoDB lock table**。`enable_dynamodb_lock=true` のときのみ作成（**デフォルトは作成しない**）。
- 背景: Req 20.3 / 21.1 は「S3 + DynamoDB lock」と記載しているが、本設計では `use_lockfile=true` を第一候補・DynamoDB を代替とする（[terraform-backend-design.md](../docs/architecture/terraform-backend-design.md)）。

## 最小権限方針（terraform-exec-role）

- **AdministratorAccess を付与しない**。`Action:"*"` + `Resource:"*"` の全許可ワイルドカードも使用しない。
- 本 Platform が作成するサービス（S3 / DynamoDB / VPC・EC2 / ECS / EKS / ECR / RDS・Aurora / SQS / EventBridge / SNS / CloudFront / WAF / Cognito / API Gateway / Lambda / IAM(必要範囲) / CloudWatch Logs・Alarms / Secrets Manager）に必要なアクションへ**サービス単位でスコープ**する。
- 可能な箇所は Resource を命名 prefix（`ops-platform-dev-*`）や account/region で制約している。
- **`Resource="*"` の方針（MVP）**: ネットワーク / ECS / EKS / ECR / RDS / SQS / EventBridge / SNS / WAF / Cognito / CloudFront / CloudWatch 等、**作成前に ARN を指定しづらい AWS サービスでは一部 `Resource="*"` を許容する**。ただしこの場合でも **Action はサービス単位に制限**しており（`Action:"*"` は使わない）、権限の広がりを抑えている。
- **本番想定での段階的制限**: `aws:RequestTag` / `aws:ResourceTag` の `Project=ops-platform` 条件を用いて `Resource="*"` の statement を段階的に絞り込む。
- **`iam:PassRole`**: `iam:PassedToService` 条件で渡す先を本 Platform が利用するサービス（`ecs-tasks` / `eks` / `eks-fargate-pods` / `lambda` / `codebuild`）に限定済み。

### CodeBuild → terraform-exec-role の AssumeRole 分離設計

- CodeBuild の `service_role` には **codebuild-role** を割り当てる。
- Terraform 実行時は codebuild-role が **`sts:AssumeRole` で terraform-exec-role を引き受け**、取得した一時クレデンシャルで `terraform` を実行する（権限分離）。
- そのため terraform-exec-role の信頼ポリシーの Principal は、`codebuild.amazonaws.com` サービスプリンシパルではなく **codebuild-role の ARN（`type = "AWS"`）** としている。
- buildspec（`buildspec.yml` / `buildspec-validate.yml` / `buildspec-plan.yml` / `buildspec-apply.yml`）では、各 Terraform 実行の前に `aws sts assume-role --role-arn "$TERRAFORM_EXEC_ROLE_ARN"` で一時クレデンシャルを取得し `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` に export する（`fmt` はローカル処理のため assume 不要）。
- Apply ステージは承認済み plan（`plan_output` の `tfplan.binary`）を Terraform コード一式（`source_output`）に適用するため、CodePipeline の Apply アクションで **両方を input_artifacts に渡し、`PrimarySource = source_output`** を設定する。buildspec 側は `CODEBUILD_SRC_DIR_plan_output` 経由で plan バイナリを参照する。

## 使い方（手順）

> **注意**: 本サブタスクではコード作成のみを行っており、`terraform apply/plan/init/validate` は実行していません。以下は運用手順の案内です。

1. 変数を用意する
   ```bash
   cd bootstrap
   cp terraform.tfvars.example terraform.tfvars
   # codestar_connection_arn / source_repository_id を設定（CodeStar Connections はコンソールで承認）
   ```
2. 初期化・確認・適用（**apply は内容確認のうえ実行**）
   ```bash
   terraform init
   terraform plan
   terraform apply   # ← 作成内容を確認してから実行
   ```
3. 出力された `state_bucket_name` を控える。
4. `infra/environments/dev/backend.tf.example` を `backend.tf` にコピーし、`bucket` を上記 state バケット名に置き換える（`use_lockfile = true`）。
5. 以降の本体インフラは **Infra_Pipeline（CodePipeline）** から適用する。ローカル端末での継続 apply は行わない（Req 21.5）。

## Infra_Pipeline（承認付き）

- **main への merge/push** で起動（Req 21.2）。
- 順序: `terraform fmt` → `validate` → `plan` → **手動承認** → `apply`（Req 21.3）。
- `plan` は作成/変更/削除予定リソース一覧と、**コスト影響が大きいリソース（Aurora / NAT / EKS / CloudFront）** を明示する（Req 23.1, 23.2）。
- **承認なしでは apply しない**（Req 21.4, 23.3）。

## 構成テスト

`bootstrap/tests/`（pytest）で、state/artifact S3 の public access block・暗号化・バージョニング、DynamoDB lock のデフォルト無効、`use_lockfile=true` の第一候補記載、`required_version >= 1.10`、terraform-exec-role の最小権限（Administrator/全許可なし）を **AWS 認証・terraform 実行なし** で検証する。詳細は [tests/README.md](tests/README.md)。

```bash
pip install -r bootstrap/tests/requirements.txt
pytest bootstrap/tests
```
