# apps/portal-frontend

Product_B の Status Portal 静的フロントエンド。CloudFront + S3(OAC) 経由で配信する。

## 構成（予定）

- `src/` … 画面ソース（ログイン(Cognito)、ステータス一覧、障害詳細、レポート一覧、レポート詳細）と `/api/*` 呼び出し
- `public/` … 静的アセット

> 実装は Task 16.1 で追加する（プレースホルダ）。build → S3 sync → CloudFront invalidation でデプロイ（Req 22.4）。
