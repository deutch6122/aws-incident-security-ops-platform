# AWS構築トラブルシューティング・ポートフォリオ

## 1. この資料について

2026-09-07〜08に、AWS Incident & Security Ops Platformを空のdev環境へ構築し、動作確認後に撤去した際のエラーと改善を記録する。単なる失敗一覧ではなく、設計・IaC・CI/CD・アプリ・運用手順を一つずつ実環境でつなぎ、再現可能な手順へ育てた過程を示すポートフォリオである。

- 対象: Terraform、AWS CodePipeline/CodeBuild、IAM/KMS、ECS/EKS、Aurora、S3/CloudFront、Cognito、Lambda、EventBridge/SQS、Portal
- 根拠: 実行時のエラー出力、修正コミット、再plan/apply、E2E確認
- セキュリティ: アクセスキー、session token、password、Bearer token、実メールは記録しない。ARN、ID、ドメインも例示用表記へ置き換える。
- 最終到達点: migration `exitCode=0`、Pipeline Apply成功、ECS/EKS稼働、Cognitoログイン、Portal一覧・詳細表示、SQS処理完了、DLQ新規増加なし

## 2. エラー対応サマリー

| 分類 | 主な件数 | 得られた改善 |
| --- | ---: | --- |
| ローカル準備・入力 | 7 | 必須ツール、Docker、SSM JSON、実値取得を事前検査へ追加 |
| Pipeline・Terraform・IAM | 15 | 最小権限を実API単位で補完し、Plan/Applyの同一性と確認手順を標準化 |
| migration・ECS・EKS | 10 | image tag、RDS managed secret、CoreDNS、SG、manifest型を実環境に合わせて修正 |
| Portal・データ連携 | 7 | OAuth session、CloudFront、Lambda proxy、EventBridge envelope、画面項目を修正 |
| destroy | 5 | 必須変数、versioned S3、ECR image、stale planを考慮した完全撤去手順へ改訂 |
| 追加照合で回収した問い合わせ | 5 | branch/PR状態、EKS version、Logs、SG診断の曖昧さを解消 |

合計49件を記録した。

## 3. エラー対応表

### 3.1 ローカル準備・入力

| ID | エラー内容・見え方 | 原因 | 修正ファイル名 | 修正内容 | 確認方法 |
| --- | --- | --- | --- | --- | --- |
| T-01 | `zsh: command not found: envsubst` | Kubernetes YAMLの変数置換に使うgettextがmacOSへ未導入だった。 | `docs/operation/aws-build-procedure.md` | `brew install gettext`、PATH設定、`command -v envsubst`を事前確認へ追加した。 | 手順1で`command -v envsubst`がパスを返す。 |
| T-02 | `Cannot connect to the Docker daemon` | Docker CLIは入っていたがDocker DesktopのEngineが停止していた。 | `docs/operation/aws-build-procedure.md` | バージョン確認だけでなく`docker info`を前提検査に追加した。 | `docker info`が成功してからbuildへ進む。 |
| T-03 | ACM証明書が`PENDING_VALIDATION`のまま | 証明書申請だけでは発行されず、ACMが示すCNAMEを対象Hosted Zoneへ登録する必要があった。 | `docs/operation/aws-build-procedure.md` | 証明書ARNの自動取得、CNAME表示、`aws acm wait certificate-validated`、`ISSUED`確認を一連の手順にした。 | `describe-certificate`で`ISSUED`と対象domainを確認する。 |
| T-04 | CodeStar ConnectionのCLI作成とConsole操作の違いが不明 | CLIは接続枠を作るだけで、GitHub認可はConsoleで完了する二段階作業だった。 | `docs/operation/aws-build-procedure.md` | `PENDING`作成、Console認可、`AVAILABLE`確認を一つの手順として説明した。 | `get-connection`が`AVAILABLE`を返す。 |
| T-05 | Parameter Sheetの全行を埋める必要があるように見えた | 参照台帳、事前入力、apply後output、Secretの区別が曖昧だった。 | `docs/operation/aws-build-procedure.md`、`docs/operation/aws-resource-parameter-sheet.xlsx` | 先頭シートの必須確認だけを入口とし、自動生成値は事前転記しない方針へ整理した。 | 必須確認の状態と、実値の正がSSM/Terraform outputで一致する。 |
| T-06 | SSMのCognito URLが`[https://...](https://...)`になった | チャット画面がURLをMarkdownリンクへ変換し、その表示文字列をコピーした。JSONとしては有効でもURLとして不正だった。 | `docs/operation/aws-build-procedure.md` | URL配列を`jq -cn --arg url ... '[ $url ]'`で生成し、`contains("[")`検査を追加した。 | SSM値を`jq -e`へ通し、各要素が純粋な`https://` URLであることを確認する。 |
| T-07 | `bootstrap/bootstrap.plan`や`destroy.plan`が未追跡で残った | Terraform binary planはローカル一時成果物だが、削除・Git管理の扱いが手順に不足していた。 | `docs/operation/aws-build-procedure.md` | planとdestroy用tfvarsを`git add`しないこと、状態を明示確認すること、終了時に対象ファイルだけを削除する手順を追加した。 | `git status --short`で誤追加がないことを確認し、destroy完了後に一時ファイルが削除済みである。 |

### 3.2 Pipeline・Terraform・IAM/KMS

| ID | エラー内容・見え方 | 原因 | 修正ファイル名 | 修正内容 | 確認方法 |
| --- | --- | --- | --- | --- | --- |
| T-08 | CodeBuildが`YAML_FILE_ERROR: Expected Commands[0] to be of string type`でDOWNLOAD_SOURCE中に失敗 | buildspecのコマンドにあるコロン等をYAMLがmapとして解釈した。 | `bootstrap/buildspec/buildspec.yml`、`bootstrap/buildspec/buildspec-plan.yml` | 複雑なコマンドをYAML block scalarへ変更した。 | CIのbuildspec静的テストとPipeline Fmt成功。commit `198984b`。 |
| T-09 | Lambda package metadata取得でJMESPathエラー | `source-code-hash`のハイフンを`Metadata.source-code-hash`と書き、式として正しく参照できなかった。 | `bootstrap/buildspec/buildspec.yml`、`bootstrap/buildspec/buildspec-apply.yml`、`bootstrap/tests/test_buildspec.py` | `head-object`全体をJSON取得し、`jq -r '.Metadata["source-code-hash"]'`で読むよう変更。空・不一致の明示エラーも追加した。 | `Lambda package integrity check: OK`を確認。commit `8ba893c`。 |
| T-10 | terraform-exec-roleがPlan artifactを読めない | CodeBuild roleからAssumeRoleしたterraform-exec-roleに、artifact bucketのlist/getとKMS decryptがなかった。 | `bootstrap/iam.tf`、`bootstrap/tests/test_iam_least_privilege.py` | artifact bucket/list、object read、artifact KMS decrypt/describeを対象bucket/keyへ限定して追加した。 | Plan stageがartifactを読んで成功。commit `15e9032`。 |
| T-11 | `s3:GetBucketObjectLockConfiguration`のAccessDeniedでPlan失敗 | S3 bucket refresh時にAWS ProviderがObject Lock設定を読むが、実行roleに権限がなかった。途中では誤ったAction名も使っていた。 | `bootstrap/iam.tf`、`bootstrap/tests/test_iam_least_privilege.py` | 正式Action `s3:GetBucketObjectLockConfiguration`をbucket権限へ追加した。 | Portal/ALB log bucketのrefreshを含むPlan成功。commit `2d18af2`。 |
| T-12 | BootstrapのIAM managed policyが大きく、変更管理も困難 | Terraform実行roleの多サービス権限を一つのpolicyへ集約していた。 | `bootstrap/iam.tf` | IAM/KMS等を用途別policyへ分割し、サイズ制限とレビュー性を改善した。 | Bootstrap plan/applyとIAM静的テスト成功。commit `12f94fa`。 |
| T-13 | Aurora/WAF/EKS/Lambda/Flow Logs作成中に複数の`AccessDenied` | 静的設計時には見えなかった作成時API、PassRole、Logs resource policy、KMS操作が不足していた。 | `bootstrap/iam.tf`、`bootstrap/tests/test_iam_least_privilege.py` | `logs:DescribeLogGroups`、限定PassRole、KMS key/alias管理、必要なservice APIをSid別に追加した。 | 再Bootstrap apply後、Plan→Applyを繰り返して不足APIが消えた。commits `b3b87a8`、`0384dae`。 |
| T-14 | `kms:TagResource` AccessDeniedでAurora用KMS keyを作れない | CreateKey時のタグ付けは独立した権限評価を受けるが、既存key管理権限だけでは足りなかった。 | `bootstrap/iam.tf`、`bootstrap/tests/test_iam_least_privilege.py` | devリージョンの新規keyに対し、許可tag keyとProject/Envを条件に`kms:TagResource`を追加した。 | 実IAM policy versionとApply成功を確認。commits `9892159`、`f0aa5e5`。 |
| T-15 | EKS Fargate Profile作成時に`missing permissions for iam:GetRole` | EKSがFargate用Service Linked Roleの存在を確認・作成するAPI権限が不足した。service名とrole ARN末尾の扱いもAWS実挙動とずれた。 | `bootstrap/iam.tf`、`bootstrap/tests/test_iam_least_privilege.py` | `iam:GetRole`と`iam:CreateServiceLinkedRole`をFargate SLR用途に限定し、必要最小限のARNパターンへ合わせた。 | Fargate Profile作成成功。commits `531173a`、`f0aa5e5`、`6f896d6`、`0384dae`。 |
| T-16 | WAF CloudWatch Log Group作成で「KMS key does not exist or is not allowed」 | us-east-1のLogs serviceとterraform-exec-roleが、WAF用KMS keyを利用できるkey policyになっていなかった。 | `infra/modules/waf/main.tf`、`infra/modules/waf/tests/test_waf_snapshot.py`、`bootstrap/iam.tf` | Logs serviceの暗号化利用、Terraformの関連付け用Describe、log delivery resource policy操作を追加した。 | WAF logging configuration作成成功。commits `531173a`、`6f896d6`、`cc79fd3`。 |
| T-17 | RDS managed master secret作成時にSecrets Manager/KMS AccessDenied | RDSが`rds!cluster-*`名のSecretを代理作成し、AWS managed Secrets Manager KMS keyも確認する挙動をIAMへ反映できていなかった。 | `bootstrap/iam.tf`、`bootstrap/tests/test_iam_least_privilege.py` | RDS生成名に限定したCreateSecret/TagResourceと、`alias/aws/secretsmanager`に限定したDescribeKeyを追加した。 | Aurora cluster作成とmanaged secret生成成功。commits `cc79fd3`、`f421b35`。 |
| T-18 | ECS/migration/EKS workerがDB Secretを復号できない | Secret取得権限はあったが、Customer Managed KMS keyのDecrypt権限がruntime roleになかった。 | `infra/modules/iam/main.tf`、`infra/modules/eks/main.tf`、各variables/tests、`infra/environments/dev/main.tf` | DB用keyだけを、`kms:ViaService=secretsmanager.<region>.amazonaws.com`条件付きでDecrypt可能にした。 | runtimeからSecret取得後にDB接続成功。commit `72d0ad4`。 |
| T-19 | Planのたびに5 Security Groupが更新扱いになる | inline ruleと個別`aws_vpc_security_group_*_rule`が同じSGを管理し、Providerが互いを差分として戻していた。 | `infra/modules/network/main.tf`、README、tests | SG本体とruleの所有を分離し、SG本体側でrule差分を再調整しないlifecycleへ変更した。 | 再planで不要なSG差分が消えた。commit `0acd73a`。 |
| T-20 | EKS clusterが`bootstrap_cluster_creator_admin_permissions`差分で置換予定になった | 初回作成時の設定をTerraform resourceが保持しておらず、`true -> null`がForceNewになった。 | `infra/modules/eks/main.tf`、`infra/modules/eks/tests/test_eks_static.py` | 作成時のbootstrap admin設定を明示的に維持した。 | Planが`0 to destroy`となりcluster置換が消えた。commit `d525009`。 |
| T-21 | `terraform fmt -check`がWAF main.tfでexit code 3 | 機能修正後のTerraform整形が未実施だった。 | `infra/modules/waf/main.tf` | `terraform fmt`を適用し、CIのfmt gateを通した。 | PRの`terraform fmt + validate`成功。commit `e4a7d2c`。 |
| T-22 | `get-pipeline-state`でApproval/Applyが別Execution IDを示し、現在状況を誤認しやすい | APIは各stageの最新実行を返すため、古いApply結果と新しいPlan結果が同じ表に並ぶ。 | `docs/operation/aws-build-procedure.md` | start時のExecution IDを保存し、各stageのExecution ID一致を確認するルールとPlanログ取得コマンドを追加した。 | 全stageが同じExecution IDでSucceededになる。 |

### 3.3 migration・ECS・EKS

| ID | エラー内容・見え方 | 原因 | 修正ファイル名 | 修正内容 | 確認方法 |
| --- | --- | --- | --- | --- | --- |
| T-23 | ECR pushで`repository ... does not exist` | 初回本体Applyより先にimageをpushし、ECR repositoryがまだ作られていなかった。 | `docs/operation/aws-build-procedure.md` | 手順順序を「初回Apply→Terraform outputで5 repository取得→build/push」に固定した。 | `ecr_repository_urls`取得後、全5 digestが返る。 |
| T-24 | migrationが`CannotPullContainerError ... tag not found` | SSMのapplication image tag、ECRのtag、ECS task definitionのtagが一致していなかった。過去tagを手作業で付け替える必要が生じた。 | `docs/operation/aws-build-procedure.md`、`scripts/deploy-migration.sh` | SSM tagとECR image、task definitionの実imageを実行前に比較し、不一致ならPipelineでtask definitionを更新するgateを追加した。 | dry-run前の`test "$ACTUAL_MIGRATION_IMAGE" = "$EXPECTED_MIGRATION_IMAGE"`が成功。 |
| T-25 | migration taskが`Essential container in task exited`、`exitCode=1` | RDS managed master secretにはusername/passwordしかなく、アプリがhost/port/dbnameもSecret内にある前提だった。 | `apps/db-migration/run_migration.py`、Backend/workerのconfig・db/secrets・session、ECS/EKS variables/manifests、tests | host/port/dbnameを非機微な環境変数からfallbackし、Secretは認証情報だけでも扱えるようにした。 | 新imageをbuild/pushし、task definition revision更新後、migration `exitCode=0`。commit `3797b70`。 |
| T-26 | `terraform output`で`Backend initialization required` | dev rootがS3 remote backendを使うのに、ローカル作業ディレクトリを正しいbucketでinitしていなかった。 | `docs/operation/aws-build-procedure.md` | Bootstrapの`state_bucket_name`を取得し、`init -reconfigure -backend-config=bucket=...`を各ローカル操作の前に追加した。 | dev rootの`terraform output -json`が成功。 |
| T-27 | `network_foundation output not found` | 手順で実在しないoutput名を推測していた。実装は`network`、`eks_deployment`等のまとまったoutputを提供していた。 | `docs/operation/aws-build-procedure.md` | output名を実ファイルに合わせ、SGはEKS API/ENIまたは正式outputから取得するよう変更した。 | `terraform output -json`の実在keyだけで値を自動設定できる。 |
| T-28 | `deploy-eks.sh: missing required environment variable(s): ALARM_ECR_REPO ...` | EKS配信に必要な値を手順書で手入力させ、設定漏れが起きた。 | `docs/operation/aws-build-procedure.md` | `eks_deployment`、`ecr_repository_urls`、`aurora`、`messaging`、`portal_deployment`から全変数を自動取得するブロックへ置換した。 | dry-runが全image/clusterを表示し、missing envなし。 |
| T-29 | Kubernetes APIが`cannot unmarshal number into ... EnvVar.value of type string` | `WORKER_DB_PORT=5432`がenvsubst後にYAML数値となり、Kubernetes EnvVar.valueの文字列型と合わなかった。 | `apps/eks-workers/k8s/20-alarm-event-processor.yaml`、`21-security-finding-worker.yaml`、`30-monthly-summary-cronjob.yaml`、tests | `value: "${WORKER_DB_PORT}"`と引用符を付けた。 | 3 manifestの`kubectl apply`成功。commit `063f765`。 |
| T-30 | worker PodがPending/CrashLoopBackOffし、STSやAWS endpointを名前解決できない | all-Fargate clusterでCoreDNS PodがFargate Profile作成前の状態に残っていた。 | `scripts/deploy-eks.sh`、`scripts/tests/test_deploy_scripts.py`、手順書 | worker適用前にCoreDNS rolloutを確認し、未Readyならrestartして最大300秒待つ処理を追加した。 | CoreDNS Ready後、worker 2 DeploymentがRunning。commit `2966dd3`。 |
| T-31 | workerがSQS messageを処理できず、main queueからDLQへ移動した | EventBridgeからSQSへ届くmessageは`detail`を持つEnvelopeだが、workerは直接業務JSONが届く前提だった。またfindingの`workflow_state`を読んでいなかった。 | `apps/eks-workers/workers/alarm.py`、`finding.py`、`sqs.py`、tests | EventBridge Envelopeを展開し、直接JSONとの両方を受理。処理失敗時の可視性も明確化した。 | 再seed後main queue 0/0、DLQ件数が投入前後で不変。commit `4ab096e`。 |
| T-32 | workerがAuroraへ接続できず、SQS messageが処理中/再試行になった | Fargate PodのENIにはTerraformで想定したEKS用SGではなく、EKS managed cluster SGが付いていた。DB SG ingressが実送信元SGを許可していなかった。 | `infra/environments/dev/main.tf`、`infra/modules/eks/outputs.tf`、tests | EKS cluster SG IDをoutputし、DB SGへPostgreSQL/5432のSG参照ingressを追加した。 | `describe-security-group-rules`でcluster SG→DB SG:5432を確認し、queueが0/0。commit `1d0db06`。 |

### 3.4 Portal・認証・データ表示

| ID | エラー内容・見え方 | 原因 | 修正ファイル名 | 修正内容 | 確認方法 |
| --- | --- | --- | --- | --- | --- |
| T-33 | CloudFrontのルート`/`が`AccessDenied`だが`/index.html`は開く | DistributionにDefault Root Objectが未設定だった。 | `infra/modules/cloudfront/main.tf`、tests | `default_root_object = "index.html"`を追加した。 | `get-distribution-config`が`index.html`を返し、ルートURLが200。commit `4ab096e`。 |
| T-34 | Cognitoログイン後、別ページへ移動すると`unauthorized` | tokenをJavaScriptメモリだけに保持していたため、HTMLページ遷移で消えた。 | `apps/portal-frontend/src/public/js/auth.js`、OAuth tests | access/id tokenと有効期限を`sessionStorage`へ保存し、expiry/logout時に削除するよう変更した。 | ログイン後にstatus/reportsを移動しても認証が維持される。commit `5998de7`。 |
| T-35 | Cognito callbackがテキスト表示のようになり、S3 objectが`binary/octet-stream` | 拡張子なしの`callback`を`s3 sync`するとContent-TypeをHTMLと判定できなかった。config.jsのcacheも残り得た。 | `scripts/deploy-frontend.sh`、tests | callbackを`text/html; charset=utf-8`、config.jsをJavaScriptとして再uploadし、両方`Cache-Control: no-store`にした。 | `s3api head-object`でContentType/CacheControlを確認。commit `5998de7`。 |
| T-36 | ログイン済みでも`/api/status`と`/api/reports`が404 | HTTP APIの`routeKey`が`ANY /api/{proxy+}`のパターンを返す一方、Lambdaが具体pathとして扱った。 | `apps/portal-lambda/app/handler.py`、README、tests、手順書 | proxy routeKeyの場合は`rawPath`とHTTP methodで具体pathを解決するよう変更した。 | Portal/APIのstatus/reportsが200。commit `c77c836`。 |
| T-37 | Portal一覧は出るがstatus、message、S3参照が空 | seed scriptの項目名`status/message/storage_key`とFrontendが期待する`state/overview/s3_key`がずれていた。 | `apps/portal-frontend/src/public/js/pages.js`、tests | 新旧双方の項目名へfallbackして表示するよう変更した。 | 一覧と詳細にstatus/message/report参照が表示される。commit `ae7e9ec`。 |
| T-38 | seed script実行で`ModuleNotFoundError: boto3` | ローカルPythonにAWS SDKが入っていなかった。 | `docs/operation/aws-build-procedure.md` | `.venv`作成、activate、boto3導入、version確認をseed手順へ追加した。 | 3 seed scriptが`failed=0`で完了。 |
| T-39 | seed直後にSQSが`NotVisible`、しばらくするとVisibleへ戻るため成功判断が難しい | SQS件数は概算かつ非同期で、worker処理中や再試行中は値が変動する。過去のDLQ 3/5件も残っていた。 | `docs/operation/aws-build-procedure.md` | 最大3分のpoll、main queue 0/0、DLQは絶対0ではなく投入前後差分なし、という判定へ変更した。 | main queue 0/0かつDLQ before=after。 |

### 3.5 destroy・後片付け

| ID | エラー内容・見え方 | 原因 | 修正ファイル名 | 修正内容 | 確認方法 |
| --- | --- | --- | --- | --- | --- |
| T-40 | `terraform_state_bucket_name` / `terraform_lock_table_name output not found` | 手順のoutput名が実装と違い、DynamoDB lockも既定では未使用だった。 | `docs/operation/aws-build-procedure.md` | 正しい`state_bucket_name`、`artifact_bucket_name`を使用。backendは`use_lockfile=true`としてDynamoDB名へ依存しない手順へ変更した。 | Bootstrap output取得とdev backend init成功。 |
| T-41 | destroy planが必須variableを対話要求し、`yes`入力で型エラー | destroyでもconfiguration評価に必要なvariableは必須。bool/List/ARNに適当な文字は入れられない。 | `docs/operation/aws-build-procedure.md` | SSMとstateから正しい型の`destroy.auto.tfvars.json`を自動生成する手順を追加した。 | `plan -input=false -destroy`が質問なしで完了。 |
| T-42 | `lambda-package-metadata.json: No such file or directory` | このmetadataはPipeline artifactで、ローカルのsource treeに常に存在するファイルではなかった。 | `docs/operation/aws-build-procedure.md` | Lambda functionのTerraform stateからbucket/key/version/hashを抽出するよう変更した。 | destroy用7必須値が非空で生成される。 |
| T-43 | `Saved plan is stale` | plan作成後にPipelineまたは別Terraform操作がstateを変更した。saved planは古いstateへは適用できない。 | `docs/operation/aws-build-procedure.md` | 古いplanを再利用せず、最新stateで再planし、承認直後に他操作を挟まずapplyする停止条件を追加した。 | 新planのapplyが開始できる。 |
| T-44 | ECR `RepositoryNotEmptyException`、S3 `BucketNotEmpty` | ECRには複数tag/untagged image、S3にはobject version/delete markerが残っていた。repository/bucket本体より先に中身を処理する必要があった。 | `docs/operation/aws-build-procedure.md`、devのforce-destroy variables | ECRの全imageをrepository単位で削除し、S3は承認済みdestroy用force flagを使う。Bootstrap versioned bucket用の全version削除関数も追加した。 | ECR image数0、本体Terraform state空、最後にBootstrap state空。 |

### 3.6 追加照合で回収した問い合わせ

| ID | エラー内容・見え方 | 原因 | 修正ファイル名 | 修正内容 | 確認方法 |
| --- | --- | --- | --- | --- | --- |
| T-45 | EKS version確認が`null`になった | Add-on用APIへKubernetes versionを渡しており、cluster versionのSupport状態を確認するAPIではなかった。 | `docs/operation/aws-build-procedure.md` | `aws eks describe-cluster-versions`でversion、Standard Support終了日、Extended Support終了日を確認し、`STANDARD_SUPPORT`以外は停止するよう変更した。 | 手順7で対象versionとSupport期間が表形式で返る。 |
| T-46 | migration成功後の`get-log-events`が`The specified log stream does not exist` | CloudWatch Logsへのstream反映前に取得したか、`--max-items`で期待した最新streamを確定できていなかった。 | `docs/operation/aws-build-procedure.md` | `--limit 1`で最新streamを取得し、存在するまで最大1分再試行してからログを読むよう変更した。 | stream名が`None`でないことを検査し、最大500件のevent messageを取得する。 |
| T-47 | `DescribeSecurityGroupRules`でfilter `referenced-group-info.group-id`がinvalid | この値はCLIのserver-side filter名として使えず、返却JSONの`ReferencedGroupInfo.GroupId`をJMESPathで絞る必要があった。 | `docs/operation/aws-build-procedure.md` | `group-id`だけをAPI filterにし、参照元SG、tcp、5432を`--query`で検査するコマンドへ変更した。 | EKS cluster SGからDB SG:5432の一致ruleが1件以上。 |
| T-48 | `git checkout main`が`.gitignore`のローカル変更を上書きするとして中断 | 未コミット変更がある状態で別branchへ切り替えようとした。Gitは利用者の変更を守るためcheckoutを停止した。 | `docs/operation/aws-build-procedure.md` | 手順1で作業ツリーが空であることをgateにし、空でない場合は自動破棄せず、commitまたはstashの判断を求めるようにした。 | `git status --porcelain`が空、HEADと`origin/main`が一致。 |
| T-49 | GitHub PRが`Checking for the ability to merge automatically...`のままに見えた | CI結果反映やmergeability計算が非同期で、画面表示が追いついていない場合がある。 | `docs/operation/aws-build-procedure.md` | AWS構築前にローカルで`origin/main`を取得し、HEAD一致を機械確認する手順を追加。PR画面だけを構築元の判定に使わない。 | CI成功・merge完了後、`git pull --ff-only`とHEAD一致検査が成功。 |

## 4. 失敗から定着した設計・運用原則

1. **値を写さない**: AWS ID、ARN、URL、resource名はTerraform output、SSM、AWS APIから取得する。
2. **JSONを手で書かない**: URL/CIDR/principal配列は`jq`で生成し、登録後も型と内容を検査する。
3. **PlanとApplyを混ぜない**: Pipeline execution IDを固定し、承認したbinary planだけをApplyする。
4. **最小権限は実APIで完成させる**: サービス名だけで権限を広げず、失敗したAction、resource、conditionを確認してSid単位で追加し、静的テストも同時に更新する。
5. **初回起動にgateを置く**: migration成功前はECS desired countを0にし、image digest/tag/task definitionの一致を確認する。
6. **AWS managed resourceの実挙動を見る**: EKS cluster SG、Service Linked Role、RDS managed secretなど、AWSが裏で作るresourceを設計へ含める。
7. **非同期値を一回の表示で判断しない**: Pipeline、SQS、CloudFront、EKS rolloutは対象IDを固定し、完了条件まで待つ。
8. **削除も構築の一部**: versioned S3、ECR image、final snapshot、required variables、stale planを事前に扱い、Bootstrapは最後に削除する。

## 5. 成果

最初の設計は静的テストを通っていたが、実AWSでは権限評価、managed resource、非同期処理、ブラウザ認証、削除時の保持データという境界面で多くの問題が現れた。各問題について、その場で権限を広げるのではなく、原因を特定し、実装・テスト・手順書を同時に修正した。結果として、次回は利用者固有の初期入力と承認操作を除き、手順書のコマンドを上から実行して同じ環境を再構築・検証・撤去できる状態になった。

関連資料:

- `docs/operation/aws-build-procedure.md`: 改訂済みの唯一の実行順序
- `docs/operation/aws-resource-parameter-sheet.xlsx`: 構築前確認、Category C、destroy判断
- `bootstrap/tests/test_iam_least_privilege.py`: Terraform実行roleの最小権限回帰テスト
- `scripts/tests/test_deploy_scripts.py`: deploy手順の入力・安全性・構文回帰テスト
