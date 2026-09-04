# デモ用トークトラック

GitHub 画面を見せながら話す台本集。限られた時間で効果的に伝えるためのガイドです。

## 30秒バージョン

> 「これはセキュリティインシデント管理基盤のポートフォリオです。AWS 上に ECS と EKS で構成され、Aurora と DynamoDB でデータを持ちます。社内運用者と公開ポータルを明確に分離し、月次レポート собой 一方向連携するアーキテクチャになっています。」

** говоря point:
- 30秒なので **3〜4 文** に絞る
- 「ECS/EKS」「Aurora/DynamoDB」「分離」「一方向連携」のキーワードを入れる
- 技術细节は省略

## 1分バージョン

> 「セキュリティインシデント管理基盤を作りました。AWS で、ECS Fargate で同期 API、EKS で非同期ワーカーを動かし、Aurora PostgreSQL にデータをためます。另一个 側に公開ポータルもあって、CloudFront と Lambda と DynamoDB で構成しています。
> 
> 特徴は Product_A と Product_B を明確に 分離したことです。社内運用と一般公開を同一个 システムに混ぜず、月次レポート作る时机にだけ A→B へデータを渡す 设计にしてあります。
> 
> Terraform でインフラを代码化し、GitHub Actions で 自动テストを 回しています。」

** говоря point:
- 30秒版より **構成と设计意図** を追加
- ECS/EKS/Aurora/DynamoDB/CloudFront/Lambda を具体的に言う
- Product_A / Product_B 分離と A→B 一方向連携を强调

## 3分バージョン

1. **开场**（30秒）
   - 「セキュリティインシデント管理基盤のポートフォリオ입니다」
   - 担当 工程（設計/実装/テスト）を簡単に提及

2. **システム構成**（1分）
   - Product_A: ECS + EKS + Aurora
   - Product_B: CloudFront + Lambda + DynamoDB
   - A→B 一方向連携（月次レポート）
   - 画面: README.md のアーキテクチャ図を指す

3. **设计判断**（1分）
   - なぜ ECS と EKS を 分けたか（同期 vs 非同期）
   - なぜ Aurora と DynamoDB を 分けたか（関係quer vs 键值）
   - なぜ 一方向にしたか（分离原则）
   - 画面: docs/architecture/architecture-overview.md

4. **実装・テスト**（30秒）
   - Terraform module 分割
   - Property Based Testing（ Hypothesis）
   - CI/CD（GitHub Actions）
   - 画面: 各 tests 目录

## GitHub で見る顺番

面试官に屏幕共享 时、以下の顺番で案内するとスムーズです：

| 顺番 | 表示する内容 | 强调 point |
| --- | --- | --- |
| 1 | README.md | プロジェクト概要、アーキテクチャ図 |
| 2 | docs/architecture/ | アーキテクチャ详细、设计判断 |
| 3 | infra/modules/ | Terraform module 分割、各 module の責務 |
| 4 | apps/backend-api/ | FastAPI、SQLAlchemy、Backend API 構成 |
| 5 | apps/eks-workers/ | Worker 3種（alarm/finding/summary） |
| 6 | apps/portal-lambda/ | Lambda、Property Based Testing |
| 7 | apps/portal-frontend/ | 静的コンテンツ、Frontend 構成 |
| 8 | scripts/ | deploy/seed 스크립트、dry-run 設計 |
| 9 | .github/workflows/ci.yml | CI/CD、自动テスト構成 |

## デモで强调する point

1. **分离原则の実践**
   - Product_A / Product_B が 代码レベルでも 分离されていること
   - Terraform module が明確に 分かれていること

2. **A→B 一方向设计**
   - なぜ B→A を排除したか
   - 実行主体が CronJob に限定されていること

3. **セキュリティ考虑**
   - Secrets Manager 使用
   - Cognito JWT 认证
   - WAF エッジ保護
   - OAC で S3 アクセス制御

4. **测试 Approach**
   - Property Based Testing（Hypothesis）
   -  suite 别执行（conftest.py 冲突回避）
   -  static safety scan

5. **CI/CD 设计**
   -  Infrastructure と App Deploy の分離
   -  dry-run 既定（安全设计）

## 話しすぎないための point

- **时间管理**: 30秒/1分/3分の版本を事前に练习
- **对话を者优先**: 面试官が質問したら一旦止めて質問に答える
- **深掘り準備**: 「为什么」を2段階答えられる用意（what と why）
- **简历**: 重要な point 3つに绞る
- **相谈**: 「もう少し詳しく话しますか？」と确认する

---

このトークトラック是根据自己的情况 修改して使ってください。最も重要なのは **简潔に** と **自信を持って** 説明することです。
