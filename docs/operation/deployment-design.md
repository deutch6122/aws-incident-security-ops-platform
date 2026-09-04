# デプロイ設計（3 層分離）

design.md の「デプロイ設計」を要約する（Req 20〜23, 26.2）。

```mermaid
flowchart LR
    subgraph L1["Bootstrap（ローカル初回のみ）"]
        B[remote state S3 / state lock（use_lockfile=true）<br/>CodePipeline/CodeBuild / artifact S3 / terraform-exec-role]
    end
    subgraph L2["Infra_Pipeline（CodePipeline+CodeBuild）"]
        P[fmt → validate → plan → 手動承認 → apply]
    end
    subgraph L3["App_Deploy（インフラ apply と分離）"]
        D1[ECS: build→ECR push→service update]
        D2[EKS: build→ECR push→kubectl apply]
        D3[CloudFront: build→S3 sync→invalidation]
    end
    B --> P --> L3
```

## 分離理由

- **Bootstrap 分離**: パイプラインを作るための state / 権限をパイプライン自身で作れない鶏卵問題を回避するため、初回のみローカルで土台を作る。
- **アプリ / インフラ apply 分離**: インフラは変更頻度が低く影響が大きい、アプリは変更頻度が高く影響が局所的、という性質差に合わせ、独立して安全にリリースするため分離する（Req 22.1）。

詳細: [cicd-design.md](cicd-design.md)（Infra_Pipeline）、[app-deployment-design.md](app-deployment-design.md)（App_Deploy）、backend/state は [../architecture/terraform-backend-design.md](../architecture/terraform-backend-design.md)。
