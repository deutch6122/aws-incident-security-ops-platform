# CI/CD 設計（Infra_Pipeline）

design.md の「Infra_Pipeline」を要約する（Req 21, 23, 26.2）。

## パイプライン

- main への merge/push で起動する（Req 21.2）。
- 順序: `terraform fmt` → `terraform validate` → `terraform plan` → **手動承認** → `terraform apply`（Req 21.3）。
- `terraform plan` で作成/変更/削除予定リソース一覧と、**コスト影響が大きいリソース（Aurora / NAT / EKS / CloudFront）** を明示する（Req 23.1, 23.2）。
- **承認なしでは apply しない**（Req 21.4, 23.3）。ローカル端末からの継続 apply は行わない（Req 21.5）。
- state は remote backend（S3、`use_lockfile=true`）で管理する（Req 20.3）。

## 構成要素（Bootstrap で作成）

- CodePipeline（ステージ: Source → fmt/validate → plan → Approval → apply）。
- CodeBuild（buildspec で Terraform コマンドを実行）。
- artifact 用 S3、terraform-exec IAM Role（最小権限、Req 17.2）。

> CodeDeploy は ECS Blue/Green 候補に限定し、Terraform リソース作成用途では使わない。
