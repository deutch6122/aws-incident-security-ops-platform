# 想定 Q&A

面接官から聞かれる可能性がある質問と回答例です。「ポートフォリオ」「自己学習」という前提を忘れず、適切に説明してください。

## Q1: なぜ Product_A / Product_B を分けたのか

**回答例**:

> セキュリティ運用の「内部データ」と「公開データ」では、求められるセキュリティレベルと取り扱いが異なります。社内運用基盤には機微なインシデント情報が含まれますが、公開ポータルは関係者に伝える必要のある最小限の情報だけです。
> 
> 両者を同一个システムに統合すると、公開 API や設定ミスが内部データ泄露のリスクになります。分开することで、一方の脆弱性が他方へ波及するのを防げます。これは AWS の Well-Architected Framework で推奨されている ** separation of concerns** の实践です。
> 
> 実装では、ECS/EKS/Aurora を Product_A、CloudFront/Lambda/DynamoDB を Product_B とし、コード的にも Terraform module 的にも明確に分离しています。

## Q2: なぜ A→B 一方向なのか

**回答例**:

> Product_B から Product_A への書き込み経路を设计上没有めた理由は、分离原则を彻底するためです。双向連携にすると、Product_B の障害や設定ミスが Product_A に影响を与える可能性があります。
> 
> もう一つの理由は、データの性质です。Product_B に渡すデータは月次レポート那样的汇总信息で、リアルタイム性が必要ありません。EKS の CronJob で月次汇总を生成し、非同期・幂等的に Product_B へ反映する设计にしています。
> 
> これにより、Product_A は稳定供应し、Product_B は公开供应を安全に 行えます。

## Q3: なぜ Terraform と App Deploy を分けたのか

**回答例**:

> インフラ（VPC、ECS クラスタ、Aurora）とアプリケーション（コンテナ、静的ファイル）では、変更频度と影响范围が违います。インフラは週〜月単位の変更で影响范围が大きい、アプリケーションは日〜週単位の変更で影响范围が局所的です。
> 
> 分离することで、インフラ变更は Infra_Pipeline で計画的・承認制で适用し、アプリケーション変更は App_Deploy で快速にデプロイできます。App_Deploy から terraform を呼ばない 设计也因此です。
> 
> もう一つの理由はコストです。インフラ変更はリソース作成/削除が発生するためコスト影响が大きいが、アプリケーション更新はコンテナ更新だけで済みます。

## Q4: なぜ ECS と EKS の両方を使ったのか

**回答例**:

> ECS Fargate は同期 API（リクエスト/レスポンス型）に适しています。ALB 配下で简单的にコンテナを実行でき、运用负荷が低いです。
> 
> EKS は非同期处理・CronJob に适しています。SQS 驱动的イベント処理、複数の Worker 种别（alarm-event-processor、security-finding-worker、monthly-summary-cronjob）のオーケストレーションが必要です。Kubernetes の Job/CronJob 机能を使って実装しました。
> 
> 「同期 API」「非同期処理基盤」という异なる责務を、それぞれた适合한サービスに割り当てた设计です。

## Q5: なぜ Aurora と DynamoDB を使い分けたのか

**回答例**:

> Aurora は关系数据库で、复杂なクエリ・トランザクション・JOIN が必要です。インシデントと Finding の关联検索、audit_logs の时系列查询など、リレーショナルな处理が必要です。
> 
> DynamoDB は键值存储で、スケーラビリティと低コストが魅力です。Product_B の public_status_items は单纯な key-value 读取居多で、DynamoDB の GSÍ 设计で効率的な检索が可能です。
> 
> つまり、事务处理・复杂查询が必要なデータは Aurora、スケーラビリティ・轻量化が必要なデータは DynamoDB という选択肢です。

## Q6: なぜ CloudFront / S3 / OAC / WAF 構成にしたのか

**回答例**:

> CloudFront + S3 は、静的コンテンツの高效なエッジ配信ためです。S3 单一で公开すると世界で延迟が発生するし、费用もかかります。
> 
> OAC（Origin Access Control）は、S3 へのアクセスを CloudFront 経由に限定する机能です。S3 を public にする必要がなくなり、セキュリティ强化になります。
> 
> WAF はエッジ保护ためです。Rate Limit（1分钟あたり1000リクエスト超过でブロック）、IP reputation、SQL injection 対策などを.edgeで适用できます。防护可以在恶意请求到达源站之前拦截。

## Q7: なぜ Cognito / API Gateway / Lambda 構成にしたのか

**回答例**:

> Cognito は、JWT ベースの认证机能を提供します。Users ごとに ID/密码を管理せずとも、安全に用户认证を行えます。
> 
> API Gateway は、CloudFront と Lambda の间的桥梁です。Cognito Authorizer で JWT を验证し、有効なトークンを持つ用户のみ Lambda を呼び出せます。
> 
> Lambda は、サーバーレスでコードを実行できます。トラフィックに 따라自动スケーリングされ、アイドル时间のコストが零です。Product_B の API 処理に最适合しました。

## Q8: 监视设计で何を的意识したか

**回答例**:

> 3つの视点を入れました。
> 
> **1. 资源单位的监视**: SQS DLQ、ECS CPU/メモリ/タスク数、ALB 5xx/レイテンシ、Lambda Errors/Throttles/Duration、Aurora ACU/接続数。
> 
> **2. 分离的 Dashboard**: Product_A と Product_B を分けたダッシュボードを作成し、一方の负载が他方の监视を隠すことを防ぎました。
> 
> **3. 通知的体制**: CloudWatch Alarm → SNS → 通知の流れで、障害发生時にすばやく気付ける设计です。

## Q9: Secret をどう扱っているか

**回答例**:

> DB パスワードなどの secret は、Secrets Manager で管理し、代码・Terraform に平文で埋め込んでいません。ECS/EKS のタスクロールが Secrets Manager から情報を取得する设计です。
> 
> `.gitignore` で `.env`、`*.pem`、`credentials` などの机微ファイルを排除しており、git 管理对象に含めていません。
> 
> CI/CD（GitHub Actions）では、AWS 認証情报を GitHub Secrets 経由で环境变量として渡しており、代码内に credential を埋め込んでいません。

## Q10: CI で何を確認しているか

**回答例**:

> GitHub Actions で以下のことを確認しています。
> 
> - **infra module tests**: Terraform 资源のスナップショットテスト（コード改变検出）
> - **application tests**: FastAPI / Worker / Lambda の单元・Property Based Test
> - **deploy script syntax**: `bash -n` で構文错误检测
> - **static safety scan**: 机微ファイル（`.venv`、`.env`、`*.pem` 等）が git 管理对象に含まれていないこと、实 Secret/ARN/账号 ID が代码に混入していないことを確認
> 
> 重要な点是、CI は実 AWS 操作・デプロイを一回も行いません。すべて静的なテストとスキャンです。

## Q11: 実 AWS にデプロイしていない場合、どう説明するか

**回答例**:

> これは自己学習目的のポートフォリオで、dev 環境の MVP を構築途中です。AWS 资源を作成・管理する费用面と inúmer的情报（实アカウント、实ドメイン）の保护面から、現在は代码・テストの验证のみで实环境へのデプロイは行していません。
> 
> しかし、Terraform で infrastructure as code を实现しており、`terraform plan` で作成予定リソースを確認できます。GitHub Actions の CI も设定済みで、push/PR 時に自动テストが动作します。
> 
> 次の段階として、AWS 沙箱环境でのデプロイ・动作确认を予定しています。

## Q12: コスト面で何を注意したか

**回答例**:

> MVP なので、以下の点でコスト最优化的设计しました。
> 
> - **Aurora Serverless v2**: 最小キャパシティーで必要に応じて自动スケーリング
> - **CloudFront PriceClass 100**: 日本东京のみ配信范围限定
> - **CloudWatch Logs 保持期间**: 14〜30 日に设定
> - **コスト影响大リソースの可視化**: `terraform plan` で Aurora/NAT/EKS/CloudFront のようなコスト影响大リソースを明示し、不要時は削除步骤を准备
> 
> 本番环境では、监视・アラート设计に加え、预算アラート设定なども Recommend します。

## Q13: 改善余地は何か

**回答例**:

> 现在の构成でいくつか改善余地があります。
> 
> - **EKS の完全构筑**: 現時点では EKS cluster 自体は module にあるが、完全な pod 配置には至っていない（k8s manifest 作成済み）
> - **prod 构成への展开**: dev/MVP から prod への展开手续・Blue-Green Deploy などは未実装
> - **灾害復旧**: backup/restore 戦略、Multi-AZ 配置の强化
> - **详细监视**: X-Ray、Container Insights、Aurora Performance Insights などは設計に含めるがMVPでは無効
> 
> これらは后続の学习课题として认识しています。

## Q14: 実務でどう活かせるか

**回答例**:

> 以下のような実務スキルに活かせると考えています。
> 
> - **AWS アーキテクチャ设计**: ECS/EKS/DynamoDB/Aurora/CloudFront などのサービスを选定し、分离原则を一贯して适用した经验
> - **Terraform を用いた IaC**: module 分割、再利用性、可読性を意識した构成
> - **Property Based Testing**: Hypothesis を使ったテスト设计经验（バグの早期発見）
> - **CI/CD 整備**: GitHub Actions での自动テスト、safety scan などのPipeline構築经验
> - **セキュリティ考慮**: Secrets Manager、Cognito、WAF、OAC などの実装经验
> 
> これらの経験を基に、実際の案件でも安全で维护性が高いシステム构筑に貢献できます。

---

## 回答作成のヒント

1. **「なぜ」を2段階**: 什么（What）と 为什么（Why）を分开回答できる用意をしておく
2. **具体例を混ぜる**: 「Aurora を使っている」ではなく「インシデントと Finding の关联检索に JOIN が一张必要 поэтому Aurora 选择了 PostgreSQL」のように具体性を出す
3. **ポートフォリオであることを伝える**: 「実案件ではなく自己学習プロジェクトですが」「MVP ですが」と前置きすると、面试官も期待値を调整してくれる
4. **改善余地，主动語る**: 「まだ完成形ではなく、この点は改善したいと考えています」と伝えると学习姿勢をアピールできる
