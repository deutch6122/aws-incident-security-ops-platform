# Terraform 構成

design.md の「デプロイ設計（Terraform ディレクトリ構成）」を要約する（Req 20, 26.2）。

## ディレクトリ構成

```
infra/
  environments/
    dev/            # env 固有の設定・backend 参照・provider・共通変数・命名 helper
  modules/          # 再利用可能なモジュール群
    network/  ecr/  alb/  ecs/  eks/  aurora/  messaging/
    s3-portal/  cloudfront/  waf/  cognito/  apigateway/
    lambda/  dynamodb/  logging/  monitoring/  iam/
```

- インフラは Terraform で定義し、`infra/environments/dev` と `infra/modules/*` に分離する（Req 20.1, 20.2）。
- リージョンは `ap-northeast-1`（Req 19.3）。命名規則 `ops-platform-dev-<resource>`（Req 19.1）、全リソースへ識別タグ（Req 19.2）。

## 命名 helper と共通タグ

- 命名 helper は `ops-platform-dev-<resource>` を生成し、パターン `^ops-platform-dev-.+` に一致する（Property 11、Req 19.1）。
- 共通タグ（locals）で project=`ops-platform`、env=`dev`、Platform 識別タグを全リソースへ付与する。

## モジュール一覧（責務）

| モジュール | 責務 |
| --- | --- |
| network | VPC/Subnet/SG/NAT/IGW/VPCエンドポイント |
| ecr | backend-api / eks-workers 用リポジトリ |
| alb | ALB / Target Group / リスナー / アクセスログ |
| ecs | cluster / task / service / autoscaling（設計含有） |
| eks | クラスタ / Fargate Profile / IRSA / ログルーター |
| aurora | Aurora Serverless v2 + Secrets Manager 連携 |
| messaging | SQS + DLQ + EventBridge |
| s3-portal | Portal_Storage（OAC 保護） |
| cloudfront | CloudFront + OAC + WAF |
| waf | WAF Web ACL（cloudfront と統合可） |
| cognito | User Pool / App Client |
| apigateway | `/api/*` + Cognito JWT Authorizer |
| lambda | Portal_API Lambda |
| dynamodb | Portal_DB 4テーブル |
| logging | CloudWatch Logs グループ |
| monitoring | Alarm / Dashboard / SNS |
| iam | 最小権限ロール群 |
