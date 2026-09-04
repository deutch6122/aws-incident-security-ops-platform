# アプリデプロイ設計（App_Deploy）

design.md の「App_Deploy（インフラ apply と分離）」を要約する（Req 22, 26.2）。

App_Deploy はインフラの `terraform apply` 工程と分離する（Req 22.1）。`scripts/*` として実装する（Task 19.1）。

| 対象 | 手順 | 対応要件 |
| --- | --- | --- |
| ECS（Backend_API） | Docker build → ECR push → ECS service update | Req 22.2 |
| EKS（ワーカー群） | Docker build → ECR push → `kubectl apply`（MVP、素の manifest）または Helm upgrade（拡張時） | Req 22.3 |
| CloudFront（Product_B） | frontend build → S3 sync → CloudFront invalidation | Req 22.4 |

## EKS manifest 管理方式

MVP は**素の Kubernetes manifest（`kubectl apply`）**を推奨する。ワーカーが少数（3 種）かつ dev 単一環境であり、manifest の透明性・学習容易性・デバッグ容易性が Helm の抽象化より勝るため。環境が増加（staging/prod 追加）した時点で Helm chart 化へ移行する。
