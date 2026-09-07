# AWS Incident & Security Ops Platform 詳細構築手順書

本書は、空の検証用 AWS アカウントから dev 完全構成を構築し、動作確認後に撤去するまでの唯一の実行順序を示す。対象リージョンは原則 ap-northeast-1、CloudFront 用 WAF のみ us-east-1 である。

> 現在の検証状態: リポジトリ内実装・静的検証まで。実 AWS の plan/apply、AWS CLI、Docker、kubectl、各 deploy script の --execute は未実施である。本書の実行は Operator が plan/dry-run を確認し、各承認ゲートで明示承認した後に行う。

## 本書の使い方

- 実行順は「手順1」から「手順14」まで固定する。途中を飛ばさない。
- 最初に aws-resource-parameter-sheet.xlsx の先頭シート「構築前の必須確認」12項目だけを確認する。01〜08シートは参照台帳であり、全行レビューや全既定値の転記は不要である。
- 既定値を変更する場合、またはplanに想定外の差分が出た場合だけ、01〜08シートの該当行を参照する。Sheet の Build手順列の番号は、本書の手順番号と一致する。
- 実 ARN、12桁アカウント ID、実ドメイン、実メール、password/token/secret 値をリポジトリ・本書・実行ログへ転記しない。
- Terraform apply は、承認済み binary plan を CodePipeline の Apply stage が実行する。本体インフラをローカルから継続 apply しない。
- dry-run と plan が失敗した場合、後続操作へ進まない。修正後に同じ手順から再実行する。

### 操作記録

各コマンド操作について、実行日時、Operator、対象アカウント別名、commit SHA、plan execution ID、承認者、結果、ログ保存先を作業記録へ残す。Secret や一時認証情報は記録しない。

### 共通プレースホルダー

| 表記 | 意味 | 正となる取得元 |
| --- | --- | --- |
| ＜account-id＞ | AWS アカウント ID | aws sts get-caller-identity の Account |
| ＜region＞ | ap-northeast-1 | Parameter Sheet 00/02 |
| ＜commit-sha＞ | デプロイ対象の完全 commit SHA | git rev-parse HEAD |
| ＜domain＞ | Operator が所有・管理する DNS 名 | Parameter Sheet 03、DNS 管理台帳 |
| ＜role-arn＞ | Operator 用 IAM role ARN | Parameter Sheet 02、組織 IAM 管理台帳 |
| ＜approved-alb-cidrs-json＞ | ALB HTTPS 許可 CIDR の JSON 配列 | Parameter Sheet 先頭シート、接続元管理台帳 |
| ＜approved-eks-cidrs-json＞ | EKS API 許可 CIDR の JSON 配列 | Parameter Sheet 先頭シート、接続元管理台帳 |

## 手順1. 前提条件・認証・リージョン・予算確認

Parameter Sheet 対応: 00_使い方・前提の「構築前の必須確認」No.1、2。

### ファイル編集

この手順でリポジトリ内ファイルは編集しない。Operator の作業記録に予算上限、停止判断者、通知先の登録済み/未登録だけを記録する。

### コマンド操作 BP-01-C01

| 項目 | 内容 |
| --- | --- |
| 目的 | ローカルツール、対象 commit、未コミット変更を確認する |
| 実行ディレクトリ | リポジトリルート |
| 前提条件 | Git、Terraform、AWS CLI、Docker、kubectl、Python 3、jq、envsubst をインストール済み |
| 正確なコマンド | 下記コードブロック |
| dry-run/plan確認 | 読み取り専用。変更は発生しない |
| 成功時の期待結果 | Terraform は .terraform-version と一致し、必要コマンドが見つかる |
| 失敗時停止条件 | バージョン不一致、コマンド不足、意図しない変更がある場合は停止 |
| 確認ログ/出力 | バージョン一覧、git status、commit SHA。認証情報は保存しない |
| rollback方法 | 変更なし |
| 次へ進める条件 | 対象 commit と作業ツリーの扱いを Operator が確認済み |

~~~bash
git status --short
git rev-parse HEAD
terraform version
aws --version
docker --version
kubectl version --client
python3 --version
jq --version
envsubst --version
~~~

### コマンド操作 BP-01-C02

| 項目 | 内容 |
| --- | --- |
| 目的 | 実行主体、アカウント、リージョンを誤りなく固定する |
| 実行ディレクトリ | 任意 |
| 前提条件 | 承認済み AWS profile または SSO session |
| 正確なコマンド | 下記コードブロック |
| dry-run/plan確認 | 読み取り専用だが AWS API を呼ぶため Operator 承認後に実行 |
| 成功時の期待結果 | Account、Arn、Region が Parameter Sheet と一致 |
| 失敗時停止条件 | 想定外アカウント、root user、Region 不一致、期限切れ認証 |
| 確認ログ/出力 | Account alias と role 名のみ。アクセスキーを保存しない |
| rollback方法 | 変更なし。誤 profile を解除 |
| 次へ進める条件 | 対象が検証用アカウント、Region が ap-northeast-1 |

~~~bash
export AWS_PROFILE=＜approved-profile＞
export AWS_REGION=ap-northeast-1
aws sts get-caller-identity
aws configure get region
~~~

構築前に AWS Budgets/請求アラートを設定する。Aurora Serverless v2、NAT Gateway、EKS control plane、CloudFront、CloudWatch Logs、WAF、S3/ECR 保持が継続課金要因である。予算アラート未設定、または停止判断者が未確定なら手順2へ進まない。

## 手順2. ACM・DNS・CodeStar Connection の事前入力

Parameter Sheet 対応: 00_使い方・前提の「構築前の必須確認」No.3〜5。詳細が必要な場合だけ02、03を参照する。

### ファイル編集 BP-02-E01

| 項目 | 内容 |
| --- | --- |
| 対象ファイル | ローカル専用 bootstrap/terraform.tfvars（Git 管理しない） |
| block/key | source_repository_id、source_branch、codestar_connection_arn |
| placeholder例 | ＜owner/repository＞、main、＜codestar-connection-arn＞ |
| 正となる値の取得元 | GitHub repository、CodeStar Connections の AVAILABLE 接続 |
| 編集完了条件 | 空文字がなく、git status に terraform.tfvars が表示されない |

~~~hcl
source_repository_id    = "＜owner/repository＞"
source_branch           = "main"
codestar_connection_arn = "＜codestar-connection-arn＞"
~~~

### コマンド操作 BP-02-C01

| 項目 | 内容 |
| --- | --- |
| 目的 | ALB HTTPS 用 ACM 証明書を ap-northeast-1 に用意する |
| 実行ディレクトリ | 任意 |
| 前提条件 | ＜domain＞の DNS を変更でき、証明書作成が承認済み |
| 正確なコマンド | 下記。既存証明書を使う場合は describe-certificate のみ |
| dry-run/plan確認 | request-certificate は AWS 変更。実行前に domain と Region を再確認 |
| 成功時の期待結果 | Status=ISSUED、対象 domain が一致 |
| 失敗時停止条件 | PENDING_VALIDATION、FAILED、別 Region、別 domain |
| 確認ログ/出力 | 証明書 ARN は SSM に保存し、本書や Git へ記載しない |
| rollback方法 | 未使用証明書を delete-certificate。DNS 検証レコードも確認して削除 |
| 次へ進める条件 | ap-northeast-1 の証明書が ISSUED |

~~~bash
aws acm request-certificate \
  --region ap-northeast-1 \
  --domain-name ＜domain＞ \
  --validation-method DNS

aws acm describe-certificate \
  --region ap-northeast-1 \
  --certificate-arn ＜certificate-arn＞ \
  --query 'Certificate.{Status:Status,DomainName:DomainName}'
~~~

### コマンド操作 BP-02-C02

| 項目 | 内容 |
| --- | --- |
| 目的 | GitHub Source 用 CodeStar Connection を作成し、接続を有効化する |
| 実行ディレクトリ | 任意 |
| 前提条件 | GitHub repository 管理権限と AWS 側承認 |
| 正確なコマンド | 下記。返却 ARN を使い AWS Console で pending handshake を完了 |
| dry-run/plan確認 | create-connection は AWS 変更。接続名と provider を確認 |
| 成功時の期待結果 | get-connection が ConnectionStatus=AVAILABLE |
| 失敗時停止条件 | PENDING のまま、対象 GitHub owner/repository が不一致 |
| 確認ログ/出力 | Connection ARN と AVAILABLE 状態 |
| rollback方法 | 未使用 Connection を delete-connection |
| 次へ進める条件 | AVAILABLE の ARN を BP-02-E01 に供給済み |

~~~bash
aws codestar-connections create-connection \
  --provider-type GitHub \
  --connection-name ops-platform-dev-github

aws codestar-connections get-connection \
  --connection-arn ＜codestar-connection-arn＞
~~~

DNS の public record は CloudFront domain 確定後に設定する。現時点では所有権と変更担当だけを確認し、未確定値を Terraform や frontend に埋め込まない。

## 手順3. Parameter Sheet 必須項目の確認・承認

Parameter Sheet 対応: 00_使い方・前提の「構築前の必須確認」12項目。01〜08は参照台帳であり、全行確認は不要である。

### 必須確認項目

| No. | いつ | 確認対象 | 実値の設定先 | 合格条件 |
| --- | --- | --- | --- | --- |
| 1 | 手順1 | AWSアカウント、実行role、リージョン | AWS profile/session、作業記録 | 検証用アカウント、root以外、ap-northeast-1 |
| 2 | 手順1 | 予算アラート、停止判断者 | AWS Budgets、作業記録 | アラート有効、停止判断者が確定 |
| 3 | 手順2/5 | ALB用ACM証明書 | SSM /ops-platform/dev/alb-certificate-arn | ap-northeast-1、対象domain、ISSUED |
| 4 | 手順2 | CodeStar Connection | bootstrap/terraform.tfvars | GitHub接続がAVAILABLE |
| 5 | 手順2 | source repository / branch | bootstrap/terraform.tfvars | owner/repositoryが正しく、branchはmain |
| 6 | 手順5 | ALB HTTPS許可CIDR | SSM /ops-platform/dev/alb-ingress-cidrs | JSON配列、管理対象CIDR、0.0.0.0/0なし |
| 7 | 手順5 | EKS API許可CIDR | SSM /ops-platform/dev/eks-public-access-cidrs | JSON配列、kubectl接続元、0.0.0.0/0なし |
| 8 | 手順5 | EKS Operator role | SSM /ops-platform/dev/eks-operator-principal-arn | 承認済みIAM role ARN |
| 9 | 手順5 | migration起動主体 | SSM /ops-platform/dev/migration-launcher-principal-arns | 承認済みIAM role ARNのJSON配列 |
| 10 | 手順5 | 初回起動ゲート | SSMのecs-desired-count / monitoring-enable-sns-subscription | ecs=0、SNS=false |
| 11 | 手順7前 | コスト・保持・destroy方針 | 作業記録。必要時のみ02、06、08 | NAT/Aurora/EKS/WAF等の継続課金とsnapshot責任者を承認 |
| 12 | 手順7直前 | EKS versionのStandard Support | variables.tfの候補とAWS公式情報 | apply時点でStandard Support対象 |

上記以外は次の扱いとする。

- variables.tfに既定値があり変更しない項目: 転記不要。planで採用値だけ確認する。
- Terraformが自動生成する名前、ID、ARN、bucket名、output: 事前入力不要。apply後に取得する。
- 05_Deploy環境変数: deploy直前にTerraform outputから取得するため、手順3では入力しない。
- 07_Category-C検証と08_destroy前確認: 該当手順で使用し、手順3で全行を完了させない。

### ファイル編集 BP-03-E01

| 項目 | 内容 |
| --- | --- |
| 対象ファイル | docs/operation/aws-resource-parameter-sheet.xlsx の先頭シート |
| block/key | 「構築前の必須確認」表の状態・記録列 |
| placeholder例 | 実値ではなく「確認済み」「SSM登録済み」「terraform.tfvars設定済み」 |
| 正となる値の取得元 | BP-01/02の結果、AWS/組織台帳、SSM登録結果 |
| 編集完了条件 | 12項目がすべて「確認済み」。記録列にSecret、実メール、アクセスキーを書かない |

### コマンド操作 BP-03-C01

| 項目 | 内容 |
| --- | --- |
| 目的 | Parameter Sheet の承認済み版を構築の入力基準に固定する |
| 実行ディレクトリ | リポジトリルート |
| 前提条件 | 先頭シートの必須12項目のレビュー完了 |
| 正確なコマンド | 下記 |
| dry-run/plan確認 | 読み取り専用 |
| 成功時の期待結果 | xlsx が存在し、Git の対象差分として認識される |
| 失敗時停止条件 | ファイル欠落、開けない、必須12項目のいずれかが未確認 |
| 確認ログ/出力 | ファイルハッシュと承認記録 |
| rollback方法 | 変更前版へ戻す。承認前版を構築に使わない |
| 次へ進める条件 | 必須12項目が確認済みで、必要な実値がterraform.tfvarsまたはSSMへ供給可能 |

~~~bash
test -f docs/operation/aws-resource-parameter-sheet.xlsx
shasum -a 256 docs/operation/aws-resource-parameter-sheet.xlsx
git status --short docs/operation/aws-resource-parameter-sheet.xlsx
~~~

## 手順4. Bootstrap の init・plan・承認・apply

Parameter Sheet 対応: 01、02、06、07 の Build手順 4。

### ファイル編集 BP-04-E01

| 項目 | 内容 |
| --- | --- |
| 対象ファイル | ローカル専用 bootstrap/terraform.tfvars |
| block/key | aws_region、project、env、source_*、codestar_connection_arn、artifact_retention_days、pipeline_*_parameter_name |
| placeholder例 | ap-northeast-1、ops-platform、dev、＜owner/repository＞ |
| 正となる値の取得元 | Parameter Sheet 02 と BP-02 の結果 |
| 編集完了条件 | Secretなし、実値ファイルが Git 管理外、SSM parameter name が手順5と一致 |

plan前に bootstrap/iam.tf と bootstrap/cicd.tf も読み取り確認し、terraform-exec-role、CodeBuild role、CodePipeline role、artifact KMS/S3、SSM読取範囲がParameter Sheetの所有関係と一致することを確認する。これらの追跡ファイルへ実アカウント固有値を直接追記しない。

### コマンド操作 BP-04-C01

| 項目 | 内容 |
| --- | --- |
| 目的 | Bootstrap の作成内容を初回ローカル plan で確認し、承認後だけ適用する |
| 実行ディレクトリ | リポジトリルート |
| 前提条件 | 手順1〜3完了、CodeStar Connection AVAILABLE |
| 正確なコマンド | 下記。apply は plan 承認後のみ |
| dry-run/plan確認 | bootstrap.plan と terraform show 出力で作成/変更/削除、S3/KMS/IAM/CodeBuild/CodePipelineを確認 |
| 成功時の期待結果 | init/validate=0、plan に想定外削除なし、apply complete |
| 失敗時停止条件 | validate非ゼロ、想定外account/region、AdministratorAccess、Resource=* の無登録例外、削除 |
| 確認ログ/出力 | bootstrap.plan、no-color plan、apply summary。Secretを保存しない |
| rollback方法 | apply前は何もしない。apply後は本体未構築の場合のみ承認付き destroy、空にすべきbucketは先に確認 |
| 次へ進める条件 | Bootstrap outputs が取得でき、Pipeline stage が Source→Fmt→Validate→Plan→Approval→Apply |

~~~bash
terraform -chdir=bootstrap fmt -check
terraform -chdir=bootstrap init
terraform -chdir=bootstrap validate
terraform -chdir=bootstrap plan -out=bootstrap.plan
terraform -chdir=bootstrap show -no-color bootstrap.plan

# 承認後のみ
terraform -chdir=bootstrap apply bootstrap.plan
~~~

terraform validate がネットワーク/認証だけを理由に非ゼロになった場合も成功扱いしない。作業記録に「失敗したコマンド」「エラー要約」「ネットワーク/認証条件」「未検証 module/resource」「再実行責任者」を記録し、解消後に同じ検証を再実行する。

## 手順5. Bootstrap outputs・SSM Pipeline 入力

Parameter Sheet 対応: 02、03、04、05 の Build手順 5。ここで用意する値は Pipeline plan の唯一の外部入力となる。

### ファイル編集

リポジトリ内ファイルは編集しない。SSM の値を terraform.tfvars や GitHub Actions secret へ複製しない。

### コマンド操作 BP-05-C01

| 項目 | 内容 |
| --- | --- |
| 目的 | Bootstrap outputs と commit SHA をローカル環境変数へ取得する |
| 実行ディレクトリ | リポジトリルート |
| 前提条件 | Bootstrap apply完了 |
| 正確なコマンド | 下記 |
| dry-run/plan確認 | Terraform outputとGitの読み取り |
| 成功時の期待結果 | state/artifact bucket、pipeline、role ARN、commit SHA が非空 |
| 失敗時停止条件 | null/空、想定外account、commit未確定 |
| 確認ログ/出力 | output 名と存在のみ。実ARN/IDを文書へ転記しない |
| rollback方法 | shell sessionを終了 |
| 次へ進める条件 | 全変数が非空 |

~~~bash
export STATE_BUCKET=$(terraform -chdir=bootstrap output -raw state_bucket_name)
export ARTIFACT_BUCKET=$(terraform -chdir=bootstrap output -raw artifact_bucket_name)
export PIPELINE_NAME=$(terraform -chdir=bootstrap output -raw codepipeline_name)
export TERRAFORM_EXEC_ROLE_ARN=$(terraform -chdir=bootstrap output -raw terraform_exec_role_arn)
export COMMIT_SHA=$(git rev-parse HEAD)
test -n "$STATE_BUCKET" -a -n "$ARTIFACT_BUCKET" -a -n "$PIPELINE_NAME" -a -n "$COMMIT_SHA"
~~~

### コマンド操作 BP-05-C02

| 項目 | 内容 |
| --- | --- |
| 目的 | 初回 plan 用の非機微・運用入力を SSM に登録する |
| 実行ディレクトリ | リポジトリルート |
| 前提条件 | 値が Parameter Sheet で承認済み。実メール/Secretは下記の endpoint parameter 以外へ書かない |
| 正確なコマンド | 下記。既存値更新は --overwrite を付け、事前に差分承認 |
| dry-run/plan確認 | put-parameter は AWS 変更。parameter name、型、値形式を確認 |
| 成功時の期待結果 | 全 parameter の Version が返る。初回 desired count=0 |
| 失敗時停止条件 | JSON形式不正、world-open CIDR、未承認principal、desired countが0以外 |
| 確認ログ/出力 | parameter名とversionだけ。値はログへ転記しない |
| rollback方法 | 新規parameterをdelete、更新時は直前versionの値へ承認付き復旧 |
| 次へ進める条件 | get-parameterで存在確認でき、CodeBuild roleが対象pathを読める |

~~~bash
aws ssm put-parameter --region ap-northeast-1 --type String \
  --name /ops-platform/dev/alb-certificate-arn --value '＜certificate-arn＞'
aws ssm put-parameter --region ap-northeast-1 --type String \
  --name /ops-platform/dev/alb-ingress-cidrs --value '＜approved-alb-cidrs-json＞'
aws ssm put-parameter --region ap-northeast-1 --type String \
  --name /ops-platform/dev/eks-operator-principal-arn --value '＜role-arn＞'
aws ssm put-parameter --region ap-northeast-1 --type String \
  --name /ops-platform/dev/migration-launcher-principal-arns --value '[\"＜role-arn＞\"]'
aws ssm put-parameter --region ap-northeast-1 --type String \
  --name /ops-platform/dev/eks-public-access-cidrs --value '＜approved-eks-cidrs-json＞'
aws ssm put-parameter --region ap-northeast-1 --type String \
  --name /ops-platform/dev/application-image-tag --value "$COMMIT_SHA"
aws ssm put-parameter --region ap-northeast-1 --type String \
  --name /ops-platform/dev/ecs-desired-count --value '0'
aws ssm put-parameter --region ap-northeast-1 --type String \
  --name /ops-platform/dev/cognito-callback-urls --value '[\"http://localhost:5173/callback\"]'
aws ssm put-parameter --region ap-northeast-1 --type String \
  --name /ops-platform/dev/cognito-logout-urls --value '[\"http://localhost:5173/\"]'
aws ssm put-parameter --region ap-northeast-1 --type String \
  --name /ops-platform/dev/cognito-keep-localhost-urls --value 'false'
aws ssm put-parameter --region ap-northeast-1 --type String \
  --name /ops-platform/dev/monitoring-enable-sns-subscription --value 'false'
aws ssm put-parameter --region ap-northeast-1 --type String \
  --name /ops-platform/dev/monitoring-notification-parameter-name \
  --value '/ops-platform/dev/monitoring-notification-endpoint'
aws ssm put-parameter --region ap-northeast-1 --type String \
  --name /ops-platform/dev/monitoring-notification-protocol --value 'email'
~~~

## 手順6. Lambda ZIP の再現生成・versioned S3 upload

Parameter Sheet 対応: 03、04 の Build手順 6。

### ファイル編集

apps/portal-lambda/requirements.txt の固定バージョンと apps/portal-lambda/build.sh を使用する。生成物 apps/portal-lambda/dist/portal-api.zip はGitへ追加しない。

### コマンド操作 BP-06-C01

| 項目 | 内容 |
| --- | --- |
| 目的 | 同一sourceから同一hashのLambda ZIPを再現生成する |
| 実行ディレクトリ | リポジトリルート |
| 前提条件 | Python/pip利用可能、依存取得先が承認済み |
| 正確なコマンド | 下記 |
| dry-run/plan確認 | ローカル生成のみ。AWS変更なし |
| 成功時の期待結果 | 2回の base64 SHA-256 が一致 |
| 失敗時停止条件 | build失敗、hash不一致、未固定依存、ZIPにapp/欠落 |
| 確認ログ/出力 | hashのみ。ZIP内容にSecretを含めない |
| rollback方法 | dist/portal-api.zipを削除 |
| 次へ進める条件 | 再現hash一致 |

~~~bash
apps/portal-lambda/build.sh
export LAMBDA_HASH_1=$(openssl dgst -sha256 -binary apps/portal-lambda/dist/portal-api.zip | openssl base64 -A)
apps/portal-lambda/build.sh
export LAMBDA_HASH_2=$(openssl dgst -sha256 -binary apps/portal-lambda/dist/portal-api.zip | openssl base64 -A)
test "$LAMBDA_HASH_1" = "$LAMBDA_HASH_2"
unzip -l apps/portal-lambda/dist/portal-api.zip
~~~

### コマンド操作 BP-06-C02

| 項目 | 内容 |
| --- | --- |
| 目的 | commit SHA不変keyで暗号化・versioned objectを作成する |
| 実行ディレクトリ | リポジトリルート |
| 前提条件 | BP-06-C01成功、artifact bucket versioning/KMS有効、AWS変更承認 |
| 正確なコマンド | 下記 |
| dry-run/plan確認 | bucket/key/hashを表示して承認。put-objectはAWS変更 |
| 成功時の期待結果 | VersionIdが非空、head-objectのSSE=aws:kms、metadata hash一致 |
| 失敗時停止条件 | VersionId=None、暗号化不一致、metadata hash不一致 |
| 確認ログ/出力 | bucket/key/version/hash。ZIP本体や認証情報は記録しない |
| rollback方法 | 当該versionだけを delete-object --version-id で承認付き削除 |
| 次へ進める条件 | object identity 4値が確認済み。Pipeline Planも同じ処理を再実行し、そのmetadataをapplyの正とする |

~~~bash
export PACKAGE_KEY="lambda/$COMMIT_SHA/portal-api.zip"
export PACKAGE_VERSION=$(aws s3api put-object \
  --region ap-northeast-1 \
  --bucket "$ARTIFACT_BUCKET" \
  --key "$PACKAGE_KEY" \
  --body apps/portal-lambda/dist/portal-api.zip \
  --server-side-encryption aws:kms \
  --metadata "source-code-hash=$LAMBDA_HASH_2" \
  --query VersionId --output text)
test -n "$PACKAGE_VERSION" -a "$PACKAGE_VERSION" != "None"
aws s3api head-object --region ap-northeast-1 \
  --bucket "$ARTIFACT_BUCKET" --key "$PACKAGE_KEY" --version-id "$PACKAGE_VERSION"
~~~

## 手順7. 本体 plan・承認・初回 apply（ECS desired_count=0）

Parameter Sheet 対応: 01〜04、06、07 の Build手順 7。

### ファイル編集 BP-07-E01

| 項目 | 内容 |
| --- | --- |
| 対象ファイル | infra/environments/dev/backend.tf |
| block/key | terraform.backend.s3 |
| placeholder例 | bucketは記載しない。key=environments/dev/terraform.tfstate、region=ap-northeast-1、use_lockfile=true |
| 正となる値の取得元 | コミット済みpartial backendとBootstrap output |
| 編集完了条件 | 実bucket/account/credentialなし。Pipelineが -backend-config でbucketを供給 |

### コマンド操作 BP-07-C01

| 項目 | 内容 |
| --- | --- |
| 目的 | apply直前にEKS versionがAWS Standard Support内か確認する |
| 実行ディレクトリ | 任意 |
| 前提条件 | Parameter Sheetの eks_kubernetes_version 候補 |
| 正確なコマンド | AWS公式EKS Kubernetes versions表と下記CLIの両方を確認 |
| dry-run/plan確認 | 読み取り専用AWS API |
| 成功時の期待結果 | 指定versionがStandard Support内 |
| 失敗時停止条件 | Standard Support外、終了日を確認できない、Extended Supportが必要 |
| 確認ログ/出力 | 確認日、version、Standard Support終了日 |
| rollback方法 | 変更なし |
| 次へ進める条件 | Standard Support内。外ならapplyを停止し、変数・設計・テストを更新して再plan |

~~~bash
aws eks describe-addon-versions \
  --region ap-northeast-1 \
  --kubernetes-version ＜eks-version＞ \
  --query 'addons[0].addonVersions[0].compatibilities[0].clusterVersion'
~~~

Extended Support を前提に進めない。既定値が現在の Standard Supportから外れている場合は、planより前にリポジトリ実装を更新する。

### コマンド操作 BP-07-C02

| 項目 | 内容 |
| --- | --- |
| 目的 | Pipelineで17 moduleをplanし、承認済みbinary planだけを初回applyする |
| 実行ディレクトリ | 任意 |
| 前提条件 | mainに対象commitがあり、SSM ecs-desired-count=0、手順6完了 |
| 正確なコマンド | 下記。ApprovalはAWS Console/承認APIでplan確認後のみ |
| dry-run/plan確認 | Fmt→Validate→Planで停止し、plan-summaryを確認 |
| 成功時の期待結果 | cycleなし、17 module、ECS desired_count=0、想定外削除なし、Apply成功 |
| 失敗時停止条件 | P0 resource欠落、WAF region不正、ALB TLS/log欠落、bucket名衝突、削除、ECS count≠0 |
| 確認ログ/出力 | pipeline execution ID、plan-summary、承認者、apply summary |
| rollback方法 | Approvalを拒否。apply後は修正planを作成し承認経路で戻す |
| 次へ進める条件 | apply成功、Terraform outputs取得可能、ECSタスク0 |

~~~bash
export PIPELINE_EXECUTION_ID=$(aws codepipeline start-pipeline-execution \
  --name "$PIPELINE_NAME" \
  --query pipelineExecutionId --output text)
aws codepipeline get-pipeline-state --name "$PIPELINE_NAME"
~~~

validateがネットワーク/認証で失敗した場合は手順4と同じ記録項目を残し、未検証範囲がゼロになるまでApprovalしない。初回planでは Aurora/NAT/EKS/CloudFront と log retention、S3 force_destroy、Aurora deletion_protection/skip_final_snapshotを個別承認する。

## 手順8. 5イメージ build・push

Parameter Sheet 対応: 04、05、07 の Build手順 8。

### ファイル編集

Dockerfileは編集しない。イメージtagは /ops-platform/dev/application-image-tag のcommit SHAを唯一の値とし、latestを最終構築に使わない。

### コマンド操作 BP-08-C01

| 項目 | 内容 |
| --- | --- |
| 目的 | Backend、worker 3種、migrationの5 ECR imageをlinux/amd64で作成・pushする |
| 実行ディレクトリ | リポジトリルート |
| 前提条件 | 初回infra apply成功、ECR 5 repository存在、Docker実行承認 |
| 正確なコマンド | 下記。ECR URLは terraform output -json ecr_repository_urls から取得 |
| dry-run/plan確認 | 先に各docker build commandと5 URIを表示し、tag/arch/contextを確認 |
| 成功時の期待結果 | 5 URIへ同一commit tagが存在し、manifest architecture=linux/amd64 |
| 失敗時停止条件 | push失敗、tag相違、worker repository重複、migration contextがrepo root以外 |
| 確認ログ/出力 | image URI、digest、architecture。認証tokenは保存しない |
| rollback方法 | 未使用tagをbatch-delete-imageで承認付き削除 |
| 次へ進める条件 | 5 image digest確認済み |

~~~bash
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export IMAGE_TAG=$(aws ssm get-parameter --name /ops-platform/dev/application-image-tag --query Parameter.Value --output text)
export REGISTRY="$AWS_ACCOUNT_ID.dkr.ecr.ap-northeast-1.amazonaws.com"

aws ecr get-login-password --region ap-northeast-1 |
  docker login --username AWS --password-stdin "$REGISTRY"

docker build --platform linux/amd64 \
  -t "$REGISTRY/ops-platform-dev-backend-api:$IMAGE_TAG" apps/backend-api

docker build --platform linux/amd64 \
  -t "$REGISTRY/ops-platform-dev-alarm-event-processor:$IMAGE_TAG" \
  -t "$REGISTRY/ops-platform-dev-security-finding-worker:$IMAGE_TAG" \
  -t "$REGISTRY/ops-platform-dev-monthly-summary-cronjob:$IMAGE_TAG" \
  apps/eks-workers

docker build --platform linux/amd64 \
  -f apps/db-migration/Dockerfile \
  -t "$REGISTRY/ops-platform-dev-db-migration:$IMAGE_TAG" .

docker push "$REGISTRY/ops-platform-dev-backend-api:$IMAGE_TAG"
docker push "$REGISTRY/ops-platform-dev-alarm-event-processor:$IMAGE_TAG"
docker push "$REGISTRY/ops-platform-dev-security-finding-worker:$IMAGE_TAG"
docker push "$REGISTRY/ops-platform-dev-monthly-summary-cronjob:$IMAGE_TAG"
docker push "$REGISTRY/ops-platform-dev-db-migration:$IMAGE_TAG"
~~~

リポジトリ名は terraform -chdir=infra/environments/dev output -json ecr_repository_urls の実結果を正とする。上記の規約名と異なる場合は文字列を推測せずoutputを使用する。

## 手順9. VPC内 one-off migration

Parameter Sheet 対応: 04、05、07 の Build手順 9。

### ファイル編集

リポジトリ内ファイルは編集しない。必要値は Terraform の `ecs_deployment`、`ecr_repository_urls`、`aurora` outputs から下記コマンドで自動取得する。値を手入力・転記しない。DB passwordを取得・表示しない。

### コマンド操作 BP-09-C01

| 項目 | 内容 |
| --- | --- |
| 目的 | migration-launcher-roleをAssumeRoleし、private subnet内Fargate taskでschemaを適用する |
| 実行ディレクトリ | リポジトリルート |
| 前提条件 | Bootstrapと初回infra apply成功、migration image存在、ECS desired_count=0、Aurora available、AWS CLI認証済み |
| 正確なコマンド | 下記を上から1ブロックずつ実行する。山括弧の手入力箇所はない。最初は--executeなし、その出力承認後に--execute |
| dry-run/plan確認 | dry-runでAssumeRole/run-task/wait/describe command、subnet、SG、public IP disabledを確認 |
| 成功時の期待結果 | lastStatus=STOPPED、essential container exitCode=0、7業務tableと制約が存在 |
| 失敗時停止条件 | task ARNなし、exitCode≠0、public subnet/public IP、schema確認失敗 |
| 確認ログ/出力 | task ARN、lastStatus、exitCode、stoppedReason、migration log。Secret値は保存しない |
| rollback方法 | 失敗時はECS countを0のまま維持。再実行可能性を確認し、破壊的SQLを手動実行しない |
| 次へ進める条件 | exitCode=0とschema検証の両方が合格 |

~~~bash
# 1. 共通値とremote state backendを初期化する
#    initはstateを読み取れるようにする操作であり、AWSリソースを作成・変更しない。
export AWS_REGION=ap-northeast-1
export STATE_BUCKET="$(terraform -chdir=bootstrap output -raw state_bucket_name)"
test -n "$STATE_BUCKET"

terraform -chdir=infra/environments/dev init \
  -input=false \
  -lockfile=readonly \
  -reconfigure \
  -backend-config="bucket=$STATE_BUCKET"

# 2. migrationに必要な値をTerraform outputsから自動設定する
export ECS_DEPLOYMENT_JSON="$(terraform -chdir=infra/environments/dev output -json ecs_deployment)"
export ECR_REPOSITORIES_JSON="$(terraform -chdir=infra/environments/dev output -json ecr_repository_urls)"
export AURORA_JSON="$(terraform -chdir=infra/environments/dev output -json aurora)"

export MIGRATION_LAUNCHER_ROLE_ARN="$(jq -er '.migration_launcher_role_arn | select(type == "string" and length > 0)' <<<"$ECS_DEPLOYMENT_JSON")"
export ECS_CLUSTER="$(jq -er '.migration_cluster_arn | select(type == "string" and length > 0)' <<<"$ECS_DEPLOYMENT_JSON")"
export ECS_CLUSTER_NAME="$(jq -er '.cluster_name | select(type == "string" and length > 0)' <<<"$ECS_DEPLOYMENT_JSON")"
export ECS_SERVICE_NAME="$(jq -er '.service_name | select(type == "string" and length > 0)' <<<"$ECS_DEPLOYMENT_JSON")"
export ECS_TASK_DEFINITION="$(jq -er '.migration_task_definition | select(type == "string" and length > 0)' <<<"$ECS_DEPLOYMENT_JSON")"
export PRIVATE_SUBNET_IDS="$(jq -er '.private_subnet_ids | select(type == "array" and length > 0) | join(",")' <<<"$ECS_DEPLOYMENT_JSON")"
export MIGRATION_SECURITY_GROUP_ID="$(jq -er '.migration_security_group_id | select(type == "string" and length > 0)' <<<"$ECS_DEPLOYMENT_JSON")"
export MIGRATION_REPOSITORY_URL="$(jq -er '.["db-migration"] | select(type == "string" and length > 0)' <<<"$ECR_REPOSITORIES_JSON")"
export AURORA_CLUSTER_ID="$(jq -er '.cluster_id | select(type == "string" and length > 0)' <<<"$AURORA_JSON")"
export IMAGE_TAG="$(aws ssm get-parameter \
  --region "$AWS_REGION" \
  --name /ops-platform/dev/application-image-tag \
  --query 'Parameter.Value' \
  --output text)"
export EXPECTED_MIGRATION_IMAGE="${MIGRATION_REPOSITORY_URL}:${IMAGE_TAG}"

# 3. 実行前検査。いずれかが失敗した場合は--executeへ進まない
aws sts get-caller-identity --query '{Account:Account,Arn:Arn}' --output table

aws ecr describe-images \
  --region "$AWS_REGION" \
  --repository-name "${MIGRATION_REPOSITORY_URL##*/}" \
  --image-ids imageTag="$IMAGE_TAG" \
  --query 'imageDetails[0].{Digest:imageDigest,PushedAt:imagePushedAt}' \
  --output table

export ACTUAL_MIGRATION_IMAGE="$(aws ecs describe-task-definition \
  --region "$AWS_REGION" \
  --task-definition "$ECS_TASK_DEFINITION" \
  --query 'taskDefinition.containerDefinitions[?essential==`true`].image | [0]' \
  --output text)"
test "$ACTUAL_MIGRATION_IMAGE" = "$EXPECTED_MIGRATION_IMAGE"

test "$(aws rds describe-db-clusters \
  --region "$AWS_REGION" \
  --db-cluster-identifier "$AURORA_CLUSTER_ID" \
  --query 'DBClusters[0].Status' \
  --output text)" = "available"

test "$(aws ecs describe-services \
  --region "$AWS_REGION" \
  --cluster "$ECS_CLUSTER_NAME" \
  --services "$ECS_SERVICE_NAME" \
  --query 'services[0].desiredCount' \
  --output text)" = "0"

printf 'MIGRATION_LAUNCHER_ROLE_ARN=%s\n' "$MIGRATION_LAUNCHER_ROLE_ARN"
printf 'ECS_CLUSTER=%s\n' "$ECS_CLUSTER"
printf 'ECS_TASK_DEFINITION=%s\n' "$ECS_TASK_DEFINITION"
printf 'PRIVATE_SUBNET_IDS=%s\n' "$PRIVATE_SUBNET_IDS"
printf 'MIGRATION_SECURITY_GROUP_ID=%s\n' "$MIGRATION_SECURITY_GROUP_ID"
printf 'MIGRATION_IMAGE=%s\n' "$ACTUAL_MIGRATION_IMAGE"

# 4. dry-run。AWSの変更操作は行われない
scripts/deploy-migration.sh
~~~

dry-runに表示された role、cluster、task definition、private subnet、security group、`assignPublicIp=DISABLED` が上記の取得値と一致することを確認する。確認後、実行を承認した場合だけ次を実行する。

~~~bash
# 5. 承認後のみ実行する
scripts/deploy-migration.sh --execute
~~~

`deploy-migration.sh` は内部で `sts:AssumeRole`、`ecs:RunTask`、`ecs:Wait`、`ecs:DescribeTasks` を行い、先頭のmigration containerの `exitCode=0` 以外を失敗として終了する。DB Secretはcustomer-managed KMS keyで暗号化されるため、migration task roleには対象Secretの `secretsmanager:GetSecretValue` と、対象KMS key限定・Secrets Manager経由限定の `kms:Decrypt` の両方が必要である。成功時は `[done] migration task stopped successfully with exitCode=0.` が表示される。

失敗時は再実行せず、migrationログを確認する。次のコマンドは最新のlog streamを自動選択する。

~~~bash
export MIGRATION_LOG_GROUP="/ecs/ops-platform-dev-migration"
export MIGRATION_LOG_STREAM="$(aws logs describe-log-streams \
  --region "$AWS_REGION" \
  --log-group-name "$MIGRATION_LOG_GROUP" \
  --order-by LastEventTime \
  --descending \
  --max-items 1 \
  --query 'logStreams[0].logStreamName' \
  --output text)"

aws logs get-log-events \
  --region "$AWS_REGION" \
  --log-group-name "$MIGRATION_LOG_GROUP" \
  --log-stream-name "$MIGRATION_LOG_STREAM" \
  --start-from-head \
  --limit 500 \
  --query 'events[].message' \
  --output text
~~~

## 手順10. ECS desired_count=1 の再plan・承認・apply

Parameter Sheet 対応: 03、04、05 の Build手順 10。

### ファイル編集 BP-10-E01

| 項目 | 内容 |
| --- | --- |
| 対象ファイル | リポジトリ内編集なし。SSM /ops-platform/dev/ecs-desired-count |
| block/key | ecs_desired_count |
| placeholder例 | 1 |
| 正となる値の取得元 | migration exitCode=0の承認記録 |
| 編集完了条件 | SSM値が1。variables.tfのdefaultを書き換えない |

### コマンド操作 BP-10-C01

| 項目 | 内容 |
| --- | --- |
| 目的 | migration合格後だけBackend ECSを1台へ開始する |
| 実行ディレクトリ | 任意 |
| 前提条件 | 手順9合格、Backend image digest確認済み |
| 正確なコマンド | 下記 |
| dry-run/plan確認 | SSM更新後に新Pipeline Planを作り、差分が主にdesired_count 0→1であることを確認 |
| 成功時の期待結果 | 承認後apply成功、service desired/running count=1、ALB health正常 |
| 失敗時停止条件 | migration未確認、別image tag、想定外infra変更、health check失敗 |
| 確認ログ/出力 | SSM version、pipeline execution ID、plan summary、ECS service event |
| rollback方法 | SSMを0へ戻し、新たなplan→承認→apply |
| 次へ進める条件 | ECS running=1、health check合格、protected APIが401/期待成功を返す |

~~~bash
aws ssm put-parameter --region ap-northeast-1 --type String --overwrite \
  --name /ops-platform/dev/ecs-desired-count --value '1'

aws codepipeline start-pipeline-execution --name "$PIPELINE_NAME"
aws codepipeline get-pipeline-state --name "$PIPELINE_NAME"
~~~

## 手順11. EKS logging・workload配信

Parameter Sheet 対応: 03、04、05、07 の Build手順 11。

### ファイル編集 BP-11-E01

| 項目 | 内容 |
| --- | --- |
| 対象ファイル | apps/eks-workers/k8s/*.yamlは直接実値編集しない |
| block/key | image、IRSA role ARN、queue URL、DB secret ARN、log group、Portal書込先 |
| placeholder例 | 環境変数名のplaceholder |
| 正となる値の取得元 | Terraform outputs と scripts/deploy-eks.sh の入力契約 |
| 編集完了条件 | 一時render後の未解決placeholderがゼロ。Git管理YAMLに実ARN/URLなし |

### コマンド操作 BP-11-C01

| 項目 | 内容 |
| --- | --- |
| 目的 | EKS logging prerequisitesを先に適用し、その後3 workloadを配信する |
| 実行ディレクトリ | リポジトリルート |
| 前提条件 | EKS Standard Support再確認、5 image合格、Operator access確認、全env設定 |
| 正確なコマンド | 下記。最初はdry-run、その出力承認後に--execute |
| dry-run/plan確認 | render結果にplaceholderなし、適用順00→40→10→20→21→30 |
| 成功時の期待結果 | 3 workloadが300秒以内にRunning/Job complete、image pull成功 |
| 失敗時停止条件 | auth can-i不一致、placeholder、ImagePullBackOff、logging ConfigMap欠落 |
| 確認ログ/出力 | rendered validation、rollout/job status、pod event、CloudWatch log stream |
| rollback方法 | 直前tagで再配信、Deploymentはrollout undo、CronJob停止。logging前提はworkload停止後に戻す |
| 次へ進める条件 | 3 workloadとCloudWatch logging、Operator権限が合格 |

~~~bash
aws eks update-kubeconfig --region ap-northeast-1 --name ＜eks-cluster-name＞
kubectl auth can-i get pods --namespace workers

export AWS_REGION=ap-northeast-1
export AWS_ACCOUNT_ID=＜account-id＞
export EKS_CLUSTER=＜eks_deployment.cluster_name＞
export ALARM_ECR_REPO=＜alarm-repository-name＞
export FINDING_ECR_REPO=＜finding-repository-name＞
export SUMMARY_ECR_REPO=＜summary-repository-name＞
export EKS_ALARM_WORKER_ROLE_ARN=＜eks_deployment.alarm_worker_role_arn＞
export EKS_FINDING_WORKER_ROLE_ARN=＜eks_deployment.finding_worker_role_arn＞
export EKS_CRONJOB_ROLE_ARN=＜eks_deployment.cronjob_role_arn＞
export WORKER_DB_SECRET_ARN=＜aurora.secret_arn＞
export ALARM_QUEUE_URL=＜messaging.alarm_queue_url＞
export FINDING_QUEUE_URL=＜messaging.finding_queue_url＞
export WORKER_LOG_GROUP_NAME=＜eks_deployment.worker_log_group_name＞
export PORTAL_REPORTS_BUCKET=＜portal_deployment.s3_bucket_name＞
export PORTAL_REPORT_METADATA_TABLE=＜portal_deployment.report_metadata_table_name＞
export PORTAL_PUBLIC_STATUS_ITEMS_TABLE=＜portal_deployment.public_status_items_table_name＞

scripts/deploy-eks.sh --tag "$IMAGE_TAG"

# dry-run承認後のみ。内部適用順:
# apps/eks-workers/k8s/00-namespace.yaml
# apps/eks-workers/k8s/40-fargate-logging.yaml
# apps/eks-workers/k8s/10-serviceaccounts.yaml
# apps/eks-workers/k8s/20-alarm-event-processor.yaml
# apps/eks-workers/k8s/21-security-finding-worker.yaml
# apps/eks-workers/k8s/30-monthly-summary-cronjob.yaml
scripts/deploy-eks.sh --tag "$IMAGE_TAG" --execute

kubectl get pods -n workers
kubectl get cronjob -n workers
~~~

## 手順12. CloudFront確定後のCognito HTTPS URL更新

Parameter Sheet 対応: 03、04、07 の Build手順 12。

### ファイル編集 BP-12-E01

| 項目 | 内容 |
| --- | --- |
| 対象ファイル | リポジトリ内編集なし。SSM cognito-callback-urls / logout-urls / keep-localhost-urls |
| block/key | cognito_callback_urls、cognito_logout_urls、cognito_keep_localhost_urls |
| placeholder例 | ["https://＜cloudfront-domain＞/callback"]、["https://＜cloudfront-domain＞/"]、false |
| 正となる値の取得元 | portal_deployment.cloudfront_domain_name |
| 編集完了条件 | HTTPS URLのみ。localhostを保持しない。Cognito側とfrontend設定が一致 |

### コマンド操作 BP-12-C01

| 項目 | 内容 |
| --- | --- |
| 目的 | CloudFront domainを正としてCognito callback/logout URLを確定する |
| 実行ディレクトリ | 任意 |
| 前提条件 | 初回CloudFront distribution Deployed |
| 正確なコマンド | 下記 |
| dry-run/plan確認 | SSM更新値を確認し、新Pipeline PlanでCognito app client差分だけを確認 |
| 成功時の期待結果 | 承認後apply成功、HTTPS callback/logout登録、localhostなし |
| 失敗時停止条件 | HTTP、別domain、localhost残存、想定外CloudFront/Cognito再作成 |
| 確認ログ/出力 | SSM version、plan summary、Cognito client設定 |
| rollback方法 | 直前URLをSSMへ戻し、新plan→承認→apply |
| 次へ進める条件 | OAuth state/PKCE/expiry/logoutのlive検証準備完了 |

~~~bash
export CLOUDFRONT_DOMAIN=＜portal_deployment.cloudfront_distribution_domain＞
aws ssm put-parameter --region ap-northeast-1 --type String --overwrite \
  --name /ops-platform/dev/cognito-callback-urls \
  --value "[\"https://$CLOUDFRONT_DOMAIN/callback\"]"
aws ssm put-parameter --region ap-northeast-1 --type String --overwrite \
  --name /ops-platform/dev/cognito-logout-urls \
  --value "[\"https://$CLOUDFRONT_DOMAIN/\"]"
aws ssm put-parameter --region ap-northeast-1 --type String --overwrite \
  --name /ops-platform/dev/cognito-keep-localhost-urls --value 'false'

aws codepipeline start-pipeline-execution --name "$PIPELINE_NAME"
~~~

独自domainを使う場合は、CloudFront alternate domain/certificateの設計とDNSを別途承認済み変更として実装してから、そのHTTPS domainを使用する。未実装の値を本手順だけで仮定しない。

## 手順13. Frontend・Sample Data・Monitoring

Parameter Sheet 対応: 03〜07 の Build手順 13。

### ファイル編集 BP-13-E01

| 項目 | 内容 |
| --- | --- |
| 対象ファイル | scripts/deploy-frontend.sh が一時生成するconfig.js |
| block/key | Cognito IDs/domain、redirect/logout URI、API base URL |
| placeholder例 | Terraform portal_deployment output |
| 正となる値の取得元 | portal_deployment と手順12のHTTPS URL |
| 編集完了条件 | 一時成果物にplaceholderなし。リポジトリのconfig.jsへ実値を書かない |

### コマンド操作 BP-13-C01

| 項目 | 内容 |
| --- | --- |
| 目的 | FrontendをS3へ同期しCloudFront cacheを無効化する |
| 実行ディレクトリ | リポジトリルート |
| 前提条件 | Cognito HTTPS URL更新済み、CloudFront Deployed、全env設定 |
| 正確なコマンド | 下記。dry-run承認後のみ--execute |
| dry-run/plan確認 | config.js生成値とplaceholder検査、S3/invalidation commandを確認 |
| 成功時の期待結果 | sync成功、invalidation ID返却、Portal表示 |
| 失敗時停止条件 | placeholder、URL不一致、sync/invalidation失敗 |
| 確認ログ/出力 | sync summary、invalidation ID。tokenは保存しない |
| rollback方法 | 直前frontend成果物を同scriptで再配信しinvalidation |
| 次へ進める条件 | OAuth loginと4 API smokeが実行可能 |

~~~bash
export AWS_REGION=ap-northeast-1
export S3_BUCKET=＜portal_deployment.s3_bucket_name＞
export CLOUDFRONT_DISTRIBUTION_ID=＜portal_deployment.cloudfront_distribution_id＞
export COGNITO_USER_POOL_ID=＜portal_deployment.cognito_user_pool_id＞
export COGNITO_APP_CLIENT_ID=＜portal_deployment.cognito_app_client_id＞
export COGNITO_DOMAIN=＜portal_deployment.cognito_domain＞
export COGNITO_REDIRECT_URI="https://$CLOUDFRONT_DOMAIN/callback"
export COGNITO_LOGOUT_URI="https://$CLOUDFRONT_DOMAIN/"

scripts/deploy-frontend.sh

# dry-run承認後のみ
scripts/deploy-frontend.sh --execute
~~~

### コマンド操作 BP-13-C02

| 項目 | 内容 |
| --- | --- |
| 目的 | 非機微dummy event/dataを投入し、A→B連携と監視を確認する |
| 実行ディレクトリ | リポジトリルート |
| 前提条件 | ECS/EKS/frontend正常、dummy data承認 |
| 正確なコマンド | 下記。各scriptは最初に--executeなしで確認 |
| dry-run/plan確認 | payloadがdummyであり、実顧客情報・Secretを含まないことを確認 |
| 成功時の期待結果 | queue分離、worker取込、A→Bが決定的keyへ収束、Portal表示 |
| 失敗時停止条件 | 他queue配送、重複、Product_B→Product_Aアクセス、実データ混入 |
| 確認ログ/出力 | event ID、dummy key、worker/Lambda log、dashboard |
| rollback方法 | dummy dataだけを識別して削除。rule/permissionを場当たり変更しない |
| 次へ進める条件 | C-02/C-03/C-06/C-07/C-09/C-14が合格または保留理由を記録 |

~~~bash
python3 scripts/seed_alarm_events.py
python3 scripts/seed_finding_events.py --count 5
python3 scripts/seed_portal_reports.py --count 6 \
  --report-metadata-table ＜report-metadata-table＞ \
  --public-status-table ＜public-status-items-table＞ \
  --reports-bucket ＜portal-bucket＞

# payload承認後のみ
python3 scripts/seed_alarm_events.py --execute
python3 scripts/seed_finding_events.py --execute --count 5
python3 scripts/seed_portal_reports.py --execute --count 6 \
  --report-metadata-table ＜report-metadata-table＞ \
  --public-status-table ＜public-status-items-table＞ \
  --reports-bucket ＜portal-bucket＞
~~~

### コマンド操作 BP-13-C03

| 項目 | 内容 |
| --- | --- |
| 目的 | SNS通知を任意で有効化し、Monitoring dashboard/alarmを確認する |
| 実行ディレクトリ | 任意 |
| 前提条件 | 実通知先をSSM SecureStringへ保存する承認 |
| 正確なコマンド | 下記。通知不要ならenable=falseのまま |
| dry-run/plan確認 | endpoint値をログへ表示せず、planでsubscription追加だけを確認 |
| 成功時の期待結果 | apply成功、SNS confirmationが通知先へ届く |
| 失敗時停止条件 | endpoint漏えい、想定外protocol/topic、alarm設定欠落 |
| 確認ログ/出力 | SSM version、subscription PendingConfirmation/Confirmed、alarm状態 |
| rollback方法 | enable=falseへ戻して新plan→承認→apply |
| 次へ進める条件 | 未確認endpointはC保留として記録。Terraform apply自体の失敗扱いにはしない |

~~~bash
aws ssm put-parameter --region ap-northeast-1 --type SecureString --overwrite \
  --name /ops-platform/dev/monitoring-notification-endpoint \
  --value '＜notification-endpoint＞'
aws ssm put-parameter --region ap-northeast-1 --type String --overwrite \
  --name /ops-platform/dev/monitoring-enable-sns-subscription --value 'true'
aws ssm put-parameter --region ap-northeast-1 --type String --overwrite \
  --name /ops-platform/dev/monitoring-notification-protocol --value 'email'
aws codepipeline start-pipeline-execution --name "$PIPELINE_NAME"
~~~

email/email-json subscriptionのconfirmationはCategory Cである。未確認でもSNS subscriptionはPendingConfirmationとなり、Terraform構成の作成自体を失敗扱いにしない。ただし通知到達テストは合格にできない。

## 手順14. Category C・停止・rollback・コスト停止・destroy

Parameter Sheet 対応: 07_Category-C検証、08_destroy前確認の全行。

### Category C 完了判定

| ID | 対象 | 合格条件 | 失敗時 |
| --- | --- | --- | --- |
| C-01 | Aurora migration | exitCode=0、7業務table/constraint | ECS=0を維持、再実行可能性確認 |
| C-02/C-03 | EventBridge/SQS/DLQ | alarm/finding分離、5回後専用DLQ | seed停止、rule/queue修正 |
| C-04/C-05 | EKS/image | 300秒以内に稼働、5 image linux/amd64 | workload rollback |
| C-06 | A→B | S3 1 object、DynamoDB各1 itemへ収束 | dummy data削除、権限確認 |
| C-07/C-08/C-09 | Lambda/OAuth/CloudFront | 4 API、state/PKCE/logout、401 | frontend/API公開停止 |
| C-10〜C-12 | Terraform/WAF/ALB | 17 module、cycleなし、region/TLS/log | Approval拒否 |
| C-13/C-14 | EKS auth/Flow Logs | Operator権限、実log entry | access/log設定修正 |
| C-15 | Monitoring | alarm/SNS通知 | subscription無効化 |
| C-16 | Pipeline | 未承認applyなし、同一binary plan | Pipeline停止 |

Category Cが未実施の場合、「構築済み」ではなく「静的検証済み・実行環境検証保留」と報告する。

### 付録A. Category C 保留検証一覧

本付録の全項目は **保留** である。Operator の明示承認、対象 AWS アカウント、必要な認証情報、承認済み Parameter Sheet、費用アラートを用意した後に、本書の該当手順で実施する。保留は静的検証の失敗を意味しないが、実環境での成立を保証するものでもない。

| 要件・AC | 検証対象 | 状態 | 保留理由 | 必要環境 | 未検証の残存リスク | 実施手順 |
| --- | --- | --- | --- | --- | --- | --- |
| Req 5.3 / 5.5 | Aurora migration、7業務table/constraint、失敗後の再実行 | 保留 | 実AuroraとVPC内ECS taskが必要 | 承認済みAWS、Aurora、ECS、migration image | 実DBでのSQL互換性、rollback/retry挙動 | 手順9 / C-01 |
| Req 6.3 / 6.4 / 6.7 | alarm/findingの実配送分離、5回失敗後の専用DLQ移動 | 保留 | 実EventBridge/SQS配送が必要 | 承認済みAWS、EventBridge、SQS、worker | 誤配送、再配送、redrive挙動 | 手順13 / C-02〜C-03 |
| Req 8.4 / 8.5 | EKS 3 workloadの300秒以内起動、image pull失敗検出 | 保留 | 実clusterとECR imageが必要 | 承認済みAWS、EKS、ECR、kubectl | Pod起動、pull、runtime設定 | 手順11 / C-04 |
| Req 9.2 | 5 imageのlinux/amd64 architecture | 保留 | Docker build/inspectを本フェーズで実行しない | Docker/buildx、5 image | Apple Silicon等で誤architectureをpushする可能性 | 手順8 / C-05 |
| Req 10.4 | A→BのS3/DynamoDB実書込みと再試行収束 | 保留 | 実S3/DynamoDB/IRSAが必要 | 承認済みAWS、EKS、S3、DynamoDB | 実権限、部分失敗、再試行時の収束 | 手順11・13 / C-06 |
| Req 11.4 | versioned S3 Lambda packageの実upload/invoke | 保留 | AWS artifact bucketとLambda invokeが必要 | 承認済みAWS、artifact bucket、Lambda | object version/hash連携、runtime依存 | 手順6・13 / C-07 |
| Req 13.7 | Cognitoでの実sign-inとportal 4 API応答 | 保留 | 実Cognito/CloudFront/APIが必要 | 承認済みAWS、browser、test user | callback、PKCE、token、CORS統合 | 手順12・13 / C-08 |
| Req 14.3 / 14.4 | CloudFront `/api/status` の200/401 | 保留 | 公開済みdistribution/APIが必要 | 承認済みAWS、有効/無効token | path転送、JWT authorizer、cache policy | 手順13 / C-09 |
| Req 15.3 / 16.4 / 17.2 / 18.2 | 実plan上のcycleなし、bucket名、WAF region、ALB log | 保留 | 実backend/providerによるplanを禁止しているため | 承認済みAWS、remote state、Terraform | account固有値とprovider解決後の差分 | 手順7・10 / C-10〜C-12 |
| Req 19.2 | ALB HTTP→HTTPS実redirect | 保留 | 実ALB/DNS/ACMが必要 | 承認済みAWS、ALB、ACM、DNS | listener/certificate/DNSの実統合 | 手順7・13 / C-12 |
| Req 20.4 | Operator roleの`kubectl auth can-i` | 保留 | 実EKS access entryが必要 | 承認済みAWS、EKS、Operator role、kubectl | principal紐付けとRBAC有効性 | 手順11 / C-13 |
| Req 21.2 | VPC Flow Logsの実log-stream entry | 保留 | 実VPC trafficとCloudWatch Logsが必要 | 承認済みAWS、VPC、CloudWatch Logs | 配送role、log group、traffic capture | 手順13 / C-14 |
| Req 22.4 | alarm state、SNS通知、subscription confirmation | 保留 | 実alarm/SNS endpointが必要 | 承認済みAWS、SNS、承認済みendpoint | 通知到達、PendingConfirmation、alarm遷移 | 手順13 / C-15 |
| Req 23.3 / 24.2 / 25.1 / 25.3 / 26.3 | remote backend、同一Terraform/provider、binary plan、入力一致 | 保留 | 実CodePipeline/CodeBuild実行が必要 | 承認済みAWS、Bootstrap/Pipeline、SSM入力 | plan/apply同一性、artifact受渡し、入力差異 | 手順4・5・7・10 / C-16 |

### 付録B. 静的・mock 検証の完了状態

- Verification A: 必須のPythonテスト514件、Node.js OAuthテスト4件、shell構文検査、Terraform `fmt -check`、Bootstrap・Dev Root・全17 moduleの`init -backend=false`/`validate`、機密情報パターンスキャン、差分品質検査に合格。
- Verification B: motoを使用するEventBridge/SQS分離とS3/DynamoDB収束テストを含め、実行可能なmock検証に合格。
- skip: Docker/testcontainersを要する任意schema smoke test 1件のみ。必要環境はDocker daemonとPostgreSQL testcontainerで、残存リスクは実Aurora/PostgreSQL上のmigration適用互換性が未確認であること。これはTask 11.1*の任意Category C相当であり、Verification Aの成功件数には含めない。
- P0: B-001〜B-024の24件は静的/mockレベルで解消済み。残存P0は0件。
- P1/P2: 静的/mockレベルの未解決実装項目は0件。上表のCategory C保留は実行環境での確認待ちであり、書面受容した未修正P1として扱わない。
- region: 原則`ap-northeast-1`。CLOUDFRONT scopeのWAFおよびそのlogging/KMSだけ`us-east-1`。
- 完了表現: **statically verified; real AWS plan, apply, and E2E are not performed**（静的検証済み。実AWSのplan、apply、E2Eは未実施）。

この結果は「AWS build is possible」という断定ではない。実AWS上の構築可否は、Operator承認後に付録Aを順番に実施し、すべて合格した時点で判定する。

### destroy前ファイル確認 BP-14-E01

| 項目 | 内容 |
| --- | --- |
| 対象ファイル | docs/operation/aws-resource-parameter-sheet.xlsx の 08_destroy前確認 |
| block/key | 順序1〜12、確認責任、停止条件 |
| placeholder例 | final snapshot識別子、保管判断、承認者 |
| 正となる値の取得元 | 実リソース、DB/Product/Security/Platform各owner |
| 編集完了条件 | 全12行の確認責任者と判断が記録済み。Secretなし |

### コマンド操作 BP-14-C01

| 項目 | 内容 |
| --- | --- |
| 目的 | コスト停止または完全撤去を依存の逆順で安全に実施する |
| 実行ディレクトリ | リポジトリルート |
| 前提条件 | Pipeline/deploy/migration停止、未処理queue確認、snapshot/ログ/object/image保持判断、破壊操作承認 |
| 正確なコマンド | 下記は順序例。各plan結果を再承認し、対象ARN/名前はoutputsで解決 |
| dry-run/plan確認 | kubectl deleteは事前get、S3/ECR削除はinventory、Terraformはplan -destroyを先行 |
| 成功時の期待結果 | workload停止→本体destroy→残存確認→Bootstrap最後、state保全 |
| 失敗時停止条件 | backup未確定、進行中job、未処理DLQ、bucketに要保管object、想定外destroy |
| 確認ログ/出力 | inventory、destroy plan、承認者、destroy summary、残存確認 |
| rollback方法 | destroy開始後の自動rollbackはない。snapshot/object/image/stateから承認付き再構築 |
| 次へ進める条件 | 各段階の残存確認が合格。Bootstrapは本体destroyとstate保存後のみ |

~~~bash
# 1. 現況確認（読み取り）
kubectl get deployment,cronjob,pod -n workers
aws ecs describe-services --region ap-northeast-1 \
  --cluster ＜cluster＞ --services ＜service＞

# 2. workload停止（承認後）
kubectl delete -f apps/eks-workers/k8s/30-monthly-summary-cronjob.yaml
kubectl delete -f apps/eks-workers/k8s/20-alarm-event-processor.yaml
kubectl delete -f apps/eks-workers/k8s/21-security-finding-worker.yaml
aws ssm put-parameter --region ap-northeast-1 --type String --overwrite \
  --name /ops-platform/dev/ecs-desired-count --value '0'
aws codepipeline start-pipeline-execution --name "$PIPELINE_NAME"

# 3. 本体destroy plan（Pipeline停止後、専用承認手順として実施）
terraform -chdir=infra/environments/dev init \
  -backend-config="bucket=$STATE_BUCKET"
terraform -chdir=infra/environments/dev plan -destroy -out=destroy.plan
terraform -chdir=infra/environments/dev show -no-color destroy.plan

# 破壊承認後のみ
terraform -chdir=infra/environments/dev apply destroy.plan

# 4. 本体destroy完了とstate保管を確認後、Bootstrap plan
terraform -chdir=bootstrap plan -destroy -out=bootstrap-destroy.plan
terraform -chdir=bootstrap show -no-color bootstrap-destroy.plan

# artifact/state bucket内の必要物を退避し、削除可能状態を確認して承認後のみ
terraform -chdir=bootstrap apply bootstrap-destroy.plan
~~~

S3 bucket、ECR repository、Aurora snapshot、Secrets Manager recovery windowなどによりdestroyが止まる場合、force_destroyやskip_final_snapshotを即時変更しない。Parameter Sheet 08のowner判断を取り直し、新しいdestroy planを作成する。us-east-1のWAF/log/KMSも残存確認対象であり、ap-northeast-1だけを見て完了としない。

## 完了報告テンプレート

- 対象account alias / region:
- commit SHA:
- Bootstrap execution / result:
- Infra Pipeline execution IDs（初回0台、最終1台、Cognito、Monitoring）:
- Lambda bucket/key/version/hash:
- 5 image URI/digest/architecture:
- migration task ARN / lastStatus / exitCode:
- ECS/EKS/Portal結果:
- Category C: 合格 / 不合格 / 保留（理由・必要環境・残存リスク）:
- コストアラート:
- 未解決事項:
- 実施していない操作:

この報告にaccess key、session token、password、Bearer token、実メール、Secret値を含めない。
