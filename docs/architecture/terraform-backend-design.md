# Terraform backend / state lock 設計

design.md の「Bootstrap / state lock 方式」を要約する（Req 20.3, 20.4, 21.1, 26.2）。

## remote backend

- Terraform state は remote backend（S3）で管理する（Req 20.3）。
- state 用 S3 バケットはバージョニング / 暗号化 / public access block を有効化する（Req 20.4）。

## state lock 方式

- **Terraform v1.10 以降を前提**とし、S3 backend の **`use_lockfile=true`（S3 ネイティブロック）を第一候補**とする。
- 従来方式の **DynamoDB lock table は旧方式互換 / 代替案**として扱い、Bootstrap で作成する DynamoDB lock table は**任意（変数フラグ / コメント）扱い**とする。

> 注記: Req 20.3 / 21.1 は「S3 + DynamoDB lock」と記載しているが、本設計では `use_lockfile=true` を第一候補・DynamoDB を代替とし、その旨を明記する。

## Bootstrap の位置づけ

パイプライン自身を作るための state / 権限をパイプラインで作れない鶏卵問題を回避するため、remote state / state lock / CI/CD 土台 / terraform-exec-role は初回のみローカルから作成する（[../operation/deployment-design.md](../operation/deployment-design.md) 参照）。
