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
  - `config.js` … リポジトリ上はプレースホルダのみ。デプロイ時に一時生成して差し替え
  - `js/api.js` … 4 エンドポイントを呼ぶ共通 API クライアント
  - `js/auth.js` … Cognito authorization code + PKCE、state検証、期限付きメモリ内token、logout
  - `js/pages.js` … 各画面のコントローラ
  - `css/styles.css` … 最小スタイル
- `tests/` … Python(pytest) による静的テスト（Node 不要）

## /api/* 呼び出し

`js/api.js` が以下を `fetch` で呼ぶ。認証後は、`auth.js` がメモリ内で期限管理するaccess tokenをAuthorization headerへ付与する。token値はファイル、localStorage、sessionStorageへ保存しない。

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

## Cognito連携

`config.js` は **プレースホルダ定数のみ**を持つ。実値・実ドメイン・実トークンは含めない。

- `USER_POOL_ID` / `APP_CLIENT_ID` / `REGION` / `COGNITO_DOMAIN` / `REDIRECT_URI` / `LOGOUT_URI`
  … `REPLACE_WITH_*` プレースホルダ。`deploy-frontend.sh`がTerraform output由来の環境値から一時`config.js`を生成する。
- `API_BASE` … 既定 `/api`（同一オリジン）。

ログイン要求では暗号学的乱数の`state`とPKCE verifier/challenge（S256）を生成する。短命な`state`とverifierだけをsessionStorageへ保存し、callbackで完全一致を確認してからauthorization codeをtokenへ交換する。不一致時は交換せず、tokenも保存せず画面へエラーを表示する。access tokenはメモリ内だけに保持し、`expires_in`経過後に破棄する。logoutはメモリとsessionStorageを消去してCognito logout URLへ遷移する。

## テスト

```
python3 -m pytest tests -q
```

HTML/CSS/JS の内容を静的に解析し、画面要素の存在・4 エンドポイント参照・config が
プレースホルダのみ・status_id の「/」非許容を検証する（既存 IaC スナップショットテストと
同方式、Node 不要）。

## デプロイ

buildは不要。`scripts/deploy-frontend.sh`は配信ファイルを一時ディレクトリへ複製し、Terraform output由来の非機微値から`config.js`を生成する。生成物全体に`${...}`または`REPLACE_WITH_*`が残ればS3 sync前に異常終了する。既定はdry-runで、`--execute`指定時だけS3 syncとCloudFront invalidationを行う。

検証はPython静的テスト、Node認証フローテスト、Hypothesis state property testで行う。実Cognito/API Gateway/CloudFrontへの接続はCategory CとしてOperator承認後に実施する。
