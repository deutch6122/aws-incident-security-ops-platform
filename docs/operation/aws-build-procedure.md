# AWS Incident & Security Ops Platform 詳細構築手順書

本書は、空の検証用 AWS アカウントから dev 完全構成を構築し、動作確認後に撤去するまでの唯一の実行順序を示す。対象リージョンは原則 ap-northeast-1、CloudFront 用 WAF のみ us-east-1 である。

> 実環境検証実績: 2026-09-07〜08 に検証用 AWS アカウントで、Bootstrap、本体 Pipeline、migration、ECS、EKS worker、Cognito ログイン、CloudFront Portal、サンプルデータ投入まで実施した。実行中に判明した不足は修正済みであり、本書にも反映している。ただし、別アカウントでの実行では必ず plan/dry-run と各承認ゲートを守る。

## 本書の使い方

- 実行順は「手順1」から「手順14」まで固定する。途中を飛ばさない。
- 最初に aws-resource-parameter-sheet.xlsx の先頭シート「構築前の必須確認」12項目だけを確認する。01〜08シートは参照台帳であり、全行レビューや全既定値の転記は不要である。
- 既定値を変更する場合、またはplanに想定外の差分が出た場合だけ、01〜08シートの該当行を参照する。Sheet の Build手順列の番号は、本書の手順番号と一致する。
- 実 ARN、12桁アカウント ID、実ドメイン、実メール、password/token/secret 値をリポジトリ・本書・実行ログへ転記しない。
- Terraform apply は、承認済み binary plan を CodePipeline の Apply stage が実行する。本体インフラをローカルから継続 apply しない。
- dry-run と plan が失敗した場合、後続操作へ進まない。修正後に同じ手順から再実行する。
- コードブロックは、特記がない限りリポジトリルートで上から順にコピーして実行できる。Terraform output、AWS CLI、SSMから取得できる値は手入力しない。
- コマンドブロック内の`＜...＞`は、利用者しか決められない初期入力、ブラウザから一時取得するtoken、任意の通知先に限る。AWSのID・ARN・URL・リソース名はTerraform output、SSM、AWS APIから自動取得する。
- チャットやMarkdownからURLをコピーすると `[URL](URL)` に変形する場合がある。SSMへ登録するJSONは文字列連結せず、必ず本書の`jq -cn`で生成する。

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

### シェルセッションの共通ルール

各作業日の最初に次を実行する。`AWS_PROFILE`だけは利用者のローカル設定名なので入力する。以後のコマンドは同じターミナルで実行する。

~~~bash
set -euo pipefail
export AWS_REGION=ap-northeast-1
printf '利用するAWS profile名: ' >&2
IFS= read -r AWS_PROFILE
export AWS_PROFILE

export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export COMMIT_SHA="$(git rev-parse HEAD)"
test "${#AWS_ACCOUNT_ID}" -eq 12
test "${#COMMIT_SHA}" -eq 40
aws sts get-caller-identity --query '{Account:Account,Arn:Arn}' --output table
~~~

途中で新しいターミナルを開いた場合は、必要な環境変数が消えているため、その手順の「取得」ブロックから再実行する。過去の画面出力からARNやIDをコピーしない。

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
set -euo pipefail
git status --short
if [[ -n "$(git status --porcelain)" ]]; then
  echo '未コミット変更があります。必要な変更をcommitまたはstashする方針を決めるまでbranchを切り替えません。' >&2
  exit 1
fi
git fetch --prune origin
git switch main
git pull --ff-only
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
git rev-parse HEAD
terraform version
aws --version
docker --version
kubectl version --client
python3 --version
jq --version
command -v envsubst
docker info >/dev/null
~~~

macOSで`envsubst: command not found`となった場合は、Homebrewでgettextを導入してから同じ確認を再実行する。

~~~bash
brew install gettext
export PATH="/opt/homebrew/opt/gettext/bin:$PATH"
command -v envsubst
~~~

毎回の設定を省きたい場合だけ、同じ`export PATH=...`を`.zshrc`へ一度追加する。上記ブロック自体は`.zshrc`を変更しないため、繰り返し実行しても重複行を作らない。

`docker info`が`Cannot connect to the Docker daemon`で失敗した場合はDocker Desktopを起動し、画面上でEngineがRunningになってから`docker info`を再実行する。

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
export AWS_REGION=ap-northeast-1
printf '利用する承認済みAWS profile名: ' >&2
IFS= read -r AWS_PROFILE
export AWS_PROFILE
aws sts get-caller-identity
test "$(aws sts get-caller-identity --query Account --output text)" != "None"
printf 'AWS_REGION=%s\nAWS_PROFILE=%s\n' "$AWS_REGION" "$AWS_PROFILE"
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

この編集は、先にBP-02-C02を実行してConnectionが`AVAILABLE`になった後に行う。手入力による転記ミスを防ぐため、次のコマンドでローカル専用ファイルを作る。GitHubの`owner/repository`だけを対話入力し、Connection ARNはBP-02-C02の結果を使う。

~~~bash
printf 'GitHub owner/repository（例: owner/repository）: ' >&2
IFS= read -r SOURCE_REPOSITORY_ID
export SOURCE_REPOSITORY_ID
export SOURCE_BRANCH=main
test -n "$SOURCE_REPOSITORY_ID"
test -n "$CODESTAR_CONNECTION_ARN"

umask 077
printf 'source_repository_id    = "%s"\nsource_branch           = "%s"\ncodestar_connection_arn = "%s"\n' \
  "$SOURCE_REPOSITORY_ID" "$SOURCE_BRANCH" "$CODESTAR_CONNECTION_ARN" \
  > bootstrap/terraform.tfvars

git check-ignore bootstrap/terraform.tfvars
terraform -chdir=bootstrap fmt
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
export AWS_REGION=ap-northeast-1
printf 'ALB APIドメイン（例: api.example.com）: ' >&2
IFS= read -r CERTIFICATE_DOMAIN
export CERTIFICATE_DOMAIN
test -n "$CERTIFICATE_DOMAIN"

# 既存のISSUED証明書があれば再利用し、なければ新規申請する。
export ALB_CERTIFICATE_ARN="$(aws acm list-certificates \
  --region "$AWS_REGION" \
  --certificate-statuses ISSUED \
  --query "CertificateSummaryList[?DomainName=='$CERTIFICATE_DOMAIN'].CertificateArn | [0]" \
  --output text)"

if [[ -z "$ALB_CERTIFICATE_ARN" || "$ALB_CERTIFICATE_ARN" == "None" ]]; then
  export ALB_CERTIFICATE_ARN="$(aws acm request-certificate \
    --region "$AWS_REGION" \
    --domain-name "$CERTIFICATE_DOMAIN" \
    --validation-method DNS \
    --query CertificateArn \
    --output text)"
fi

# 表示されたName/Valueを、対象ドメインのRoute 53 hosted zoneへCNAMEとして登録する。
aws acm describe-certificate \
  --region "$AWS_REGION" \
  --certificate-arn "$ALB_CERTIFICATE_ARN" \
  --query 'Certificate.DomainValidationOptions[].ResourceRecord' \
  --output table

# DNS登録後に実行する。ISSUEDになるまで手順3へ進まない。
aws acm wait certificate-validated \
  --region "$AWS_REGION" \
  --certificate-arn "$ALB_CERTIFICATE_ARN"
aws acm describe-certificate \
  --region "$AWS_REGION" \
  --certificate-arn "$ALB_CERTIFICATE_ARN" \
  --query 'Certificate.{Status:Status,DomainName:DomainName}' \
  --output table
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
export CONNECTION_REGION=us-east-1
export CONNECTION_NAME=ops-platform-dev-github

export CODESTAR_CONNECTION_ARN="$(aws codestar-connections list-connections \
  --region "$CONNECTION_REGION" \
  --provider-type-filter GitHub \
  --query "Connections[?ConnectionName=='$CONNECTION_NAME'].ConnectionArn | [0]" \
  --output text)"

if [[ -z "$CODESTAR_CONNECTION_ARN" || "$CODESTAR_CONNECTION_ARN" == "None" ]]; then
  export CODESTAR_CONNECTION_ARN="$(aws codestar-connections create-connection \
    --region "$CONNECTION_REGION" \
    --provider-type GitHub \
    --connection-name "$CONNECTION_NAME" \
    --query ConnectionArn \
    --output text)"
fi

printf 'Connection ARN: %s\n' "$CODESTAR_CONNECTION_ARN"
aws codestar-connections get-connection \
  --region "$CONNECTION_REGION" \
  --connection-arn "$CODESTAR_CONNECTION_ARN" \
  --query 'Connection.{Name:ConnectionName,Status:ConnectionStatus,Provider:ProviderType}' \
  --output table
~~~

新規接続は最初`PENDING`になる。AWS Consoleの「Developer Tools → Settings → Connections」でGitHub認可を完了し、最後の`get-connection`を再実行して`AVAILABLE`を確認する。`create-connection`とConsoleでの認可は同じ作業の前半・後半であり、どちらか一方だけでは完了しない。

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
set -euo pipefail
export AWS_REGION=ap-northeast-1
export COMMIT_SHA="$(git rev-parse HEAD)"

# 現在のshellに証明書ARNがない場合も、domain完全一致で取得する。
if [[ -z "${ALB_CERTIFICATE_ARN:-}" ]]; then
  printf 'ALB APIドメイン（例: api.example.com）: ' >&2
  IFS= read -r CERTIFICATE_DOMAIN
  export ALB_CERTIFICATE_ARN="$(aws acm list-certificates \
    --region "$AWS_REGION" \
    --certificate-statuses ISSUED \
    --query "CertificateSummaryList[?DomainName=='$CERTIFICATE_DOMAIN'].CertificateArn | [0]" \
    --output text)"
fi
export OPERATOR_PRINCIPAL_ARN="$(aws sts get-caller-identity --query Arn --output text)"

# STSの一時セッションARNはEKS access entry/trust policyへ直接登録できないため停止する。
if [[ "$OPERATOR_PRINCIPAL_ARN" == *":assumed-role/"* ]]; then
  echo "現在のArnはassumed-role sessionです。組織台帳のIAM role ARNを設定してください。" >&2
  return 1 2>/dev/null || exit 1
fi

# 現在の接続元IPを/32にする。VPN切替や固定IP要件がある場合は承認済みCIDRへ置き換える。
export OPERATOR_PUBLIC_IP="$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')"
export OPERATOR_CIDR="${OPERATOR_PUBLIC_IP}/32"
export ALB_INGRESS_CIDRS_JSON="$(jq -cn --arg cidr "$OPERATOR_CIDR" '[ $cidr ]')"
export EKS_PUBLIC_ACCESS_CIDRS_JSON="$ALB_INGRESS_CIDRS_JSON"
export MIGRATION_PRINCIPALS_JSON="$(jq -cn --arg arn "$OPERATOR_PRINCIPAL_ARN" '[ $arn ]')"
export COGNITO_CALLBACK_URLS_JSON="$(jq -cn '["http://localhost:5173/callback"]')"
export COGNITO_LOGOUT_URLS_JSON="$(jq -cn '["http://localhost:5173/"]')"

test "$ALB_CERTIFICATE_ARN" != "None"
aws acm describe-certificate --region "$AWS_REGION" \
  --certificate-arn "$ALB_CERTIFICATE_ARN" \
  --query 'Certificate.Status' --output text | grep -qx ISSUED
jq -e 'type=="array" and length>0' <<<"$ALB_INGRESS_CIDRS_JSON" >/dev/null
jq -e 'type=="array" and length>0' <<<"$MIGRATION_PRINCIPALS_JSON" >/dev/null

put_string_parameter() {
  aws ssm put-parameter --region "$AWS_REGION" --type String --overwrite \
    --name "$1" --value "$2" --query '{Version:Version,Tier:Tier}' --output json
}

put_string_parameter /ops-platform/dev/alb-certificate-arn "$ALB_CERTIFICATE_ARN"
put_string_parameter /ops-platform/dev/alb-ingress-cidrs "$ALB_INGRESS_CIDRS_JSON"
put_string_parameter /ops-platform/dev/eks-operator-principal-arn "$OPERATOR_PRINCIPAL_ARN"
put_string_parameter /ops-platform/dev/migration-launcher-principal-arns "$MIGRATION_PRINCIPALS_JSON"
put_string_parameter /ops-platform/dev/eks-public-access-cidrs "$EKS_PUBLIC_ACCESS_CIDRS_JSON"
put_string_parameter /ops-platform/dev/application-image-tag "$COMMIT_SHA"
put_string_parameter /ops-platform/dev/ecs-desired-count '0'
put_string_parameter /ops-platform/dev/cognito-callback-urls "$COGNITO_CALLBACK_URLS_JSON"
put_string_parameter /ops-platform/dev/cognito-logout-urls "$COGNITO_LOGOUT_URLS_JSON"
put_string_parameter /ops-platform/dev/cognito-keep-localhost-urls 'false'
put_string_parameter /ops-platform/dev/monitoring-enable-sns-subscription 'false'
put_string_parameter /ops-platform/dev/monitoring-notification-parameter-name \
  '/ops-platform/dev/monitoring-notification-endpoint'
put_string_parameter /ops-platform/dev/monitoring-notification-protocol 'email'

# URLがMarkdownリンクへ変形していないことを含め、全JSON値を検証する。
aws ssm get-parameter --region "$AWS_REGION" --name /ops-platform/dev/alb-ingress-cidrs \
  --query Parameter.Value --output text | jq -e . >/dev/null
aws ssm get-parameter --region "$AWS_REGION" --name /ops-platform/dev/cognito-callback-urls \
  --query Parameter.Value --output text | jq -e 'all(.[]; startswith("http"))' >/dev/null
aws ssm get-parameter --region "$AWS_REGION" --name /ops-platform/dev/cognito-logout-urls \
  --query Parameter.Value --output text | jq -e 'all(.[]; startswith("http"))' >/dev/null
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
export AWS_REGION=ap-northeast-1
export EKS_VERSION="$(awk -F'"' '/variable "eks_kubernetes_version"/{found=1} found && /default/{print $2; exit}' infra/environments/dev/variables.tf)"
test -n "$EKS_VERSION"

aws eks describe-cluster-versions \
  --region "$AWS_REGION" \
  --cluster-versions "$EKS_VERSION" \
  --include-all \
  --query 'clusterVersions[0].{Version:clusterVersion,Status:versionStatus,StandardSupportEnd:endOfStandardSupportDate,ExtendedSupportEnd:endOfExtendedSupportDate}' \
  --output table

test "$(aws eks describe-cluster-versions \
  --region "$AWS_REGION" \
  --cluster-versions "$EKS_VERSION" \
  --include-all \
  --query 'clusterVersions[0].versionStatus' \
  --output text)" = "STANDARD_SUPPORT"
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
set -euo pipefail
export PIPELINE_EXECUTION_ID="$(aws codepipeline start-pipeline-execution \
  --region "$AWS_REGION" \
  --name "$PIPELINE_NAME" \
  --query pipelineExecutionId --output text)"
printf 'PIPELINE_EXECUTION_ID=%s\n' "$PIPELINE_EXECUTION_ID"

# 今回のExecution IDのPlanだけを追跡し、成功まで待つ。
for attempt in {1..80}; do
  PLAN_ACTION_JSON="$(aws codepipeline list-action-executions \
    --region "$AWS_REGION" --pipeline-name "$PIPELINE_NAME" \
    --filter pipelineExecutionId="$PIPELINE_EXECUTION_ID" \
    --query "actionExecutionDetails[?stageName=='Plan' && actionName=='TerraformPlan'] | [0].{Status:status,BuildId:output.executionResult.externalExecutionId}" \
    --output json)"
  PLAN_STATUS="$(jq -r '.Status // "NotStarted"' <<<"$PLAN_ACTION_JSON")"
  printf 'Plan status=%s\n' "$PLAN_STATUS"
  case "$PLAN_STATUS" in
    Succeeded) break ;;
    Failed|Abandoned) echo 'Planが失敗しました。Approvalせずログを確認します。' >&2; exit 1 ;;
    *) sleep 15 ;;
  esac
done
test "$PLAN_STATUS" = "Succeeded"
export PLAN_BUILD_ID="$(jq -er '.BuildId' <<<"$PLAN_ACTION_JSON")"
export PLAN_LOG_GROUP="$(aws codebuild batch-get-builds --region "$AWS_REGION" \
  --ids "$PLAN_BUILD_ID" --query 'builds[0].logs.groupName' --output text)"
export PLAN_LOG_STREAM="$(aws codebuild batch-get-builds --region "$AWS_REGION" \
  --ids "$PLAN_BUILD_ID" --query 'builds[0].logs.streamName' --output text)"

aws logs get-log-events \
  --region "$AWS_REGION" \
  --log-group-name "$PLAN_LOG_GROUP" \
  --log-stream-name "$PLAN_LOG_STREAM" \
  --start-from-head --limit 10000 --output json |
  jq -r '.events[].message' |
  perl -pe 's/\e\[[0-9;]*m//g' |
  grep -E 'Plan:|No changes|will be destroyed|must be replaced|forces replacement'
~~~

validateがネットワーク/認証で失敗した場合は手順4と同じ記録項目を残し、未検証範囲がゼロになるまでApprovalしない。初回planでは Aurora/NAT/EKS/CloudFront と log retention、S3 force_destroy、Aurora deletion_protection/skip_final_snapshotを個別承認する。確認後、AWS Consoleで今回のExecution IDのManual Approvalを承認し、次を実行する。

~~~bash
while true; do
  PIPELINE_STATUS="$(aws codepipeline get-pipeline-execution \
    --region "$AWS_REGION" --pipeline-name "$PIPELINE_NAME" \
    --pipeline-execution-id "$PIPELINE_EXECUTION_ID" \
    --query 'pipelineExecution.status' --output text)"
  printf 'execution=%s status=%s\n' "$PIPELINE_EXECUTION_ID" "$PIPELINE_STATUS"
  case "$PIPELINE_STATUS" in
    Succeeded) break ;;
    Failed|Stopped|Superseded) echo 'Pipelineが正常終了していません。後続を停止します。' >&2; exit 1 ;;
    *) sleep 15 ;;
  esac
done
~~~

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
set -euo pipefail
export AWS_REGION=ap-northeast-1
export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export IMAGE_TAG="$(aws ssm get-parameter --region "$AWS_REGION" \
  --name /ops-platform/dev/application-image-tag --query Parameter.Value --output text)"
export ECR_REPOSITORIES_JSON="$(terraform -chdir=infra/environments/dev output -json ecr_repository_urls)"
export BACKEND_REPOSITORY_URL="$(jq -er '.["backend-api"]' <<<"$ECR_REPOSITORIES_JSON")"
export ALARM_REPOSITORY_URL="$(jq -er '.["alarm-event-processor"]' <<<"$ECR_REPOSITORIES_JSON")"
export FINDING_REPOSITORY_URL="$(jq -er '.["security-finding-worker"]' <<<"$ECR_REPOSITORIES_JSON")"
export SUMMARY_REPOSITORY_URL="$(jq -er '.["monthly-summary-cronjob"]' <<<"$ECR_REPOSITORIES_JSON")"
export MIGRATION_REPOSITORY_URL="$(jq -er '.["db-migration"]' <<<"$ECR_REPOSITORIES_JSON")"
export REGISTRY="${BACKEND_REPOSITORY_URL%%/*}"

test "$IMAGE_TAG" = "$(git rev-parse HEAD)"
docker info >/dev/null

printf '%s\n' \
  "$BACKEND_REPOSITORY_URL:$IMAGE_TAG" \
  "$ALARM_REPOSITORY_URL:$IMAGE_TAG" \
  "$FINDING_REPOSITORY_URL:$IMAGE_TAG" \
  "$SUMMARY_REPOSITORY_URL:$IMAGE_TAG" \
  "$MIGRATION_REPOSITORY_URL:$IMAGE_TAG"

aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "$REGISTRY"

docker build --platform linux/amd64 \
  -t "$BACKEND_REPOSITORY_URL:$IMAGE_TAG" apps/backend-api

docker build --platform linux/amd64 \
  -t "$ALARM_REPOSITORY_URL:$IMAGE_TAG" \
  -t "$FINDING_REPOSITORY_URL:$IMAGE_TAG" \
  -t "$SUMMARY_REPOSITORY_URL:$IMAGE_TAG" \
  apps/eks-workers

docker build --platform linux/amd64 \
  -f apps/db-migration/Dockerfile \
  -t "$MIGRATION_REPOSITORY_URL:$IMAGE_TAG" .

docker push "$BACKEND_REPOSITORY_URL:$IMAGE_TAG"
docker push "$ALARM_REPOSITORY_URL:$IMAGE_TAG"
docker push "$FINDING_REPOSITORY_URL:$IMAGE_TAG"
docker push "$SUMMARY_REPOSITORY_URL:$IMAGE_TAG"
docker push "$MIGRATION_REPOSITORY_URL:$IMAGE_TAG"

for repository_url in \
  "$BACKEND_REPOSITORY_URL" "$ALARM_REPOSITORY_URL" "$FINDING_REPOSITORY_URL" \
  "$SUMMARY_REPOSITORY_URL" "$MIGRATION_REPOSITORY_URL"; do
  aws ecr describe-images --region "$AWS_REGION" \
    --repository-name "${repository_url##*/}" \
    --image-ids imageTag="$IMAGE_TAG" \
    --query 'imageDetails[0].{Digest:imageDigest,PushedAt:imagePushedAt}' \
    --output table
done
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

失敗時は再実行せず、migrationログを確認する。CloudWatch Logsへの反映には数秒かかるため、次のコマンドはstreamが現れるまで最大1分待ってから最新ログを取得する。

~~~bash
export MIGRATION_LOG_GROUP="/ecs/ops-platform-dev-migration"
for attempt in {1..12}; do
  MIGRATION_LOG_STREAM="$(aws logs describe-log-streams \
    --region "$AWS_REGION" \
    --log-group-name "$MIGRATION_LOG_GROUP" \
    --order-by LastEventTime \
    --descending \
    --limit 1 \
    --query 'logStreams[0].logStreamName' \
    --output text)"
  [[ -n "$MIGRATION_LOG_STREAM" && "$MIGRATION_LOG_STREAM" != "None" ]] && break
  sleep 5
done
test -n "$MIGRATION_LOG_STREAM"
test "$MIGRATION_LOG_STREAM" != "None"

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
set -euo pipefail
export AWS_REGION=ap-northeast-1
export PIPELINE_NAME="${PIPELINE_NAME:-$(terraform -chdir=bootstrap output -raw codepipeline_name)}"

aws ssm put-parameter --region "$AWS_REGION" --type String --overwrite \
  --name /ops-platform/dev/ecs-desired-count --value '1'

export PIPELINE_EXECUTION_ID="$(aws codepipeline start-pipeline-execution \
  --region "$AWS_REGION" --name "$PIPELINE_NAME" \
  --query pipelineExecutionId --output text)"
printf 'PIPELINE_EXECUTION_ID=%s\n' "$PIPELINE_EXECUTION_ID"

for attempt in {1..80}; do
  PLAN_ACTION_JSON="$(aws codepipeline list-action-executions \
    --region "$AWS_REGION" --pipeline-name "$PIPELINE_NAME" \
    --filter pipelineExecutionId="$PIPELINE_EXECUTION_ID" \
    --query "actionExecutionDetails[?stageName=='Plan' && actionName=='TerraformPlan'] | [0].{Status:status,BuildId:output.executionResult.externalExecutionId}" \
    --output json)"
  PLAN_STATUS="$(jq -r '.Status // "NotStarted"' <<<"$PLAN_ACTION_JSON")"
  printf 'Plan status=%s\n' "$PLAN_STATUS"
  case "$PLAN_STATUS" in
    Succeeded) break ;;
    Failed|Abandoned) echo 'Planが失敗しました。Approvalせず停止します。' >&2; exit 1 ;;
    *) sleep 15 ;;
  esac
done
test "$PLAN_STATUS" = "Succeeded"

export PLAN_BUILD_ID="$(jq -er '.BuildId' <<<"$PLAN_ACTION_JSON")"
export PLAN_LOG_GROUP="$(aws codebuild batch-get-builds --region "$AWS_REGION" \
  --ids "$PLAN_BUILD_ID" --query 'builds[0].logs.groupName' --output text)"
export PLAN_LOG_STREAM="$(aws codebuild batch-get-builds --region "$AWS_REGION" \
  --ids "$PLAN_BUILD_ID" --query 'builds[0].logs.streamName' --output text)"
aws logs get-log-events --region "$AWS_REGION" \
  --log-group-name "$PLAN_LOG_GROUP" --log-stream-name "$PLAN_LOG_STREAM" \
  --start-from-head --limit 10000 --output json |
  jq -r '.events[].message' |
  perl -pe 's/\e\[[0-9;]*m//g' |
  grep -E 'Plan:|No changes|will be destroyed|must be replaced|forces replacement|aws_ecs_service'
~~~

Planが主にECS serviceの`desired_count: 0 -> 1`で、想定外のdestroy/replaceがないことを確認し、今回のExecution IDだけをManual Approvalで承認する。その後に次を実行する。

~~~bash
while true; do
  PIPELINE_STATUS="$(aws codepipeline get-pipeline-execution \
    --region "$AWS_REGION" --pipeline-name "$PIPELINE_NAME" \
    --pipeline-execution-id "$PIPELINE_EXECUTION_ID" \
    --query 'pipelineExecution.status' --output text)"
  printf 'execution=%s status=%s\n' "$PIPELINE_EXECUTION_ID" "$PIPELINE_STATUS"
  case "$PIPELINE_STATUS" in
    Succeeded) break ;;
    Failed|Stopped|Superseded) echo 'Applyが成功していません。後続を停止します。' >&2; exit 1 ;;
    *) sleep 15 ;;
  esac
done

export ECS_DEPLOYMENT_JSON="$(terraform -chdir=infra/environments/dev output -json ecs_deployment)"
export ECS_CLUSTER_NAME="$(jq -er '.cluster_name' <<<"$ECS_DEPLOYMENT_JSON")"
export ECS_SERVICE_NAME="$(jq -er '.service_name' <<<"$ECS_DEPLOYMENT_JSON")"
aws ecs wait services-stable --region "$AWS_REGION" \
  --cluster "$ECS_CLUSTER_NAME" --services "$ECS_SERVICE_NAME"
aws ecs describe-services --region "$AWS_REGION" \
  --cluster "$ECS_CLUSTER_NAME" --services "$ECS_SERVICE_NAME" \
  --query 'services[0].{Status:status,Desired:desiredCount,Running:runningCount,Pending:pendingCount}' \
  --output table
test "$(aws ecs describe-services --region "$AWS_REGION" \
  --cluster "$ECS_CLUSTER_NAME" --services "$ECS_SERVICE_NAME" \
  --query 'services[0].runningCount' --output text)" = "1"
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
| 目的 | CoreDNSがFargate上でReadyであることを確認し、EKS logging prerequisitesを先に適用し、その後3 workloadを配信する |
| 実行ディレクトリ | リポジトリルート |
| 前提条件 | EKS Standard Support再確認、5 image合格、Operator access確認、全env設定 |
| 正確なコマンド | 下記。最初はdry-run、その出力承認後に--execute |
| dry-run/plan確認 | render結果にplaceholderなし、CoreDNS確認、適用順00→40→10→20→21→30 |
| 成功時の期待結果 | 3 workloadが300秒以内にRunning/Job complete、image pull成功 |
| 失敗時停止条件 | CoreDNS Pending継続、auth can-i不一致、placeholder、ImagePullBackOff、logging ConfigMap欠落 |
| 確認ログ/出力 | rendered validation、rollout/job status、pod event、CloudWatch log stream |
| rollback方法 | 直前tagで再配信、Deploymentはrollout undo、CronJob停止。logging前提はworkload停止後に戻す |
| 次へ進める条件 | 3 workloadとCloudWatch logging、Operator権限が合格 |

~~~bash
set -euo pipefail
export AWS_REGION=ap-northeast-1
export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export IMAGE_TAG="$(aws ssm get-parameter --region "$AWS_REGION" \
  --name /ops-platform/dev/application-image-tag --query Parameter.Value --output text)"
export EKS_DEPLOYMENT_JSON="$(terraform -chdir=infra/environments/dev output -json eks_deployment)"
export ECR_REPOSITORIES_JSON="$(terraform -chdir=infra/environments/dev output -json ecr_repository_urls)"
export AURORA_JSON="$(terraform -chdir=infra/environments/dev output -json aurora)"
export MESSAGING_JSON="$(terraform -chdir=infra/environments/dev output -json messaging)"
export PORTAL_JSON="$(terraform -chdir=infra/environments/dev output -json portal_deployment)"

export EKS_CLUSTER="$(jq -er '.cluster_name' <<<"$EKS_DEPLOYMENT_JSON")"
export ALARM_ECR_REPO="$(jq -er '.["alarm-event-processor"]' <<<"$ECR_REPOSITORIES_JSON" | awk -F/ '{print $NF}')"
export FINDING_ECR_REPO="$(jq -er '.["security-finding-worker"]' <<<"$ECR_REPOSITORIES_JSON" | awk -F/ '{print $NF}')"
export SUMMARY_ECR_REPO="$(jq -er '.["monthly-summary-cronjob"]' <<<"$ECR_REPOSITORIES_JSON" | awk -F/ '{print $NF}')"
export EKS_ALARM_WORKER_ROLE_ARN="$(jq -er '.alarm_worker_role_arn' <<<"$EKS_DEPLOYMENT_JSON")"
export EKS_FINDING_WORKER_ROLE_ARN="$(jq -er '.finding_worker_role_arn' <<<"$EKS_DEPLOYMENT_JSON")"
export EKS_CRONJOB_ROLE_ARN="$(jq -er '.cronjob_role_arn' <<<"$EKS_DEPLOYMENT_JSON")"
export AURORA_CLUSTER_ID="$(jq -er '.cluster_id' <<<"$AURORA_JSON")"
export WORKER_DB_SECRET_ARN="$(aws rds describe-db-clusters --region "$AWS_REGION" \
  --db-cluster-identifier "$AURORA_CLUSTER_ID" \
  --query 'DBClusters[0].MasterUserSecret.SecretArn' --output text)"
export WORKER_DB_HOST="$(jq -er '.cluster_endpoint' <<<"$AURORA_JSON")"
export WORKER_DB_PORT="$(jq -er '.port' <<<"$AURORA_JSON")"
export WORKER_DB_NAME="$(jq -er '.database_name' <<<"$AURORA_JSON")"
export ALARM_QUEUE_URL="$(jq -er '.alarm_queue_url' <<<"$MESSAGING_JSON")"
export FINDING_QUEUE_URL="$(jq -er '.finding_queue_url' <<<"$MESSAGING_JSON")"
export WORKER_LOG_GROUP_NAME="$(jq -er '.worker_log_group_name' <<<"$EKS_DEPLOYMENT_JSON")"
export PORTAL_REPORTS_BUCKET="$(jq -er '.s3_bucket_name' <<<"$PORTAL_JSON")"
export PORTAL_REPORT_METADATA_TABLE="$(jq -er '.report_metadata_table_name' <<<"$PORTAL_JSON")"
export PORTAL_PUBLIC_STATUS_ITEMS_TABLE="$(jq -er '.public_status_table_name' <<<"$PORTAL_JSON")"

test "$WORKER_DB_SECRET_ARN" != "None"
printf '%s\n' \
  "IMAGE_TAG=$IMAGE_TAG" "EKS_CLUSTER=$EKS_CLUSTER" \
  "ALARM_ECR_REPO=$ALARM_ECR_REPO" "FINDING_ECR_REPO=$FINDING_ECR_REPO" \
  "SUMMARY_ECR_REPO=$SUMMARY_ECR_REPO" "WORKER_DB_HOST=$WORKER_DB_HOST" \
  "WORKER_DB_PORT=$WORKER_DB_PORT" "WORKER_DB_NAME=$WORKER_DB_NAME"

aws eks update-kubeconfig --region "$AWS_REGION" --name "$EKS_CLUSTER"
kubectl auth can-i get pods --namespace workers | grep -qx yes

scripts/deploy-eks.sh --tag "$IMAGE_TAG"

# dry-run承認後のみ。内部適用順:
# apps/eks-workers/k8s/00-namespace.yaml
# apps/eks-workers/k8s/40-fargate-logging.yaml
# apps/eks-workers/k8s/10-serviceaccounts.yaml
# apps/eks-workers/k8s/20-alarm-event-processor.yaml
# apps/eks-workers/k8s/21-security-finding-worker.yaml
# apps/eks-workers/k8s/30-monthly-summary-cronjob.yaml
scripts/deploy-eks.sh --tag "$IMAGE_TAG" --execute

scripts/deploy-eks.sh は --execute 時に、最初に `kube-system` の CoreDNS を確認する。CoreDNS が Ready でない場合は `deployment/coredns` を再起動し、Fargate profile に再スケジュールされるまで待機する。CoreDNS が Pending のまま worker を起動すると、Pod 内で `sts.ap-northeast-1.amazonaws.com` を名前解決できず、IRSA の認証情報取得前に CrashLoopBackOff になる。

kubectl rollout status deployment/alarm-event-processor -n workers --timeout=300s
kubectl rollout status deployment/security-finding-worker -n workers --timeout=300s
kubectl get pods -n workers
kubectl get cronjob -n workers

# Fargate Podが実際に使うEKS managed cluster SGからDB SGの5432へ許可があることを確認する。
export EKS_CLUSTER_SG_ID="$(aws eks describe-cluster \
  --region "$AWS_REGION" --name "$EKS_CLUSTER" \
  --query 'cluster.resourcesVpcConfig.clusterSecurityGroupId' --output text)"
export DB_SECURITY_GROUP_IDS_JSON="$(aws rds describe-db-clusters \
  --region "$AWS_REGION" --db-cluster-identifier "$AURORA_CLUSTER_ID" \
  --query 'DBClusters[0].VpcSecurityGroups[].VpcSecurityGroupId' --output json)"
jq -e 'type == "array" and length > 0' <<<"$DB_SECURITY_GROUP_IDS_JSON" >/dev/null
while IFS= read -r DB_SECURITY_GROUP_ID; do
  MATCHING_RULE_COUNT="$(aws ec2 describe-security-group-rules \
    --region "$AWS_REGION" \
    --filters "Name=group-id,Values=$DB_SECURITY_GROUP_ID" \
    --query "length(SecurityGroupRules[?ReferencedGroupInfo.GroupId=='$EKS_CLUSTER_SG_ID' && IpProtocol=='tcp' && FromPort==\`5432\` && ToPort==\`5432\`])" \
    --output text)"
  test "$MATCHING_RULE_COUNT" -ge 1
done < <(jq -r '.[]' <<<"$DB_SECURITY_GROUP_IDS_JSON")
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
set -euo pipefail
export AWS_REGION=ap-northeast-1
export PORTAL_JSON="$(terraform -chdir=infra/environments/dev output -json portal_deployment)"
export CLOUDFRONT_DOMAIN="$(jq -er '.cloudfront_distribution_domain' <<<"$PORTAL_JSON")"
export COGNITO_USER_POOL_ID="$(jq -er '.cognito_user_pool_id' <<<"$PORTAL_JSON")"
export COGNITO_APP_CLIENT_ID="$(jq -er '.cognito_app_client_id' <<<"$PORTAL_JSON")"
export COGNITO_CALLBACK_URLS_JSON="$(jq -cn --arg url "https://$CLOUDFRONT_DOMAIN/callback" '[ $url ]')"
export COGNITO_LOGOUT_URLS_JSON="$(jq -cn --arg url "https://$CLOUDFRONT_DOMAIN/" '[ $url ]')"

jq -e 'all(.[]; startswith("https://") and (contains("[")|not))' <<<"$COGNITO_CALLBACK_URLS_JSON" >/dev/null
jq -e 'all(.[]; startswith("https://") and (contains("[")|not))' <<<"$COGNITO_LOGOUT_URLS_JSON" >/dev/null

aws ssm put-parameter --region "$AWS_REGION" --type String --overwrite \
  --name /ops-platform/dev/cognito-callback-urls \
  --value "$COGNITO_CALLBACK_URLS_JSON"
aws ssm put-parameter --region "$AWS_REGION" --type String --overwrite \
  --name /ops-platform/dev/cognito-logout-urls \
  --value "$COGNITO_LOGOUT_URLS_JSON"
aws ssm put-parameter --region "$AWS_REGION" --type String --overwrite \
  --name /ops-platform/dev/cognito-keep-localhost-urls --value 'false'

export PIPELINE_NAME="${PIPELINE_NAME:-$(terraform -chdir=bootstrap output -raw codepipeline_name)}"
export PIPELINE_EXECUTION_ID="$(aws codepipeline start-pipeline-execution \
  --region "$AWS_REGION" --name "$PIPELINE_NAME" \
  --query pipelineExecutionId --output text)"
printf 'PIPELINE_EXECUTION_ID=%s\n' "$PIPELINE_EXECUTION_ID"

# 今回のCognito更新Planが完成するまで待ち、そのログだけを取得する。
for attempt in {1..80}; do
  PLAN_ACTION_JSON="$(aws codepipeline list-action-executions \
    --region "$AWS_REGION" --pipeline-name "$PIPELINE_NAME" \
    --filter pipelineExecutionId="$PIPELINE_EXECUTION_ID" \
    --query "actionExecutionDetails[?stageName=='Plan' && actionName=='TerraformPlan'] | [0].{Status:status,BuildId:output.executionResult.externalExecutionId}" \
    --output json)"
  PLAN_STATUS="$(jq -r '.Status // "NotStarted"' <<<"$PLAN_ACTION_JSON")"
  printf 'Plan status=%s\n' "$PLAN_STATUS"
  case "$PLAN_STATUS" in
    Succeeded) break ;;
    Failed|Abandoned) echo 'Planが失敗しました。Approvalせず停止します。' >&2; exit 1 ;;
    *) sleep 15 ;;
  esac
done
test "$PLAN_STATUS" = "Succeeded"

export PLAN_BUILD_ID="$(jq -er '.BuildId' <<<"$PLAN_ACTION_JSON")"
export PLAN_LOG_GROUP="$(aws codebuild batch-get-builds --region "$AWS_REGION" \
  --ids "$PLAN_BUILD_ID" --query 'builds[0].logs.groupName' --output text)"
export PLAN_LOG_STREAM="$(aws codebuild batch-get-builds --region "$AWS_REGION" \
  --ids "$PLAN_BUILD_ID" --query 'builds[0].logs.streamName' --output text)"
aws logs get-log-events --region "$AWS_REGION" \
  --log-group-name "$PLAN_LOG_GROUP" --log-stream-name "$PLAN_LOG_STREAM" \
  --start-from-head --limit 10000 --output json |
  jq -r '.events[].message' |
  perl -pe 's/\e\[[0-9;]*m//g' |
  grep -E 'Plan:|No changes|will be destroyed|must be replaced|forces replacement|cognito_user_pool_client|lambda_function'
~~~

ここで一度停止する。対象Execution IDのPlanを確認し、想定どおりCognito clientとLambdaのin-place更新だけで、destroy/replaceがない場合にManual Approvalを承認する。承認前に次の確認ブロックへ進まない。

~~~bash
# 承認後、同じExecution IDがSucceededになるまで待つ。
while true; do
  PIPELINE_STATUS="$(aws codepipeline get-pipeline-execution \
    --region "$AWS_REGION" --pipeline-name "$PIPELINE_NAME" \
    --pipeline-execution-id "$PIPELINE_EXECUTION_ID" \
    --query 'pipelineExecution.status' --output text)"
  printf 'execution=%s status=%s\n' "$PIPELINE_EXECUTION_ID" "$PIPELINE_STATUS"
  case "$PIPELINE_STATUS" in
    Succeeded) break ;;
    Failed|Stopped|Superseded) echo "Pipelineが正常終了していません。後続を停止します。" >&2; exit 1 ;;
    *) sleep 15 ;;
  esac
done

# Apply成功後、Cognito側の値が実URLになったことを確認する。
aws cognito-idp describe-user-pool-client \
  --region "$AWS_REGION" \
  --user-pool-id "$COGNITO_USER_POOL_ID" \
  --client-id "$COGNITO_APP_CLIENT_ID" \
  --query 'UserPoolClient.{CallbackURLs:CallbackURLs,LogoutURLs:LogoutURLs}' \
  --output json
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
set -euo pipefail
export AWS_REGION=ap-northeast-1
export PORTAL_JSON="$(terraform -chdir=infra/environments/dev output -json portal_deployment)"
export S3_BUCKET="$(jq -er '.s3_bucket_name' <<<"$PORTAL_JSON")"
export CLOUDFRONT_DISTRIBUTION_ID="$(jq -er '.cloudfront_distribution_id' <<<"$PORTAL_JSON")"
export CLOUDFRONT_DOMAIN="$(jq -er '.cloudfront_distribution_domain' <<<"$PORTAL_JSON")"
export COGNITO_USER_POOL_ID="$(jq -er '.cognito_user_pool_id' <<<"$PORTAL_JSON")"
export COGNITO_APP_CLIENT_ID="$(jq -er '.cognito_app_client_id' <<<"$PORTAL_JSON")"
export COGNITO_DOMAIN="$(jq -er '.cognito_hosted_domain' <<<"$PORTAL_JSON")"
export COGNITO_REDIRECT_URI="https://$CLOUDFRONT_DOMAIN/callback"
export COGNITO_LOGOUT_URI="https://$CLOUDFRONT_DOMAIN/"

scripts/deploy-frontend.sh

# dry-run承認後のみ
scripts/deploy-frontend.sh --execute

aws cloudfront wait distribution-deployed --id "$CLOUDFRONT_DISTRIBUTION_ID"
aws s3api head-object --region "$AWS_REGION" --bucket "$S3_BUCKET" --key callback \
  --query '{ContentType:ContentType,CacheControl:CacheControl}' --output json
aws s3api head-object --region "$AWS_REGION" --bucket "$S3_BUCKET" --key config.js \
  --query '{ContentType:ContentType,CacheControl:CacheControl}' --output json
curl -fsS "https://$CLOUDFRONT_DOMAIN/" | grep -q '<html'
~~~

`callback`は`text/html; charset=utf-8`、`config.js`は`application/javascript; charset=utf-8`、両方の`CacheControl`は`no-store`でなければならない。CloudFrontのルートURLが`AccessDenied`になる場合は`DefaultRootObject=index.html`が未反映なので、Pipeline Apply状態を確認する。

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
| 次へ進める条件 | main queueが0/0、DLQが投入前から増加しない、DynamoDB/S3にdummy dataが存在し、Portal画面またはAPIで200応答を確認 |

~~~bash
set -euo pipefail
export AWS_REGION=ap-northeast-1

# 初回だけPython実行環境を用意する。既存.venvがあれば再利用する。
test -d .venv || python3 -m venv .venv
source .venv/bin/activate
python3 -c 'import boto3' 2>/dev/null || python3 -m pip install 'boto3==1.38.23'
python3 -c 'import boto3; print(boto3.__version__)'

# Terraform outputから投入先を取得する。手入力でテーブル名・bucket名を写さない。
export PORTAL_REPORT_METADATA_TABLE="$(terraform -chdir=infra/environments/dev output -json portal_deployment | jq -r '.report_metadata_table_name')"
export PORTAL_PUBLIC_STATUS_ITEMS_TABLE="$(terraform -chdir=infra/environments/dev output -json portal_deployment | jq -r '.public_status_table_name')"
export PORTAL_REPORTS_BUCKET="$(terraform -chdir=infra/environments/dev output -json portal_deployment | jq -r '.s3_bucket_name')"
export ALARM_QUEUE_URL="$(terraform -chdir=infra/environments/dev output -json messaging | jq -r '.alarm_queue_url')"
export FINDING_QUEUE_URL="$(terraform -chdir=infra/environments/dev output -json messaging | jq -r '.finding_queue_url')"
export ALARM_DLQ_URL="$(terraform -chdir=infra/environments/dev output -json messaging | jq -r '.alarm_dlq_url')"
export FINDING_DLQ_URL="$(terraform -chdir=infra/environments/dev output -json messaging | jq -r '.finding_dlq_url')"

printf 'REPORT_METADATA_TABLE=%s\nPUBLIC_STATUS_TABLE=%s\nREPORTS_BUCKET=%s\n' \
  "$PORTAL_REPORT_METADATA_TABLE" "$PORTAL_PUBLIC_STATUS_ITEMS_TABLE" "$PORTAL_REPORTS_BUCKET"

# workerが起動済みであることを確認する。
kubectl rollout status deployment/alarm-event-processor -n workers --timeout=300s
kubectl rollout status deployment/security-finding-worker -n workers --timeout=300s
kubectl get pods -n workers

# DLQは過去失敗分が残っていてもよい。投入前後で増えないことを確認する。
export ALARM_DLQ_BEFORE="$(aws sqs get-queue-attributes \
  --region "$AWS_REGION" \
  --queue-url "$ALARM_DLQ_URL" \
  --attribute-names ApproximateNumberOfMessages \
  --query 'Attributes.ApproximateNumberOfMessages' \
  --output text)"
export FINDING_DLQ_BEFORE="$(aws sqs get-queue-attributes \
  --region "$AWS_REGION" \
  --queue-url "$FINDING_DLQ_URL" \
  --attribute-names ApproximateNumberOfMessages \
  --query 'Attributes.ApproximateNumberOfMessages' \
  --output text)"
printf 'ALARM_DLQ_BEFORE=%s\nFINDING_DLQ_BEFORE=%s\n' "$ALARM_DLQ_BEFORE" "$FINDING_DLQ_BEFORE"

# まずdry-runでpayloadがdummyであることを確認する。
python3 scripts/seed_alarm_events.py --region "$AWS_REGION"
python3 scripts/seed_finding_events.py --region "$AWS_REGION" --count 5
python3 scripts/seed_portal_reports.py --region "$AWS_REGION" --count 6 \
  --report-metadata-table "$PORTAL_REPORT_METADATA_TABLE" \
  --public-status-table "$PORTAL_PUBLIC_STATUS_ITEMS_TABLE" \
  --reports-bucket "$PORTAL_REPORTS_BUCKET"

# payload承認後のみ実投入する。
python3 scripts/seed_alarm_events.py --execute --region "$AWS_REGION"
python3 scripts/seed_finding_events.py --execute --region "$AWS_REGION" --count 5
python3 scripts/seed_portal_reports.py --execute --region "$AWS_REGION" --count 6 \
  --report-metadata-table "$PORTAL_REPORT_METADATA_TABLE" \
  --public-status-table "$PORTAL_PUBLIC_STATUS_ITEMS_TABLE" \
  --reports-bucket "$PORTAL_REPORTS_BUCKET"

# Product_B側に検証用データが入ったことを確認する。
aws dynamodb scan \
  --region "$AWS_REGION" \
  --table-name "$PORTAL_REPORT_METADATA_TABLE" \
  --select COUNT
aws dynamodb scan \
  --region "$AWS_REGION" \
  --table-name "$PORTAL_PUBLIC_STATUS_ITEMS_TABLE" \
  --select COUNT
aws s3 ls "s3://$PORTAL_REPORTS_BUCKET/reports/" \
  --region "$AWS_REGION" \
  --recursive

# EventBridge→SQS→worker処理が詰まっていないことを確認する。
# SQSの件数は概算で反映に時間がかかるため、最大3分待つ。
for attempt in {1..18}; do
  ALARM_VISIBLE="$(aws sqs get-queue-attributes --region "$AWS_REGION" \
    --queue-url "$ALARM_QUEUE_URL" --attribute-names ApproximateNumberOfMessages \
    --query 'Attributes.ApproximateNumberOfMessages' --output text)"
  ALARM_INFLIGHT="$(aws sqs get-queue-attributes --region "$AWS_REGION" \
    --queue-url "$ALARM_QUEUE_URL" --attribute-names ApproximateNumberOfMessagesNotVisible \
    --query 'Attributes.ApproximateNumberOfMessagesNotVisible' --output text)"
  FINDING_VISIBLE="$(aws sqs get-queue-attributes --region "$AWS_REGION" \
    --queue-url "$FINDING_QUEUE_URL" --attribute-names ApproximateNumberOfMessages \
    --query 'Attributes.ApproximateNumberOfMessages' --output text)"
  FINDING_INFLIGHT="$(aws sqs get-queue-attributes --region "$AWS_REGION" \
    --queue-url "$FINDING_QUEUE_URL" --attribute-names ApproximateNumberOfMessagesNotVisible \
    --query 'Attributes.ApproximateNumberOfMessagesNotVisible' --output text)"
  printf 'attempt=%s alarm=%s/%s finding=%s/%s\n' \
    "$attempt" "$ALARM_VISIBLE" "$ALARM_INFLIGHT" "$FINDING_VISIBLE" "$FINDING_INFLIGHT"
  [[ "$ALARM_VISIBLE/$ALARM_INFLIGHT/$FINDING_VISIBLE/$FINDING_INFLIGHT" == "0/0/0/0" ]] && break
  sleep 10
done

test "$ALARM_VISIBLE/$ALARM_INFLIGHT/$FINDING_VISIBLE/$FINDING_INFLIGHT" = "0/0/0/0"
aws sqs get-queue-attributes \
  --region "$AWS_REGION" \
  --queue-url "$ALARM_QUEUE_URL" \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible
aws sqs get-queue-attributes \
  --region "$AWS_REGION" \
  --queue-url "$FINDING_QUEUE_URL" \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible

export ALARM_DLQ_AFTER="$(aws sqs get-queue-attributes \
  --region "$AWS_REGION" \
  --queue-url "$ALARM_DLQ_URL" \
  --attribute-names ApproximateNumberOfMessages \
  --query 'Attributes.ApproximateNumberOfMessages' \
  --output text)"
export FINDING_DLQ_AFTER="$(aws sqs get-queue-attributes \
  --region "$AWS_REGION" \
  --queue-url "$FINDING_DLQ_URL" \
  --attribute-names ApproximateNumberOfMessages \
  --query 'Attributes.ApproximateNumberOfMessages' \
  --output text)"
printf 'ALARM_DLQ_BEFORE=%s ALARM_DLQ_AFTER=%s\n' "$ALARM_DLQ_BEFORE" "$ALARM_DLQ_AFTER"
printf 'FINDING_DLQ_BEFORE=%s FINDING_DLQ_AFTER=%s\n' "$FINDING_DLQ_BEFORE" "$FINDING_DLQ_AFTER"
test "$ALARM_DLQ_BEFORE" = "$ALARM_DLQ_AFTER"
test "$FINDING_DLQ_BEFORE" = "$FINDING_DLQ_AFTER"
~~~

#### Security Hub CRITICAL Findingの実経路確認（BP-13-C02-SH）

この確認はSecurity Hubを既に有効化しているdevアカウントでのみ行う。Security Hubの有効化や標準の有効化には料金が発生し得るため、本手順から自動有効化しない。`describe-hub`が失敗した場合は停止し、費用承認後に別途有効化する。

最初のブロックは設定確認だけでAWSリソースを変更しない。2つ目の`batch-import-findings`は検証用Findingを実際に1件作るため、Operator承認後だけ実行する。

~~~bash
set -euo pipefail
export AWS_REGION=ap-northeast-1
export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export MESSAGING_JSON="$(terraform -chdir=infra/environments/dev output -json messaging)"
export SECURITYHUB_RULE_ARN="$(jq -er '.securityhub_critical_event_rule_arn' <<<"$MESSAGING_JSON")"
export SECURITYHUB_RULE_NAME="${SECURITYHUB_RULE_ARN##*/}"
export PORTAL_PUBLIC_STATUS_ITEMS_TABLE="$(terraform -chdir=infra/environments/dev output -json portal_deployment | jq -er '.public_status_table_name')"

# Security Hubが有効であることと、CRITICAL ruleが有効であることを確認する。
aws securityhub describe-hub --region "$AWS_REGION" \
  --query '{HubArn:HubArn,AutoEnable:AutoEnable}' --output table
aws events describe-rule --region "$AWS_REGION" --name "$SECURITYHUB_RULE_NAME" \
  --query '{Name:Name,State:State,EventPattern:EventPattern}' --output json

# 実イベントを作らず、rule patternがCRITICALに一致しHIGHには一致しないことを確認する。
export SECURITYHUB_EVENT_PATTERN="$(aws events describe-rule \
  --region "$AWS_REGION" --name "$SECURITYHUB_RULE_NAME" \
  --query EventPattern --output text)"
export TEST_EVENT_CRITICAL='{"id":"00000000-0000-0000-0000-000000000001","account":"111122223333","source":"aws.securityhub","time":"2026-01-01T00:00:00Z","region":"ap-northeast-1","resources":[],"detail-type":"Security Hub Findings - Imported","detail":{"findings":[{"Severity":{"Label":"CRITICAL"}}]}}'
export TEST_EVENT_HIGH='{"id":"00000000-0000-0000-0000-000000000002","account":"111122223333","source":"aws.securityhub","time":"2026-01-01T00:00:00Z","region":"ap-northeast-1","resources":[],"detail-type":"Security Hub Findings - Imported","detail":{"findings":[{"Severity":{"Label":"HIGH"}}]}}'
test "$(aws events test-event-pattern --region "$AWS_REGION" \
  --event-pattern "$SECURITYHUB_EVENT_PATTERN" --event "$TEST_EVENT_CRITICAL" \
  --query Result --output text)" = "True"
test "$(aws events test-event-pattern --region "$AWS_REGION" \
  --event-pattern "$SECURITYHUB_EVENT_PATTERN" --event "$TEST_EVENT_HIGH" \
  --query Result --output text)" = "False"
~~~

Operator承認後、次のブロックでdev用CRITICAL Findingを投入する。実在の顧客・端末・脆弱性情報は入れない。

~~~bash
set -euo pipefail
export TEST_FINDING_SUFFIX="$(date -u +%Y%m%dT%H%M%SZ)"
export TEST_FINDING_TIME="$(date -u +%Y-%m-%dT%H:%M:%S.000Z)"
export SECURITYHUB_PRODUCT_ARN="arn:aws:securityhub:${AWS_REGION}:${AWS_ACCOUNT_ID}:product/${AWS_ACCOUNT_ID}/default"
export TEST_FINDING_ID="${SECURITYHUB_PRODUCT_ARN}/finding/ops-platform-dev-critical-${TEST_FINDING_SUFFIX}"

jq -n \
  --arg schema "2018-10-08" \
  --arg finding_id "$TEST_FINDING_ID" \
  --arg product_arn "$SECURITYHUB_PRODUCT_ARN" \
  --arg account_id "$AWS_ACCOUNT_ID" \
  --arg region "$AWS_REGION" \
  --arg timestamp "$TEST_FINDING_TIME" \
  '[{
    SchemaVersion: $schema,
    Id: $finding_id,
    ProductArn: $product_arn,
    GeneratorId: "ops-platform-dev-verification",
    AwsAccountId: $account_id,
    Types: ["Software and Configuration Checks/Security Best Practices"],
    CreatedAt: $timestamp,
    UpdatedAt: $timestamp,
    Severity: {Label: "CRITICAL"},
    Title: "DEV verification CRITICAL Security Hub finding",
    Description: "Non-sensitive dev verification finding.",
    Resources: [{
      Type: "AwsAccount",
      Id: ("AWS::::Account:" + $account_id),
      Partition: "aws",
      Region: $region
    }],
    Workflow: {Status: "NEW"},
    RecordState: "ACTIVE"
  }]' > /tmp/ops-platform-securityhub-test-finding.json

aws securityhub batch-import-findings --region "$AWS_REGION" \
  --findings file:///tmp/ops-platform-securityhub-test-finding.json \
  --query '{SuccessCount:SuccessCount,FailedCount:FailedCount,FailedFindings:FailedFindings}' \
  --output json

# EventBridge→SQS→Workerの反映を最大3分待つ。
for attempt in {1..18}; do
  PORTAL_MATCH_COUNT="$(aws dynamodb scan \
    --region "$AWS_REGION" --table-name "$PORTAL_PUBLIC_STATUS_ITEMS_TABLE" \
    --filter-expression 'finding_id = :finding_id AND severity = :severity' \
    --expression-attribute-values "{\":finding_id\":{\"S\":\"$TEST_FINDING_ID\"},\":severity\":{\"S\":\"critical\"}}" \
    --select COUNT --query Count --output text)"
  printf 'attempt=%s portal_match_count=%s\n' "$attempt" "$PORTAL_MATCH_COUNT"
  [[ "$PORTAL_MATCH_COUNT" -ge 1 ]] && break
  sleep 10
done
test "$PORTAL_MATCH_COUNT" -ge 1

# Portalで同じタイトルが表示されることをCognitoログイン後に確認する。
printf 'Portal確認対象: %s\n' "$TEST_FINDING_ID"
~~~

確認後に検証Findingを閉じる場合は次を実行する。Portal表示項目は監査用に残すか、`finding_id`を条件に特定してから明示承認のうえ削除する。

~~~bash
aws securityhub batch-update-findings --region "$AWS_REGION" \
  --finding-identifiers "Id=$TEST_FINDING_ID,ProductArn=$SECURITYHUB_PRODUCT_ARN" \
  --workflow Status=RESOLVED \
  --record-state ARCHIVED
~~~

Frontendから確認する場合は、CloudFront URLでログイン後に`/status.html`と`/reports.html`を開き、一覧が表示されることを確認する。CLIでAPIを直接確認する場合は、ブラウザ開発者ツール等で取得した有効なCognito tokenを一時変数に入れ、Secretやtokenを作業記録へ残さない。

~~~bash
export CLOUDFRONT_DOMAIN="$(terraform -chdir=infra/environments/dev output -json portal_deployment | jq -er '.cloudfront_distribution_domain')"
export PORTAL_TOKEN='＜browser-session-token-not-recorded＞'

curl -fsS "https://$CLOUDFRONT_DOMAIN/api/status" \
  -H "Authorization: Bearer $PORTAL_TOKEN" | jq .
curl -fsS "https://$CLOUDFRONT_DOMAIN/api/reports" \
  -H "Authorization: Bearer $PORTAL_TOKEN" | jq .

unset PORTAL_TOKEN
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
set -euo pipefail
export AWS_REGION=ap-northeast-1
export PIPELINE_NAME="${PIPELINE_NAME:-$(terraform -chdir=bootstrap output -raw codepipeline_name)}"
printf '通知先（画面へ表示しません）: ' >&2
IFS= read -r -s MONITORING_NOTIFICATION_ENDPOINT
printf '\n'
test -n "$MONITORING_NOTIFICATION_ENDPOINT"

aws ssm put-parameter --region "$AWS_REGION" --type SecureString --overwrite \
  --name /ops-platform/dev/monitoring-notification-endpoint \
  --value "$MONITORING_NOTIFICATION_ENDPOINT" \
  --query '{Version:Version,Tier:Tier}' --output json
unset MONITORING_NOTIFICATION_ENDPOINT
aws ssm put-parameter --region "$AWS_REGION" --type String --overwrite \
  --name /ops-platform/dev/monitoring-enable-sns-subscription --value 'true'
aws ssm put-parameter --region "$AWS_REGION" --type String --overwrite \
  --name /ops-platform/dev/monitoring-notification-protocol --value 'email'

export PIPELINE_EXECUTION_ID="$(aws codepipeline start-pipeline-execution \
  --region "$AWS_REGION" --name "$PIPELINE_NAME" \
  --query pipelineExecutionId --output text)"
printf 'PIPELINE_EXECUTION_ID=%s\n' "$PIPELINE_EXECUTION_ID"

for attempt in {1..80}; do
  PLAN_ACTION_JSON="$(aws codepipeline list-action-executions \
    --region "$AWS_REGION" --pipeline-name "$PIPELINE_NAME" \
    --filter pipelineExecutionId="$PIPELINE_EXECUTION_ID" \
    --query "actionExecutionDetails[?stageName=='Plan' && actionName=='TerraformPlan'] | [0].{Status:status,BuildId:output.executionResult.externalExecutionId}" \
    --output json)"
  PLAN_STATUS="$(jq -r '.Status // "NotStarted"' <<<"$PLAN_ACTION_JSON")"
  printf 'Plan status=%s\n' "$PLAN_STATUS"
  case "$PLAN_STATUS" in
    Succeeded) break ;;
    Failed|Abandoned) echo 'Planが失敗しました。Approvalせず停止します。' >&2; exit 1 ;;
    *) sleep 15 ;;
  esac
done
test "$PLAN_STATUS" = "Succeeded"

export PLAN_BUILD_ID="$(jq -er '.BuildId' <<<"$PLAN_ACTION_JSON")"
export PLAN_LOG_GROUP="$(aws codebuild batch-get-builds --region "$AWS_REGION" \
  --ids "$PLAN_BUILD_ID" --query 'builds[0].logs.groupName' --output text)"
export PLAN_LOG_STREAM="$(aws codebuild batch-get-builds --region "$AWS_REGION" \
  --ids "$PLAN_BUILD_ID" --query 'builds[0].logs.streamName' --output text)"
aws logs get-log-events --region "$AWS_REGION" \
  --log-group-name "$PLAN_LOG_GROUP" --log-stream-name "$PLAN_LOG_STREAM" \
  --start-from-head --limit 10000 --output json |
  jq -r '.events[].message' |
  perl -pe 's/\e\[[0-9;]*m//g' |
  grep -E 'Plan:|No changes|will be destroyed|must be replaced|forces replacement|aws_sns_topic_subscription'
~~~

Planが想定したSNS subscription追加だけでdestroy/replaceがないことを確認し、今回のExecution IDをManual Approvalで承認する。承認後はBP-12-C01と同じ`get-pipeline-execution`の待機ブロックを実行して`Succeeded`を確認する。email/email-json subscriptionのconfirmationはCategory Cである。未確認でもSNS subscriptionはPendingConfirmationとなり、Terraform構成の作成自体を失敗扱いにしない。ただし通知到達テストは合格にできない。

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

### 付録A. Category C 実環境検証記録

当初は全項目を保留としていたが、2026-09-07〜08のdev構築で下表の「実施済み」を確認した。新しいアカウントで再構築する場合、この実績を流用して合格扱いにはせず、Operatorの承認後に同じ手順で再確認する。「一部保留」「保留」は未確認範囲を示す。

| 要件・AC | 検証対象 | 状態 | 保留理由 | 必要環境 | 未検証の残存リスク | 実施手順 |
| --- | --- | --- | --- | --- | --- | --- |
| Req 5.3 / 5.5 | Aurora migration、7業務table/constraint、失敗後の再実行 | 実施済み | 2026-09-08にECS one-off migrationがexitCode=0 | 承認済みAWS、Aurora、ECS、migration image | 新環境では再実行が必要 | 手順9 / C-01 |
| Req 6.3 / 6.4 / 6.7 | alarm/findingの実配送分離、5回失敗後の専用DLQ移動 | 一部実施済み | 実配送分離、worker処理、再投入後のDLQ増加なしを確認。5回境界の意図的失敗試験は未完 | 承認済みAWS、EventBridge、SQS、worker | redrive回数境界の再確認 | 手順13 / C-02〜C-03 |
| Req 8.4 / 8.5 | EKS 3 workloadの300秒以内起動、image pull失敗検出 | 実施済み | CoreDNS修正後、2 DeploymentがRunning、CronJob作成済み | 承認済みAWS、EKS、ECR、kubectl | 新環境では再実行が必要 | 手順11 / C-04 |
| Req 9.2 | 5 imageのlinux/amd64 architecture | 実施済み | 5 imageをlinux/amd64でbuild/push | Docker/buildx、5 image | 新しいtagごとの誤architecture | 手順8 / C-05 |
| Req 10.4 | A→BのS3/DynamoDB実書込みと再試行収束 | 実施済み | seed後、S3とDynamoDB各6件、main queue 0/0、DLQ増加なし | 承認済みAWS、EKS、S3、DynamoDB | 新環境では再実行が必要 | 手順11・13 / C-06 |
| Req 11.4 | versioned S3 Lambda packageの実upload/invoke | 実施済み | VersionId/hash一致とPortal API応答を確認 | 承認済みAWS、artifact bucket、Lambda | 新packageごとの整合 | 手順6・13 / C-07 |
| Req 13.7 | Cognitoでの実sign-inとportal 4 API応答 | 実施済み | Hosted UIログイン、callback、ページ遷移、一覧・詳細表示を確認 | 承認済みAWS、browser、test user | 新domain/clientでは再実行が必要 | 手順12・13 / C-08 |
| Req 14.3 / 14.4 | CloudFront `/api/status` の200/401 | 実施済み | 未認証401と、認証後status/reports表示を確認 | 承認済みAWS、有効/無効token | cache/policy変更後は再確認 | 手順13 / C-09 |
| Req 15.3 / 16.4 / 17.2 / 18.2 | 実plan上のcycleなし、bucket名、WAF region、ALB log | 実施済み | remote backendのPlan/Apply成功、WAF/ALBを含む構築成功 | 承認済みAWS、remote state、Terraform | 新account固有値で再確認 | 手順7・10 / C-10〜C-12 |
| Req 19.2 | ALB HTTP→HTTPS実redirect | 実施済み | ACM ISSUEDとALB HTTPS構成を実Apply | 承認済みAWS、ALB、ACM、DNS | 独自DNSのend-to-end到達は環境ごとに確認 | 手順7・13 / C-12 |
| Req 20.4 | Operator roleの`kubectl auth can-i` | 実施済み | Operatorからkubeconfig更新とworkload操作を確認 | 承認済みAWS、EKS、Operator role、kubectl | principal変更時のRBAC | 手順11 / C-13 |
| Req 21.2 | VPC Flow Logsの実log-stream entry | 保留 | 実log-stream entryの証跡を今回の作業記録で未取得 | 承認済みAWS、VPC、CloudWatch Logs | 配送role、traffic capture | 手順13 / C-14 |
| Req 22.4 | alarm state、SNS通知、subscription confirmation | 保留 | 実alarm/SNS endpointが必要 | 承認済みAWS、SNS、承認済みendpoint | 通知到達、PendingConfirmation、alarm遷移 | 手順13 / C-15 |
| Req 23.3 / 24.2 / 25.1 / 25.3 / 26.3 | remote backend、同一Terraform/provider、binary plan、入力一致 | 実施済み | 複数回のCodePipelineで同一Execution IDのPlan/Approval/Apply成功を確認 | 承認済みAWS、Bootstrap/Pipeline、SSM入力 | Pipeline変更後は再確認 | 手順4・5・7・10 / C-16 |

### 付録B. 静的・mock 検証の完了状態

- Verification A: 必須のPythonテスト514件、Node.js OAuthテスト4件、shell構文検査、Terraform `fmt -check`、Bootstrap・Dev Root・全17 moduleの`init -backend=false`/`validate`、機密情報パターンスキャン、差分品質検査に合格。
- Verification B: motoを使用するEventBridge/SQS分離とS3/DynamoDB収束テストを含め、実行可能なmock検証に合格。
- skip: Docker/testcontainersを要する任意schema smoke test 1件のみ。必要環境はDocker daemonとPostgreSQL testcontainerで、残存リスクは実Aurora/PostgreSQL上のmigration適用互換性が未確認であること。これはTask 11.1*の任意Category C相当であり、Verification Aの成功件数には含めない。
- P0: B-001〜B-024の24件は静的/mockレベルで解消済み。残存P0は0件。
- P1/P2: 静的/mockレベルの未解決実装項目は0件。上表のCategory C保留は実行環境での確認待ちであり、書面受容した未修正P1として扱わない。
- region: 原則`ap-northeast-1`。CLOUDFRONT scopeのWAFおよびそのlogging/KMSだけ`us-east-1`。
- 完了表現: **statically verified and live-tested on the dev AWS account on 2026-09-07/08; Flow Logs evidence and SNS delivery remain pending**（静的検証およびdev実環境の主要E2Eを実施済み。Flow Logsの証跡取得とSNS通知到達は保留）。

この実績は別アカウント・別時点の無条件な成功を保証しない。再構築時はOperator承認後に付録Aを順番に実施し、その環境の結果を改めて記録する。

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

以下は完全撤去用であり、データを戻せない操作を含む。Parameter Sheet 08の承認後、ブロック単位で実行する。

#### BP-14-C01-A 現況取得とworkload停止

~~~bash
set -euo pipefail
export AWS_REGION=ap-northeast-1
export STATE_BUCKET="$(terraform -chdir=bootstrap output -raw state_bucket_name)"
export ARTIFACT_BUCKET="$(terraform -chdir=bootstrap output -raw artifact_bucket_name)"
export PIPELINE_NAME="$(terraform -chdir=bootstrap output -raw codepipeline_name)"

terraform -chdir=infra/environments/dev init \
  -input=false -lockfile=readonly -reconfigure \
  -backend-config="bucket=$STATE_BUCKET"

export ECS_DEPLOYMENT_JSON="$(terraform -chdir=infra/environments/dev output -json ecs_deployment)"
export ECS_CLUSTER_NAME="$(jq -er '.cluster_name' <<<"$ECS_DEPLOYMENT_JSON")"
export ECS_SERVICE_NAME="$(jq -er '.service_name' <<<"$ECS_DEPLOYMENT_JSON")"

kubectl get deployment,cronjob,pod -n workers || true
aws ecs describe-services --region "$AWS_REGION" \
  --cluster "$ECS_CLUSTER_NAME" --services "$ECS_SERVICE_NAME" \
  --query 'services[0].{Status:status,Desired:desiredCount,Running:runningCount}' --output table
aws codepipeline list-pipeline-executions --region "$AWS_REGION" \
  --pipeline-name "$PIPELINE_NAME" --max-results 5 \
  --query 'pipelineExecutionSummaries[].{ID:pipelineExecutionId,Status:status}' --output table

# 破壊承認後のみ。存在しない場合のNotFoundは無視する。
kubectl delete cronjob monthly-summary-cronjob -n workers --ignore-not-found
kubectl delete deployment alarm-event-processor security-finding-worker \
  -n workers --ignore-not-found
~~~

Pipelineに`InProgress`があれば、その実行を承認・Applyせず停止する。停止対象IDは直前の一覧からコピーし、別実行を止めない。

~~~bash
printf '停止するInProgress execution ID（なければ空Enter）: ' >&2
IFS= read -r PIPELINE_EXECUTION_TO_STOP
if [[ -n "$PIPELINE_EXECUTION_TO_STOP" ]]; then
  aws codepipeline stop-pipeline-execution \
    --region "$AWS_REGION" --pipeline-name "$PIPELINE_NAME" \
    --pipeline-execution-id "$PIPELINE_EXECUTION_TO_STOP" \
    --abandon --reason 'Approved full teardown'
fi
~~~

#### BP-14-C01-B destroy専用入力を自動生成する

`terraform destroy`でも必須variableの型検査が行われる。`yes`や`y`を入力してはいけない。現在のSSMとTerraform stateから値を取得し、Git管理外の一時ファイルを作る。

~~~bash
set -euo pipefail
export ALB_CERTIFICATE_ARN="$(aws ssm get-parameter --region "$AWS_REGION" \
  --name /ops-platform/dev/alb-certificate-arn --query Parameter.Value --output text)"
export EKS_OPERATOR_PRINCIPAL_ARN="$(aws ssm get-parameter --region "$AWS_REGION" \
  --name /ops-platform/dev/eks-operator-principal-arn --query Parameter.Value --output text)"
export MIGRATION_LAUNCHER_TRUSTED_PRINCIPAL_ARNS="$(aws ssm get-parameter --region "$AWS_REGION" \
  --name /ops-platform/dev/migration-launcher-principal-arns --query Parameter.Value --output text)"

export LAMBDA_STATE_FILE="$(mktemp "${TMPDIR:-/tmp}/ops-platform-lambda-state.XXXXXX")"
terraform -chdir=infra/environments/dev state show -no-color \
  module.lambda.aws_lambda_function.portal > "$LAMBDA_STATE_FILE"
export LAMBDA_PACKAGE_S3_BUCKET="$(awk -F' = ' '/^[[:space:]]*s3_bucket[[:space:]]*=/{gsub(/\"/,\"\",$2); print $2}' "$LAMBDA_STATE_FILE")"
export LAMBDA_PACKAGE_S3_KEY="$(awk -F' = ' '/^[[:space:]]*s3_key[[:space:]]*=/{gsub(/\"/,\"\",$2); print $2}' "$LAMBDA_STATE_FILE")"
export LAMBDA_PACKAGE_S3_OBJECT_VERSION="$(awk -F' = ' '/^[[:space:]]*s3_object_version[[:space:]]*=/{gsub(/\"/,\"\",$2); print $2}' "$LAMBDA_STATE_FILE")"
export LAMBDA_SOURCE_CODE_HASH="$(awk -F' = ' '/^[[:space:]]*source_code_hash[[:space:]]*=/{gsub(/\"/,\"\",$2); print $2}' "$LAMBDA_STATE_FILE")"

for required_value in \
  "$ALB_CERTIFICATE_ARN" "$EKS_OPERATOR_PRINCIPAL_ARN" \
  "$LAMBDA_PACKAGE_S3_BUCKET" "$LAMBDA_PACKAGE_S3_KEY" \
  "$LAMBDA_PACKAGE_S3_OBJECT_VERSION" "$LAMBDA_SOURCE_CODE_HASH"; do
  test -n "$required_value"
done
jq -e 'type=="array" and length>0' <<<"$MIGRATION_LAUNCHER_TRUSTED_PRINCIPAL_ARNS" >/dev/null

jq -n \
  --arg alb_certificate_arn "$ALB_CERTIFICATE_ARN" \
  --arg eks_operator_principal_arn "$EKS_OPERATOR_PRINCIPAL_ARN" \
  --argjson migration_launcher_trusted_principal_arns "$MIGRATION_LAUNCHER_TRUSTED_PRINCIPAL_ARNS" \
  --arg lambda_package_s3_bucket "$LAMBDA_PACKAGE_S3_BUCKET" \
  --arg lambda_package_s3_key "$LAMBDA_PACKAGE_S3_KEY" \
  --arg lambda_package_s3_object_version "$LAMBDA_PACKAGE_S3_OBJECT_VERSION" \
  --arg lambda_source_code_hash "$LAMBDA_SOURCE_CODE_HASH" \
  '{
    alb_certificate_arn: $alb_certificate_arn,
    eks_operator_principal_arn: $eks_operator_principal_arn,
    migration_launcher_trusted_principal_arns: $migration_launcher_trusted_principal_arns,
    lambda_package_s3_bucket: $lambda_package_s3_bucket,
    lambda_package_s3_key: $lambda_package_s3_key,
    lambda_package_s3_object_version: $lambda_package_s3_object_version,
    lambda_source_code_hash: $lambda_source_code_hash,
    portal_bucket_force_destroy: true,
    alb_access_logs_force_destroy: true
  }' > infra/environments/dev/destroy.auto.tfvars.json

jq 'keys' infra/environments/dev/destroy.auto.tfvars.json
if ! git check-ignore -q infra/environments/dev/destroy.auto.tfvars.json; then
  echo '[warning] destroy.auto.tfvars.jsonはGit除外されていません。git addせず、destroy完了後に本手順で削除します。' >&2
fi
git status --short infra/environments/dev/destroy.auto.tfvars.json
~~~

`portal_bucket_force_destroy=true`と`alb_access_logs_force_destroy=true`は、両bucket内の全versionを削除する。保存が必要ならここで停止する。

#### BP-14-C01-C ECR imageを空にして本体をdestroyする

ECR repositoryはimageが1件でもあるとTerraformから削除できないため、承認後に5 repositoryのimageを先に削除する。

~~~bash
set -euo pipefail
export ECR_REPOSITORIES_JSON="$(terraform -chdir=infra/environments/dev output -json ecr_repository_urls)"
for repository_url in $(jq -r '.[]' <<<"$ECR_REPOSITORIES_JSON"); do
  repository_name="${repository_url##*/}"
  image_ids="$(aws ecr list-images --region "$AWS_REGION" \
    --repository-name "$repository_name" --query imageIds --output json)"
  if [[ "$(jq 'length' <<<"$image_ids")" -gt 0 ]]; then
    aws ecr batch-delete-image --region "$AWS_REGION" \
      --repository-name "$repository_name" --image-ids "$image_ids" >/dev/null
  fi
  test "$(aws ecr list-images --region "$AWS_REGION" \
    --repository-name "$repository_name" --query 'length(imageIds)' --output text)" = "0"
done

# 古いplanは使わず、最新stateから作り直す。
rm -f infra/environments/dev/destroy.plan
terraform -chdir=infra/environments/dev plan \
  -input=false -destroy -out=destroy.plan
terraform -chdir=infra/environments/dev show -no-color destroy.plan
~~~

表示内容を再承認した直後にだけ次を実行する。plan作成後にPipelineや別Terraform操作を実行すると`Saved plan is stale`になるため、その場合は適用せず直前のplan作成からやり直す。

~~~bash
terraform -chdir=infra/environments/dev apply -input=false destroy.plan
terraform -chdir=infra/environments/dev state list
~~~

最後の`state list`が空でなければBootstrapを削除しない。残ったresourceとエラーを確認し、新しいdestroy planを作る。

#### BP-14-C01-D Bootstrapを最後にdestroyする

BootstrapにはTerraform state、Pipeline artifact、IAM、KMS、CodeBuild、CodePipelineが含まれる。state/artifact bucketを空にすると復元手段を失うため、完全削除の承認後だけ実行する。

~~~bash
set -euo pipefail
terraform -chdir=bootstrap state list
terraform -chdir=bootstrap plan -destroy -out=bootstrap-destroy.plan
terraform -chdir=bootstrap show -no-color bootstrap-destroy.plan
~~~

bucketのversionとdelete markerを完全削除する関数を定義し、対象を名前で限定して空にする。

~~~bash
empty_versioned_bucket() {
  local bucket_name="$1"
  local delete_payload
  while true; do
    delete_payload="$(aws s3api list-object-versions --region "$AWS_REGION" \
      --bucket "$bucket_name" --output json |
      jq '{Objects: ([((.Versions // [])[]), ((.DeleteMarkers // [])[])] | map({Key,VersionId})), Quiet: true}')"
    [[ "$(jq '.Objects | length' <<<"$delete_payload")" -eq 0 ]] && break
    aws s3api delete-objects --region "$AWS_REGION" --bucket "$bucket_name" \
      --delete "$delete_payload" >/dev/null
  done
}

printf '完全削除対象: %s %s\n' "$ARTIFACT_BUCKET" "$STATE_BUCKET"
printf '上記2bucketの全versionを削除する場合だけ DELETE と入力: ' >&2
IFS= read -r CONFIRM_BOOTSTRAP_BUCKET_DELETE
test "$CONFIRM_BOOTSTRAP_BUCKET_DELETE" = "DELETE"
empty_versioned_bucket "$ARTIFACT_BUCKET"
empty_versioned_bucket "$STATE_BUCKET"
~~~

bucketを空にした後は、先ほど保存したBootstrap planを速やかに適用する。Bootstrapがlocal stateを使っていることを確認してから行う。

~~~bash
terraform -chdir=bootstrap apply -input=false bootstrap-destroy.plan
terraform -chdir=bootstrap state list
rm -f infra/environments/dev/destroy.auto.tfvars.json \
  infra/environments/dev/destroy.plan \
  bootstrap/bootstrap-destroy.plan \
  bootstrap/bootstrap.plan
git status --short
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
