# apps/portal-lambda

Product_B の Portal_API（Python Lambda）。API Gateway + Cognito JWT Authorizer 配下で稼働。

## 構成（予定）

- ハンドラ、DynamoDB アクセス層、JWT 検証（欠落/無効時 401）
- `GET /api/status` / `GET /api/status/{id}`（閲覧時に page_view_logs へ1件記録、public_status_items 本体は不変）
- `GET /api/reports` / `GET /api/reports/{id}`（未登録は 404）

IAM: DynamoDB 読取＋page_view_logs 書込のみ。**Product_A への書き込み権限なし**（Req 14.3）。

> 実装は Task 15 以降で追加する（プレースホルダ）。
