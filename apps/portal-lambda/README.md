# apps/portal-lambda

Product_B（CloudFront 配信ポータル）の Portal_API。Python の AWS Lambda 関数として動作し、API Gateway HTTP API v2（payload format 2.0）+ Cognito JWT Authorizer（Task 14）の背後で稼働する。DynamoDB（Portal_DB）4 テーブルのみを参照し、書き込みは `page_view_logs` の閲覧ログのみ。Product_A（Backend API / Aurora / ECS / EKS / Product_A SQS）へは一切アクセスしない。

## エンドポイント

| メソッド / パス | 役割 | 参照 / 記録 |
| --- | --- | --- |
| `GET /api/status` | 障害ステータス一覧 | `public_status_items` 読取、`page_view_logs` へ 1 件記録（Req 10.1, 10.3） |
| `GET /api/status/{id}` | 障害詳細 | `public_status_items` 読取、`page_view_logs` へ 1 件記録。未登録 ID は 404（Req 10.2, 10.3） |
| `GET /api/reports` | 月次レポート一覧 | `report_metadata` 読取（Req 11.1） |
| `GET /api/reports/{id}` | レポート詳細（メタ＋ファイル参照情報） | `report_metadata` 読取。未登録は 404（Req 11.2, 11.3） |

- JWT 欠落 / claims 不正時はすべて 401（fail-closed、Req 9.3）。401 時は `page_view_logs` に書き込まない。
- レポート詳細はメタ情報と Portal_Storage 上のオブジェクト参照（S3 キー/プレフィックス等）のみを返す。**S3 実アクセス・署名 URL 生成は行わない**（配信は Task 13 の S3/CloudFront が担う）。

## パッケージ構成

```
app/
  config.py         非シークレット設定（AWS region と Product_B テーブル名のみ）。読取時に AWS I/O なし
  auth.py           JWT claims 検証（requestContext.authorizer.jwt.claims）。欠落/不正は fail-closed 401
  stores.py         リポジトリ Protocol と in-memory fake（テスト用の Portal_DB 代替）
  repositories.py   DynamoDB(boto3) 実装。boto3 は初回利用時に遅延生成（import 時に接続しない）
  services.py       StatusService（閲覧ログ 1 件記録＋本体不変）/ ReportService（一覧・詳細・404）
  errors.py         ApiError と HTTP API v2 JSON レスポンスヘルパ
  handler.py        Lambda エントリポイント。routeKey もしくは rawPath+method でルーティング
tests/              単体テスト・Property 10（Hypothesis, fake ベース）
```

## ルーティング

`app.handler._method_and_path` は API Gateway HTTP API v2 event の `routeKey`（例 `GET /api/status`）を第一に使い、`$default` や欠落時は `rawPath` + `requestContext.http.method` にフォールバックする。GET 以外は 404。

## 認証 / JWT claims 確認方針

- 実際の JWT 署名・有効期限検証は前段の **API Gateway Cognito JWT Authorizer（Task 14）** が担う。Lambda 単体では署名を再検証しない。
- Lambda は `event.requestContext.authorizer.jwt.claims` を確認し、**欠落・空・subject を特定できない場合は fail-closed で 401** を返す（`app/auth.py`）。有効な subject（`sub` / `cognito:username` / `username` / `email` のいずれか）を持つ claims があれば Viewer とみなす。
- トークン・Authorization ヘッダ・認証情報の値をログや応答本文に載せない。

## DynamoDB アクセス層 / AWS 非接続方針

- `app/repositories.py` は boto3 の DynamoDB resource を **初回テーブル操作時に遅延生成**する。モジュール import 時に AWS 接続・認証情報要求・環境変数必須化・Secret 取得を行わない。
- 抽象リポジトリ（`app/stores.py` の Protocol）に対し、DynamoDB 実装（`repositories.py`）と in-memory fake（`stores.py`）を差し替え可能。**テストは fake を使用**し、AWS / Docker / moto / DynamoDB Local を必要としない。
- 参照は `public_status_items` / `report_metadata` の 2 テーブル（＋任意で `maintenance_windows`）、書込は `page_view_logs` のみ。IAM ロール（`infra/modules/lambda`）も同じ最小権限で構成されている。
- Secret（DB パスワード・接続 URL・認証ヘッダ・AWS 認証情報）はコード・README・テストに含めない。Portal_API は DynamoDB のみを扱い DB Secret を必要としない。

## 依存導入手順（実インストールはこのタスクでは行わない）

`requirements.txt`（`boto3`）と `requirements-test.txt`（`pytest` / `hypothesis`、任意で `moto[dynamodb]`）に記載。導入例（手順記載のみ）:

```
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-test.txt
```

## テスト方針

実 AWS / 実 DB / Docker へ接続しない。Portal_DB は `app/stores.py` の in-memory fake で代替する（DynamoDB のアイテム形状と、`page_view_logs` 追記のみ・`public_status_items` 読取専用という不変条件を再現）。moto / DynamoDB Local は任意で、未導入時はその変種のみ skip する。**fake ベースの Property 10 と単体テストは skip しない**。

- 単体テスト（`tests/test_portal_api_unit.py`）: JWT 欠落/不正 401、status 一覧/詳細/未登録 404、reports 一覧/詳細/未登録 404、閲覧ログ記録、`public_status_items` 本体不変、routeKey フォールバック。
- 安全性テスト（`tests/test_config_and_safety.py`）: import 時非 I/O、boto3 の import 時非ロード、Product_A 非参照、Product_B 4 テーブルのみ、機微リテラル非混入。
- Property 10（`tests/test_property10_view_side_effect.py`）: Hypothesis（`max_examples=100`）で「閲覧後 `page_view_logs` が +1、対象 `public_status_items` 本体不変」を検証。

```
python3 -m pytest tests -q -rs
```

> 既定の system Python に `hypothesis` が無い場合は、Hypothesis を含む既存 venv（例: リポジトリ内 `apps/backend-api/.venv`、`pytest` / `hypothesis` / `boto3` 導入済み）で実行できる。新規インストールは行わない。
