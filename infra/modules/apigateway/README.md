# module: apigateway (Portal_API front door)

Product_B（公開ポータル）の Portal_API 入口を定義する。HTTP API（apigatewayv2）で
`/api/*` ルートを公開し、Cognito JWT Authorizer で保護する（Requirement 9.3, 12.4）。
CloudFront は本 API を custom origin として参照する。

- 対応要件: Req 9.3, 12.4
- 実装: Task 14.2

## リソース

| リソース | 論理名 | 補足 |
| --- | --- | --- |
| `aws_apigatewayv2_api` | `<name_prefix>-portal-api` | HTTP API（protocol_type=HTTP） |
| `aws_apigatewayv2_authorizer` | `<name_prefix>-cognito-jwt` | JWT。issuer/audience を変数で受ける |
| `aws_apigatewayv2_integration` | (lambda) | AWS_PROXY。Lambda invoke ARN を変数で受ける |
| `aws_apigatewayv2_route` | `ANY /api/{proxy+}` | JWT authorizer 適用 |
| `aws_lambda_permission` | `AllowPortalApiGatewayInvoke` | API Gateway → Portal_API Lambda invoke の最小権限 |
| `aws_apigatewayv2_stage` | `<stage_name>`（既定 api） | auto_deploy |

命名は `ops-platform-dev-<resource>` 準拠。`common_tags` を API / Stage へ付与する。

## 設計判断

- **HTTP API（apigatewayv2）** を採用。REST API より低コスト・低レイテンシで小規模 dev
  に適し、Cognito JWT Authorizer を一級サポートする。
- **Cognito JWT Authorizer**（`authorizer_type=JWT`）: `jwt_configuration` に
  `issuer`（cognito モジュールの `issuer_url`）と `audience`（App Client id 群）を
  変数で受ける。`identity_sources=["$request.header.Authorization"]`。
- **Lambda 統合**（`integration_type=AWS_PROXY`、`payload_format_version=2.0`）:
  Portal_API Lambda の invoke ARN を変数で受ける。Lambda 本体は Task 15 で実装。
- **ルート `ANY /api/{proxy+}`** に authorizer を適用（`authorization_type=JWT`）。
  `/api/` 配下の全リクエストが有効トークンを要求される（Requirement 9.3）。
- **Lambda invoke 許可**（`aws_lambda_permission`）: API Gateway が Portal_API
  Lambda を呼び出す最小権限を付与する。`principal=apigateway.amazonaws.com`、
  `action=lambda:InvokeFunction`。`source_arn` は当該 API の execution ARN
  （`aws_apigatewayv2_api.this.execution_arn`）に限定し、wildcard は
  `/*/*`（メソッド/パス2階層）のみに留めて過度な広域付与を避ける。
  - `lambda_invoke_arn`（API Gateway integration 用）と `lambda_function_name`
    （`aws_lambda_permission` 用）は役割が異なる。前者は AWS_PROXY 統合の
    `integration_uri` に使う invoke ARN、後者は invoke 許可を付与する対象の
    Lambda 関数名。両方とも lambda module の対応する出力を dev root で配線する。
- **CloudFront origin 用出力** `api_domain_name` は `api_endpoint` から `https://`
  を除いた host。実ドメイン/実 ID は埋め込まない。

## Product_A / Product_B 分離

本モジュールは Product_B 専用。Portal_API Lambda（`lambda_invoke_arn`）とのみ統合し、
Product_A（Backend API / ECS / ALB / Aurora）へ直接接続しない。

## 変数

- `name_prefix`（必須）/ `common_tags`（必須）
- `jwt_issuer_url`（必須、https。cognito `issuer_url`）
- `jwt_audiences`（必須、非空リスト。App Client id 群）
- `lambda_invoke_arn`（必須。lambda `lambda_invoke_arn`。AWS_PROXY 統合用）
- `lambda_function_name`（必須。lambda `lambda_function_name`。`aws_lambda_permission` 用）
- `stage_name`（既定 `api`）

## 出力

- `api_id` / `api_endpoint` / `api_execution_arn`
- `api_domain_name`（CloudFront origin 用 host）
- `authorizer_id` / `stage_name`

## dev root への配線について（後続依存）

`infra/environments/dev` への配線は、cognito（Task 14.1）と lambda（Task 14.3）の
出力、および CloudFront origin の配線先確定後に行う。既存モジュールと同じ「実装した
ものだけ配線」方針に従い、Task 14 時点では dev ルートへは配線しない。

## テスト

`tests/test_apigateway_snapshot.py` は Terraform/AWS を実行しない静的テスト。`/api/*`
ルート・Cognito JWT Authorizer・AWS_PROXY 統合の存在、命名/タグ、Product_A 非参照、
機微リテラル非混入を検証する。
