# module: cognito (Auth_Service)

Product_B（公開ポータル）の Viewer 認証基盤 Auth_Service を定義する。Cognito
User Pool と、Portal フロントエンド（SPA）が利用する public な App Client を構成する
（Requirement 9.1, 9.2）。User Pool が発行する JWT は、Portal_API の API Gateway
JWT Authorizer（Task 14.2）が検証する。

- 対応要件: Req 9.1, 9.2
- 実装: Task 14.1

## リソース

| リソース | 論理名 | 補足 |
| --- | --- | --- |
| `aws_cognito_user_pool` | `<name_prefix>-user-pool` | email サインイン、email 検証、パスワードポリシー |
| `aws_cognito_user_pool_client` | `<name_prefix>-portal-client` | public App Client。**client secret を作成しない** |

命名は `ops-platform-dev-<resource>` 準拠。`common_tags` を User Pool へ付与する
（App Client は tags 非対応）。

## 設計判断

- **App Client は client secret なし**（`generate_secret = false`）。ブラウザ上の
  SPA はシークレットを安全に保持できないため、public クライアントとして構成し、
  auth flow は SRP と refresh token に限定する（`prevent_user_existence_errors`
  有効）。
- **パスワードポリシー**（MVP 安全最小）: 最小長 `password_minimum_length`（既定 8）
  ＋小文字/大文字/数字/記号を必須。
- **account recovery** は verified_email のみ（phone フォールバックなし）。
- **username_configuration** は case_sensitive=false、`username_attributes=["email"]`。
- **admin_create_user_config** で `allow_admin_create_user_only=true`（MVP は管理者
  作成のみ、オープンなセルフサインアップを無効化）。
- **issuer_url** は `https://cognito-idp.<region>.amazonaws.com/<user_pool_id>` を
  ローカルで構築（`region` は provider から取得、実 User Pool ID は apply 時に解決）。
  実 ID は埋め込まない。

## Product_A / Product_B 分離

本モジュールは Product_B 専用。Aurora/RDS/EKS/ECS/SQS/Backend API への参照・依存を
一切持たない。

## 変数

- `name_prefix`（必須、例 `ops-platform-dev`）
- `common_tags`（必須）
- `password_minimum_length`（既定 8、範囲 8〜99）
- `aws_region`（既定 null＝provider リージョン。issuer_url 構築にのみ使用）

## 出力

- `user_pool_id` / `user_pool_arn` / `user_pool_endpoint`
- `app_client_id`
- `issuer_url`（API Gateway JWT Authorizer の issuer に使用）

## dev root への配線について（後続依存）

`infra/environments/dev` への配線は、Portal_API（Task 15）や CloudFront→API Gateway
の配線先確定後に行う。既存モジュールと同じ「実装したものだけ配線」方針に従い、Task 14
時点では dev ルートへは配線しない。

## テスト

`tests/test_cognito_snapshot.py` は Terraform/AWS を実行しない静的テスト。User Pool /
App Client の存在、App Client の client secret なし構成（`generate_secret = false`）、
命名/タグ、Product_A 非参照、機微リテラル非混入を検証する。
