# apps/portal-frontend

Product_B の Status Portal 静的フロントエンド。CloudFront + S3(OAC) 経由で配信する
バニラ JS の MVP（ビルドツール・npm 依存なし）。

## 構成

- `src/public/` … 配信対象の静的アセット
  - `index.html` … ログイン（Cognito Hosted UI へリダイレクト）
  - `status.html` … ステータス一覧（`GET /api/status`）
  - `status-detail.html` … 障害詳細（`GET /api/status/{id}`）
  - `reports.html` … レポート一覧（`GET /api/reports`）
  - `report-detail.html` … レポート詳細（`GET /api/reports/{id}`）
  - `config.js` … 設定 **プレースホルダのみ**（後述）
  - `js/api.js` … 4 エンドポイントを呼ぶ共通 API クライアント
  - `js/auth.js` … Cognito Hosted UI ログイン URL 生成・トークン読取（プレースホルダ）
  - `js/pages.js` … 各画面のコントローラ
  - `css/styles.css` … 最小スタイル
- `tests/` … Python(pytest) による静的テスト（Node 不要）

## /api/* 呼び出し

`js/api.js` が以下を `fetch` で呼ぶ。`Authorization: Bearer <token>` を付与する構造
（トークン値は埋め込まず、Cognito Hosted UI/SDK が実行時に session storage へ格納した
id/access token を読む）。

| 画面 | 呼び出し |
| --- | --- |
| ステータス一覧 | `GET /api/status` |
| 障害詳細 | `GET /api/status/{id}` |
| レポート一覧 | `GET /api/reports` |
| レポート詳細 | `GET /api/reports/{id}` |

`API_BASE` は既定で同一オリジンの `/api`（CloudFront の API Gateway オリジン想定）。
実 API ドメインはハードコードしない。

### status_id の安全性

`status_id` は「/」を含まない ID（例 `status-202406`）である前提。`buildStatusDetailPath`
は「/」を含む ID を拒否し、それ以外の予約文字は `encodeURIComponent` でエンコードする。
これにより `/api/status/{id}` の path param として安全に扱える。

## Cognito 連携（MVP プレースホルダ）

`config.js` は **プレースホルダ定数のみ**を持つ。実値・実ドメイン・実トークンは含めない。

- `USER_POOL_ID` / `APP_CLIENT_ID` / `REGION` / `COGNITO_DOMAIN` / `REDIRECT_URI`
  … `REPLACE_WITH_*` プレースホルダ。デプロイ時（`deploy-frontend.sh` 等）に実値へ置換する。
- `API_BASE` … 既定 `/api`（同一オリジン）。

ログインは Cognito Hosted UI へリダイレクトし、コールバックが id/access token を
session storage（`portal_id_token` / `portal_access_token`）へ格納する想定。本 MVP では
実 Cognito/API Gateway/CloudFront へ接続しない。

## テスト

```
python3 -m pytest tests -q
```

HTML/CSS/JS の内容を静的に解析し、画面要素の存在・4 エンドポイント参照・config が
プレースホルダのみ・status_id の「/」非許容を検証する（既存 IaC スナップショットテストと
同方式、Node 不要）。

## デプロイ（予定）

build 不要。`src/public/` を S3 へ sync → CloudFront invalidation（Req 22.4）。
`config.js` のプレースホルダはデプロイ時に実値へ差し替える。
