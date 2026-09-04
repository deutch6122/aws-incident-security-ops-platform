# API 設計

design.md の「Components and Interfaces / Backend_API / Product_B API」を要約する（Req 26.2, 26.3）。

## Product_A API（Backend_API / ECS Fargate, FastAPI）

全 API で認可情報が必須。欠落時は 401（Req 2.3。Property 2）。OpenAPI(Swagger) を FastAPI で自動生成・公開する（Req 26.2）。

| メソッド / パス | 概要 | 主なエラー | 対応要件 |
| --- | --- | --- | --- |
| `GET /dashboard/summary` | インシデント/Finding 件数・ステータス別集計 | 401 | Req 2 |
| `GET /incidents` | インシデント一覧 | 401 | Req 3.1 |
| `GET /incidents/{id}` | インシデント詳細＋コメント | 401, 404 | Req 3.2, 3.3 |
| `POST /incidents` | インシデント作成 | 400（欠落項目提示）, 401 | Req 3.4, 3.5 |
| `PATCH /incidents/{id}/status` | ステータス更新＋監査記録 | 401, 404 | Req 3.6, 8.3 |
| `GET /findings` | Finding 一覧 | 401 | Req 4.1 |
| `GET /findings/{id}` | Finding 詳細＋triage | 401, 404 | Req 4.2, 4.3 |
| `GET /summaries/{yyyymm}` | 月次集計取得 | 401, 404 | Req 5.1, 5.2 |

### レスポンス例（概要）

- `GET /dashboard/summary` → `{ incident_count, finding_count, status_breakdown{} }`
  （incident_count/finding_count は件数と一致、status_breakdown の合計は総件数と一致。Property 1）

### エラー方針（Product_A）

| 状況 | 応答 |
| --- | --- |
| 認可情報欠落 | 401（Property 2） |
| 必須項目欠落 | 400 + 欠落項目（Property 5） |
| 未登録 ID / 年月 | 404（Property 4） |
| Aurora 一時不可 | 503（リトライ可） |
| 予期しない例外 | 500（相関 ID をログへ） |

## Product_B API（Portal_API / API Gateway + Lambda）

JWT 必須。欠落 / 無効時は 401（Req 9.3）。

| メソッド / パス | 概要 | 主なエラー | 対応要件 |
| --- | --- | --- | --- |
| `GET /api/status` | public_status_items 一覧（閲覧記録） | 401 | Req 10.1, 10.3 |
| `GET /api/status/{id}` | 障害詳細（閲覧記録） | 401 | Req 10.2, 10.3 |
| `GET /api/reports` | report_metadata 一覧 | 401 | Req 11.1 |
| `GET /api/reports/{id}` | メタ情報＋レポートファイル参照情報 | 401, 404 | Req 11.2, 11.3 |

### 副作用の不変条件

`GET /api/status` / `GET /api/status/{id}` の閲覧時に `page_view_logs` へちょうど 1 件記録し、`public_status_items` 本体は変更しない（Property 10）。

### レポートアクセス制御（MVP）

静的 HTML/JS は CloudFront+S3 で配信し、機微データ（レポート本体を含む）は API Gateway + Cognito JWT で保護する。MVP はダミー / 非機微のみを扱う。機微レポートは後続 Phase で署名付きアクセスを導入する。
