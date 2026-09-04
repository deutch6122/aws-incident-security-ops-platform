# Product_A Backend API — Task 7 common foundation

Python/FastAPIによるProduct_A Backend APIのデータ層・共通HTTP基盤です。このディレクトリで実装済みなのは **Task 7.1〜7.5のみ** です。`dashboard`、`incidents`、`findings`、`summaries`などTask 8の業務APIは未実装です。

## パッケージ構成

- `app/main.py`: side effectのないapplication factory、公開health route、共通middleware
- `app/config.py`: 環境変数設定
- `app/security.py`, `app/errors.py`: Bearer認証、400/401/404/500、相関ID
- `app/db/`: 7表のSQLAlchemyモデル、Secrets Manager port、遅延Engine/Session生成
- `app/repositories.py`: incidents/comments/findings/triage/summaries/audit_logsの型付きCRUD・集計repository
- `app/domain/aggregation.py`: DB非依存の集計・変換関数
- `app/contracts.py`, `app/contract_store.py`: Task 7の401/400/404/500契約だけを確認する保護placeholder
- `tests/`: unit/static/API testsとProperty 2/4（Hypothesis、各100例）

`alarm_events`はマイグレーションとのモデル整合を保つためモデル化しています。Task 7.2のrepository対象外なのでrepositoryは後続タスクに委ねています。

## エンドポイント（Task 7限定）

| Method / path | 公開範囲 | 用途 |
| --- | --- | --- |
| `GET /health` | 公開 | コンテナhealth check。AWS/DBへ接続しない |
| `GET /docs`, `GET /openapi.json` | 公開 | FastAPI OpenAPI |
| `/_contracts/*` | Bearer必須 | 共通認証・入力・404・500契約のplaceholder |

`/_contracts/incidents/{id}`、`/_contracts/findings/{id}`、`/_contracts/summaries/{period}`はin-memory lookup portを使うテスト用contract routeです。業務データをCRUDするAPIではありません。

## 設定

設定元は環境変数のみです。値をリポジトリへ保存しないでください。

| 環境変数 | 内容 |
| --- | --- |
| `BACKEND_AWS_REGION` | Secrets Manager clientのregion |
| `BACKEND_DB_SECRET_ARN` | DB secretのARN（Secret値ではない） |
| `BACKEND_INTERNAL_BEARER_TOKEN` | Product_A MVPの内部Bearer credential |
| `BACKEND_APP_NAME` | 任意のOpenAPI title |

Secret JSONで必須のキー名は `username`、`password`、`host`、`port`、`dbname` です。Secret payload、password、完全なDB URLはログ・例外へ出しません。SQLAlchemy `URL.create`で特殊文字を安全に扱います。

認証tokenが未設定の場合、保護routeはfail-openせず401を返します。ローカル利用時もtokenは安全な設定経路から注入し、shell history、`.env`、README、テストfixtureへ固定値を書かないでください。

## ローカル起動

依存が既に用意された隔離環境で、必要な環境変数を安全に設定してから実行します。

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8080
```

この手順はAWS接続を実行しません。DBを実際に利用する後続処理が初めてSessionを要求した時だけ、注入されたSecretReaderを通じてcredentialを取得しEngineを遅延生成します。

## テスト

まずテスト依存を導入し、その後にテストとコンパイル検証を実行します。`requirements-test.txt`は`-r`で`requirements.txt`を内包し、FastAPI/uvicorn/SQLAlchemy/psycopg/boto3/pydantic-settings/pytest/httpx/Hypothesisを含みます。

```bash
python3 -m pip install -r requirements-test.txt
python3 -m pytest -q
python3 -m compileall -q app tests
```

依存を導入済みの環境（およびCI）では、以下のテストが`importorskip`でskipされず実行されます。

- FastAPI APIテスト（`tests/test_api.py`）
- SQLAlchemyモデル/Repositoryテスト（`tests/test_models_repositories.py`）
- Secret取得/DB URL構築テスト（`tests/test_secrets.py`）
- Property 2（`tests/test_property_authorization.py`、認可欠落401）
- Property 4（`tests/test_property_not_found.py`、未登録識別子404）

依存を導入していないローカル環境では、これらのテストは`importorskip`によりskipされ、依存不要の純粋ロジック・静的テストのみが実行されます。

テストはfake SecretReader、mocked Session、in-memory contract lookupを使い、AWS APIやAuroraへ接続しません。Docker/testcontainersはTask 7の必須条件ではありません。依存パッケージをこの検証のために自動インストールしません。

## セキュリティとTask境界

- 認証header欠落、不正scheme、不正credentialは常に401と`WWW-Authenticate: Bearer`。
- 認証middlewareはbody/path validationより先に保護prefixを拒否します。
- validation errorは400へ正規化し、必須欠落時は`missing_fields`を返します。
- `NotFoundError`は安全な404を生成します。
- 予期しない例外は500と検証済み／新規生成の相関IDを返し、Authorization headerをログに残しません。
- **Task 8以降の業務endpoint、AWS統合、実Aurora接続はこの実装範囲外です。**
