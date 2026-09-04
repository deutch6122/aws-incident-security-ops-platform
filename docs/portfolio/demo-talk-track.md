# デモ用トークトラック

GitHub 画面を見せながら話す台本集。限られた時間で効果的に伝えるためのガイドです。

## 30秒バージョン

> 「これはセキュリティインシデント管理基盤のポートフォリオです。AWS 上に ECS と EKS で構成され、Aurora と DynamoDB でデータを持ちます。社内運用者と公開ポータルを明確に分離し、月次レポートを一方向で連携するアーキテクチャになっています。」

話し方のポイント:
- 30秒なので **3〜4 文** に絞る
- 「ECS/EKS」「Aurora/DynamoDB」「分離」「一方向連携」のキーワードを入れる
- 技術的な細部は省略する

## 1分バージョン

> 「セキュリティインシデント管理基盤を作りました。AWS 上で、ECS Fargate で同期 API、EKS で非同期ワーカーを動かし、Aurora PostgreSQL にデータをためます。もう一方に公開ポータルもあって、CloudFront と Lambda と DynamoDB で構成しています。
> 
> 特徴は Product_A と Product_B を明確に分離したことです。社内運用と一般公開を同一のシステムに混ぜず、月次レポートを作るときにだけ A→B へデータを渡す設計にしてあります。
> 
> Terraform でインフラをコード化し、GitHub Actions で自動テストを回しています。」

話し方のポイント:
- 30秒版より **構成と設計意図** を追加する
- ECS/EKS/Aurora/DynamoDB/CloudFront/Lambda を具体的に言う
- Product_A / Product_B 分離と A→B 一方向連携を強調する

## 3分バージョン

1. **導入**（30秒）
   - 「セキュリティインシデント管理基盤のポートフォリオです」
   - 担当工程（設計/実装/テスト）を簡単に触れる

2. **システム構成**（1分）
   - Product_A: ECS + EKS + Aurora
   - Product_B: CloudFront + Lambda + DynamoDB
   - A→B 一方向連携（月次レポート）
   - 画面: README.md のアーキテクチャ図を指す

3. **設計判断**（1分）
   - なぜ ECS と EKS を分けたか（同期 vs 非同期）
   - なぜ Aurora と DynamoDB を分けたか（リレーショナル vs キーバリュー）
   - なぜ一方向にしたか（分離原則）
   - 画面: docs/architecture/architecture-overview.md

4. **実装・テスト**（30秒）
   - Terraform module 分割
   - Property Based Testing（Hypothesis）
   - CI/CD（GitHub Actions）
   - 画面: 各 tests ディレクトリ

## GitHub で見る順番

面接官に画面共有するときは、以下の順番で案内するとスムーズです。

| 順番 | 表示する内容 | 強調ポイント |
| --- | --- | --- |
| 1 | README.md | プロジェクト概要、アーキテクチャ図 |
| 2 | docs/architecture/ | アーキテクチャ詳細、設計判断 |
| 3 | infra/modules/ | Terraform module 分割、各 module の責務 |
| 4 | apps/backend-api/ | FastAPI、SQLAlchemy、Backend API 構成 |
| 5 | apps/eks-workers/ | Worker 3種（alarm/finding/summary） |
| 6 | apps/portal-lambda/ | Lambda、Property Based Testing |
| 7 | apps/portal-frontend/ | 静的コンテンツ、Frontend 構成 |
| 8 | scripts/ | deploy/seed スクリプト、dry-run 設計 |
| 9 | .github/workflows/ci.yml | CI/CD、自動テスト構成 |

## デモで強調するポイント

1. **分離原則の実践**
   - Product_A / Product_B がコードレベルでも分離されていること
   - Terraform module が明確に分かれていること

2. **A→B 一方向設計**
   - なぜ B→A を排除したか
   - 実行主体が CronJob に限定されていること

3. **セキュリティ考慮**
   - Secrets Manager 使用
   - Cognito JWT 認証
   - WAF エッジ保護
   - OAC で S3 アクセス制御

4. **テストアプローチ**
   - Property Based Testing（Hypothesis）
   - suite 別実行（conftest.py 衝突回避）
   - static safety scan

5. **CI/CD 設計**
   - Infrastructure と App Deploy の分離
   - dry-run 既定（安全設計）

## 話しすぎないためのポイント

- **時間管理**: 30秒/1分/3分の各バージョンを事前に練習する
- **相手優先**: 面接官が質問したら一旦止めて質問に答える
- **深掘り準備**: 「なぜ」を2段階で答えられるように用意する（what と why）
- **要点を絞る**: 重要なポイントを3つに絞る
- **相談**: 「もう少し詳しく話しますか？」と確認する

---

このトークトラックは自分の状況に合わせて修正して使ってください。最も重要なのは **簡潔に** と **自信を持って** 説明することです。
