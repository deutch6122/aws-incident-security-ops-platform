# dev Terraform root

infra/environments/dev は AWS Incident & Security Operations Platform のdev完全構成を配線するTerraform rootです。実AWS固有値やSecretを追跡ファイルへ保存しません。

## 配線済み構成

network、ecr、aurora、alb、ecs、eks、messaging、logging、dynamodb、s3-portal、cloudfront、cognito、apigateway、lambda、monitoring、iam、wafの全17 moduleを配線済みです。

- default AWS provider: ap-northeast-1
- CloudFront scope WAF: rootのaws.us_east_1をmoduleへprovider mapping
- iam→ecs: IAM側がlog group ARNをpartition/region/account/nameから組み立て、循環を回避
- s3-portal→cloudfront→root bucket policy: OAC policyをrootが所有して循環を回避
- iam/ecs→root migration-launcher policy: role本体とRunTask対象の循環を回避
- Product_A→Product_B: monthly-summary-cronjobだけがS3/DynamoDBへ一方向書込

## 主なファイル

| ファイル | 内容 |
| --- | --- |
| versions.tf | TerraformとAWS/random provider制約 |
| providers.tf | ap-northeast-1とus-east-1 alias |
| backend.tf | bucket名を含まないpartial S3 backend、use_lockfile=true |
| variables.tf | 全module入力、二段階ECS、Cognito、WAF、Monitoring |
| locals.tf | 命名、共通tag、5 ECR image URI |
| main.tf | 17 moduleとroot glue policyの配線 |
| outputs.tf | deploy/運用用の非機微output |
| .terraform.lock.hcl | provider lock |
| tests/ | root contract、命名、pipeline、静的検証 |

## 入力経路

- 非機微の既定値: variables.tf
- 環境固有の非機微値: SSM Parameter StoreからCodeBuildがTF_VARへ供給
- DB credentialと内部Bearer token: Secrets Manager。値はoutputしない
- Lambda package: bootstrap artifact S3のbucket/key/version/source_code_hash
- backend bucket: Bootstrap outputをCodeBuildの-backend-configでinit時だけ供給

必要な値、取得元、設定箇所は docs/operation/aws-resource-parameter-sheet.xlsx、実行順序は docs/operation/aws-build-procedure.md を正とします。

## Two Phase Build

1. SSM ecs-desired-count=0、対象commitのapplication-image-tagでPipeline planを作成し、承認後applyする。
2. Backend、worker 3種、db-migrationの計5 imageをlinux/amd64でpushする。
3. private subnetのone-off Fargate taskでmigrationを実行し、exitCode=0を確認する。
4. SSM ecs-desired-count=1へ変更し、新しいplanを承認してapplyする。
5. EKS logging prerequisites、workload、Cognito HTTPS URL、frontendを順番に配信する。

本体Terraform applyは承認付きInfra Pipelineが実行します。ローカルでの継続applyは行いません。

## Backend

backend.tfへ実bucket名を記載しません。Bootstrap output state_bucket_nameは次の形でinit時だけ供給します。

~~~bash
terraform -chdir=infra/environments/dev init \
  -backend-config="bucket=＜bootstrap-state-bucket＞"
~~~

S3 native lockを第一候補とし、DynamoDB lockは互換用途の任意構成です。state、tfvars、credential、SecretをGitへ追加しません。

## コストと実行前確認

Aurora Serverless v2、NAT Gateway、EKS、CloudFront、WAF、CloudWatch Logs、S3/ECR保持は継続課金対象です。apply直前にEKS versionがStandard Support内であることを再確認し、Extended Supportを前提にしません。Auroraのdeletion protection、skip final snapshot、保持期間、各force_destroyをplanで個別確認します。

## 検証状態

リポジトリ内のfmt/validate/static/unit/mockと実AWS plan/applyは別です。Category Cを未実施の場合は「静的検証済み・実行環境検証保留」と報告します。
