# 想定 Q&A

面接官から聞かれる可能性がある質問と回答例です。「ポートフォリオ」「自己学習」という前提を忘れず、適切に説明してください。

## Q1: なぜ Product_A / Product_B を分けたのか

**回答例**:

> セキュリティ運用の「内部データ」と「公開データ」では、求められるセキュリティレベルと取り扱いが異なります。社内運用基盤には機微なインシデント情報が含まれますが、公開ポータルは関係者に伝える必要のある最小限の情報だけです。
> 
> 両者を同一のシステムに統合すると、公開 API や設定ミスが内部データ漏洩のリスクになります。分けることで、一方の脆弱性が他方へ波及するのを防げます。これは AWS の Well-Architected Framework で推奨されている **separation of concerns（関心の分離）** の実践です。
> 
> 実装では、ECS/EKS/Aurora を Product_A、CloudFront/Lambda/DynamoDB を Product_B とし、コード的にも Terraform module 的にも明確に分離しています。

## Q2: なぜ A→B 一方向なのか

**回答例**:

> Product_B から Product_A への書き込み経路を設計上排除した理由は、分離原則を徹底するためです。双方向連携にすると、Product_B の障害や設定ミスが Product_A に影響を与える可能性があります。
> 
> もう一つの理由は、データの性質です。Product_B に渡すデータは月次レポートのような集計情報で、リアルタイム性が必要ありません。EKS の CronJob で月次集計を生成し、非同期・冪等的に Product_B へ反映する設計にしています。
> 
> これにより、Product_A は安定して稼働し、Product_B は公開配信を安全に行えます。

## Q3: なぜ Terraform と App Deploy を分けたのか

**回答例**:

> インフラ（VPC、ECS クラスタ、Aurora）とアプリケーション（コンテナ、静的ファイル）では、変更頻度と影響範囲が違います。インフラは週〜月単位の変更で影響範囲が大きく、アプリケーションは日〜週単位の変更で影響範囲が局所的です。
> 
> 分離することで、インフラ変更は Infra_Pipeline で計画的・承認制で適用し、アプリケーション変更は App_Deploy で迅速にデプロイできます。App_Deploy から terraform を呼ばない設計にしているのもそのためです。
> 
> もう一つの理由はコストです。インフラ変更はリソース作成/削除が発生するためコスト影響が大きいですが、アプリケーション更新はコンテナ更新だけで済みます。

## Q4: なぜ ECS と EKS の両方を使ったのか

**回答例**:

> ECS Fargate は同期 API（リクエスト/レスポンス型）に適しています。ALB 配下でシンプルにコンテナを実行でき、運用負荷が低いです。
> 
> EKS は非同期処理・CronJob に適しています。SQS 駆動のイベント処理、複数の Worker 種別（alarm-event-processor、security-finding-worker、monthly-summary-cronjob）のオーケストレーションが必要です。Kubernetes の Job/CronJob 機能を使って実装しました。
> 
> 「同期 API」「非同期処理基盤」という異なる責務を、それぞれに適したサービスに割り当てた設計です。

## Q5: なぜ Aurora と DynamoDB を使い分けたのか

**回答例**:

> Aurora はリレーショナルデータベースで、複雑なクエリ・トランザクション・JOIN に対応できます。インシデントと Finding の関連検索、audit_logs の時系列クエリなど、リレーショナルな処理が必要です。
> 
> DynamoDB はキーバリューストアで、スケーラビリティと低コストが魅力です。Product_B の public_status_items は単純な key-value の読み取りが中心で、DynamoDB の GSI 設計で効率的な検索が可能です。
> 
> つまり、トランザクション処理・複雑なクエリが必要なデータは Aurora、スケーラビリティ・軽量化が必要なデータは DynamoDB という選択です。

## Q6: なぜ CloudFront / S3 / OAC / WAF 構成にしたのか

**回答例**:

> CloudFront + S3 は、静的コンテンツの効率的なエッジ配信のためです。S3 単独で公開すると各地域で遅延が発生し、費用もかかります。
> 
> OAC（Origin Access Control）は、S3 へのアクセスを CloudFront 経由に限定する機能です。S3 を public にする必要がなくなり、セキュリティ強化になります。
> 
> WAF はエッジ保護のためです。Rate Limit（1分あたり1000リクエスト超過でブロック）、IP reputation、SQL injection 対策などをエッジで適用できます。悪意あるリクエストがオリジンに到達する前に防御できます。

## Q7: なぜ Cognito / API Gateway / Lambda 構成にしたのか

**回答例**:

> Cognito は、JWT ベースの認証機能を提供します。ユーザーごとに ID/パスワードを管理せずとも、安全にユーザー認証を行えます。
> 
> API Gateway は、CloudFront と Lambda の間の橋渡しです。Cognito Authorizer で JWT を検証し、有効なトークンを持つユーザーのみ Lambda を呼び出せます。
> 
> Lambda は、サーバーレスでコードを実行できます。トラフィックに応じて自動スケーリングされ、アイドル時間のコストがゼロです。Product_B の API 処理に最も適していました。

## Q8: 監視設計で何を意識したか

**回答例**:

> 3つの視点を入れました。
> 
> **1. リソース単位の監視**: SQS DLQ、ECS CPU/メモリ/タスク数、ALB 5xx/レイテンシ、Lambda Errors/Throttles/Duration、Aurora ACU/接続数。
> 
> **2. 分離したダッシュボード**: Product_A と Product_B を分けたダッシュボードを作成し、一方の負荷が他方の監視を覆い隠すことを防ぎました。
> 
> **3. 通知の体制**: CloudWatch Alarm → SNS → 通知の流れで、障害発生時にすばやく気付ける設計です。

## Q9: Secret をどう扱っているか

**回答例**:

> DB パスワードなどの secret は、Secrets Manager で管理し、コード・Terraform に平文で埋め込んでいません。ECS/EKS のタスクロールが Secrets Manager から情報を取得する設計です。
> 
> `.gitignore` で `.env`、`*.pem`、`credentials` などの機微ファイルを除外しており、git 管理対象に含めていません。
> 
> CI/CD（GitHub Actions）では、AWS 認証情報を GitHub Secrets 経由で環境変数として渡しており、コード内に credential を埋め込んでいません。

## Q10: CI で何を確認しているか

**回答例**:

> GitHub Actions で以下のことを確認しています。
> 
> - **infra module tests**: Terraform リソースのスナップショットテスト（コード変更検出）
> - **application tests**: FastAPI / Worker / Lambda の単体・Property Based Test
> - **deploy script syntax**: `bash -n` で構文エラー検出
> - **static safety scan**: 機微ファイル（`.venv`、`.env`、`*.pem` 等）が git 管理対象に含まれていないこと、実 Secret/ARN/アカウント ID がコードに混入していないことを確認
> 
> 重要な点は、CI は実 AWS 操作・デプロイを一切行わないことです。すべて静的なテストとスキャンです。

## Q11: 実 AWS にデプロイしていない場合、どう説明するか

**回答例**:

> これは自己学習目的のポートフォリオで、dev 環境の MVP を構築している途中です。AWS リソースを作成・管理する費用面と、機微な情報（実アカウント、実ドメイン）の保護面から、現在はコード・テストの検証のみで実環境へのデプロイは行っていません。
> 
> しかし、Terraform で infrastructure as code を実現しており、`terraform plan` で作成予定リソースを確認できます。GitHub Actions の CI も設定済みで、push/PR 時に自動テストが動作します。
> 
> 次の段階として、AWS のサンドボックス環境でのデプロイ・動作確認を予定しています。

## Q12: コスト面で何を注意したか

**回答例**:

> MVP なので、以下の点でコスト最適化を設計しました。
> 
> - **Aurora Serverless v2**: 最小キャパシティで必要に応じて自動スケーリング
> - **CloudFront PriceClass 100**: 日本・東京のみ配信範囲を限定
> - **CloudWatch Logs 保持期間**: 14〜30 日に設定
> - **コスト影響が大きいリソースの可視化**: `terraform plan` で Aurora/NAT/EKS/CloudFront のようなコスト影響が大きいリソースを明示し、不要時は削除手順を準備
> 
> 本番環境では、監視・アラート設計に加え、予算アラート設定なども推奨します。

## Q13: 改善余地は何か

**回答例**:

> 現在の構成でいくつか改善余地があります。
> 
> - **EKS の完全構築**: 現時点では EKS cluster 自体は module にありますが、完全な pod 配置には至っていません（k8s manifest は作成済み）
> - **prod 構成への展開**: dev/MVP から prod への展開手順・Blue-Green Deploy などは未実装
> - **災害復旧**: backup/restore 戦略、Multi-AZ 配置の強化
> - **詳細監視**: X-Ray、Container Insights、Aurora Performance Insights などは設計に含めるが MVP では無効
> 
> これらは今後の学習課題として認識しています。

## Q14: 実務でどう活かせるか

**回答例**:

> 以下のような実務スキルに活かせると考えています。
> 
> - **AWS アーキテクチャ設計**: ECS/EKS/DynamoDB/Aurora/CloudFront などのサービスを選定し、分離原則を一貫して適用した経験
> - **Terraform を用いた IaC**: module 分割、再利用性、可読性を意識した構成
> - **Property Based Testing**: Hypothesis を使ったテスト設計の経験（バグの早期発見）
> - **CI/CD 整備**: GitHub Actions での自動テスト、safety scan などのパイプライン構築経験
> - **セキュリティ考慮**: Secrets Manager、Cognito、WAF、OAC などの実装経験
> 
> これらの経験を基に、実際の案件でも安全で保守性が高いシステム構築に貢献できます。

---

## 回答作成のヒント

1. **「なぜ」を2段階で**: 何を（What）と なぜ（Why）を分けて回答できる用意をしておく
2. **具体例を混ぜる**: 「Aurora を使っている」ではなく「インシデントと Finding の関連検索に JOIN が必要なので Aurora（PostgreSQL）を選んだ」のように具体性を出す
3. **ポートフォリオであることを伝える**: 「実案件ではなく自己学習プロジェクトですが」「MVP ですが」と前置きすると、面接官も期待値を調整してくれる
4. **改善余地を自ら語る**: 「まだ完成形ではなく、この点は改善したいと考えています」と伝えると学習姿勢をアピールできる
