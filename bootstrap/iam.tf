# ---------------------------------------------------------------------------
# IAM: terraform-exec role（最小権限を意識）+ CodeBuild / CodePipeline サービスロール
# ---------------------------------------------------------------------------
# 対応要件: Req 17.1, 17.2, 17.3, 21.1
#
# 最小権限方針:
#   - AdministratorAccess は付与しない。
#   - Action:"*" + Resource:"*" のワイルドカード全許可は使用しない。
#   - 本 Platform が作成するサービス群に必要なアクションへサービス単位でスコープする。
#   - MVP 段階では Resource を "*" にしている箇所（ネットワーク/ECS/EKS/ECR/RDS/
#     SQS/EventBridge/SNS/WAF/Cognito/CloudFront/CloudWatch 等）を許容する。これは
#     多くの AWS サービスの Create 系 API が作成前にリソース ARN を特定できないため
#     （例: VPC, EKS 等）であり、その場合でも Action はサービス単位に制限している
#     （Action:"*" は使わない）。
#   - 本番想定（段階的絞り込み）: apply 後に確定する ARN やタグ条件
#     （aws:RequestTag / aws:ResourceTag = Project=ops-platform）で Resource /
#     Condition をさらに制限していく。
#   - iam:PassRole は iam:PassedToService 条件で渡す先サービスを限定済み。
# ---------------------------------------------------------------------------

# ===========================================================================
# terraform-exec Role
# ===========================================================================
# CodeBuild（Infra_Pipeline）が Terraform を実行するために assume するロール。
#
# 推奨: codebuild-role → terraform-exec-role の AssumeRole 分離設計
#   - CodeBuild Project の service_role には codebuild-role を割り当てる。
#   - codebuild-role が sts:AssumeRole で terraform-exec-role を引き受けたうえで
#     Terraform を実行する（権限分離）。
#   - したがって本ロールの信頼ポリシーの Principal は codebuild.amazonaws.com
#     サービスプリンシパルではなく、codebuild-role（IAM ロール ARN）とする。
#   - codebuild-role 側には AssumeTerraformExec（sts:AssumeRole to terraform_exec.arn）
#     を付与済みで、双方向で整合している。
#
# 循環参照について:
#   本ポリシードキュメントは aws_iam_role.codebuild.arn を参照し、codebuild ロールの
#   インラインポリシーは aws_iam_role.terraform_exec.arn を参照するが、ロール ARN は
#   各ロールリソースの属性であり相互のポリシー内容に依存しないため、Terraform の
#   依存解決上で循環にはならない（role リソース同士は独立に作成できる）。
data "aws_iam_policy_document" "terraform_exec_assume" {
  statement {
    sid     = "AllowCodeBuildRoleAssume"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    # codebuild-role からの assume のみ許可（サービス直 assume ではなくロール ARN 指定）。
    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.codebuild.arn]
    }
  }
}

resource "aws_iam_role" "terraform_exec" {
  name               = "${local.name_prefix}-terraform-exec-role"
  assume_role_policy = data.aws_iam_policy_document.terraform_exec_assume.json

  tags = {
    Name = "${local.name_prefix}-terraform-exec-role"
    Role = "terraform-exec"
  }
}

# ---------------------------------------------------------------------------
# terraform-exec 用ポリシー（サービス単位でスコープ）
# ---------------------------------------------------------------------------
# 注意: NotAction や "*" 全許可は使わず、サービスごとにアクションを列挙する。
data "aws_iam_policy_document" "terraform_exec" {

  # --- state backend アクセス（remote state S3, 任意 DynamoDB lock）-----------
  statement {
    sid    = "TerraformStateS3"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    # state バケットとその配下オブジェクトに限定（Resource 制約）。
    resources = [
      aws_s3_bucket.tfstate.arn,
      "${aws_s3_bucket.tfstate.arn}/*",
    ]
  }

  statement {
    sid    = "TerraformStateLockDynamoDB"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
    ]
    # lock table 名パターンに限定（作成する場合のみ意味を持つ）。
    resources = [
      "arn:aws:dynamodb:${var.aws_region}:${local.account_id}:table/${local.name_prefix}-tfstate-lock",
    ]
  }

  # --- ネットワーク（VPC/EC2 系）--------------------------------------------
  # VPC/Subnet/SG/NAT/IGW/Route/VPC Endpoint 等。多くが作成時 ARN 不定のため
  # サービス単位のアクション制約とする（TODO: タグ Condition 追加）。
  statement {
    sid    = "NetworkEC2"
    effect = "Allow"
    actions = [
      "ec2:Describe*",
      "ec2:CreateVpc",
      "ec2:DeleteVpc",
      "ec2:ModifyVpcAttribute",
      "ec2:CreateSubnet",
      "ec2:DeleteSubnet",
      "ec2:ModifySubnetAttribute",
      "ec2:CreateSecurityGroup",
      "ec2:DeleteSecurityGroup",
      "ec2:AuthorizeSecurityGroup*",
      "ec2:RevokeSecurityGroup*",
      "ec2:CreateInternetGateway",
      "ec2:DeleteInternetGateway",
      "ec2:AttachInternetGateway",
      "ec2:DetachInternetGateway",
      "ec2:CreateNatGateway",
      "ec2:DeleteNatGateway",
      "ec2:AllocateAddress",
      "ec2:ReleaseAddress",
      "ec2:CreateRouteTable",
      "ec2:DeleteRouteTable",
      "ec2:CreateRoute",
      "ec2:DeleteRoute",
      "ec2:AssociateRouteTable",
      "ec2:DisassociateRouteTable",
      "ec2:CreateVpcEndpoint",
      "ec2:DeleteVpcEndpoints",
      "ec2:ModifyVpcEndpoint",
      "ec2:CreateTags",
      "ec2:DeleteTags",
    ]
    resources = ["*"] # TODO: aws:ResourceTag/Project=ops-platform 等で段階的に制限
  }

  # --- ELB (ALB) ------------------------------------------------------------
  statement {
    sid    = "LoadBalancing"
    effect = "Allow"
    actions = [
      "elasticloadbalancing:Describe*",
      "elasticloadbalancing:Create*",
      "elasticloadbalancing:Delete*",
      "elasticloadbalancing:Modify*",
      "elasticloadbalancing:Register*",
      "elasticloadbalancing:Deregister*",
      "elasticloadbalancing:AddTags",
      "elasticloadbalancing:RemoveTags",
      "elasticloadbalancing:SetSecurityGroups",
      "elasticloadbalancing:SetSubnets",
    ]
    resources = ["*"] # TODO: ALB ARN 確定後にタグ Condition で制限
  }

  # --- ECS ------------------------------------------------------------------
  statement {
    sid    = "ECS"
    effect = "Allow"
    actions = [
      "ecs:Describe*",
      "ecs:List*",
      "ecs:CreateCluster",
      "ecs:DeleteCluster",
      "ecs:CreateService",
      "ecs:UpdateService",
      "ecs:DeleteService",
      "ecs:RegisterTaskDefinition",
      "ecs:DeregisterTaskDefinition",
      "ecs:TagResource",
      "ecs:UntagResource",
    ]
    resources = ["*"]
  }

  # --- EKS ------------------------------------------------------------------
  statement {
    sid    = "EKS"
    effect = "Allow"
    actions = [
      "eks:Describe*",
      "eks:List*",
      "eks:CreateCluster",
      "eks:DeleteCluster",
      "eks:UpdateClusterConfig",
      "eks:UpdateClusterVersion",
      "eks:CreateFargateProfile",
      "eks:DeleteFargateProfile",
      "eks:CreateNodegroup",
      "eks:DeleteNodegroup",
      "eks:TagResource",
      "eks:UntagResource",
      "eks:CreateAddon",
      "eks:DeleteAddon",
      "eks:AssociatePodIdentity",
    ]
    resources = ["*"]
  }

  # --- ECR ------------------------------------------------------------------
  statement {
    sid    = "ECR"
    effect = "Allow"
    actions = [
      "ecr:Describe*",
      "ecr:List*",
      "ecr:GetRepositoryPolicy",
      "ecr:CreateRepository",
      "ecr:DeleteRepository",
      "ecr:SetRepositoryPolicy",
      "ecr:PutLifecyclePolicy",
      "ecr:PutImageScanningConfiguration",
      "ecr:TagResource",
      "ecr:UntagResource",
    ]
    resources = ["*"]
  }

  # --- RDS / Aurora ---------------------------------------------------------
  statement {
    sid    = "RDSAurora"
    effect = "Allow"
    actions = [
      "rds:Describe*",
      "rds:ListTagsForResource",
      "rds:CreateDBCluster",
      "rds:DeleteDBCluster",
      "rds:ModifyDBCluster",
      "rds:CreateDBInstance",
      "rds:DeleteDBInstance",
      "rds:ModifyDBInstance",
      "rds:CreateDBSubnetGroup",
      "rds:DeleteDBSubnetGroup",
      "rds:AddTagsToResource",
      "rds:RemoveTagsFromResource",
    ]
    resources = ["*"]
  }

  # --- SQS ------------------------------------------------------------------
  statement {
    sid    = "SQS"
    effect = "Allow"
    actions = [
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
      "sqs:ListQueues",
      "sqs:ListQueueTags",
      "sqs:CreateQueue",
      "sqs:DeleteQueue",
      "sqs:SetQueueAttributes",
      "sqs:TagQueue",
      "sqs:UntagQueue",
    ]
    resources = ["*"]
  }

  # --- EventBridge ----------------------------------------------------------
  statement {
    sid    = "EventBridge"
    effect = "Allow"
    actions = [
      "events:Describe*",
      "events:List*",
      "events:PutRule",
      "events:DeleteRule",
      "events:PutTargets",
      "events:RemoveTargets",
      "events:TagResource",
      "events:UntagResource",
    ]
    resources = ["*"]
  }

  # --- SNS ------------------------------------------------------------------
  statement {
    sid    = "SNS"
    effect = "Allow"
    actions = [
      "sns:Get*",
      "sns:List*",
      "sns:CreateTopic",
      "sns:DeleteTopic",
      "sns:SetTopicAttributes",
      "sns:Subscribe",
      "sns:Unsubscribe",
      "sns:TagResource",
      "sns:UntagResource",
    ]
    resources = ["*"]
  }

  # --- DynamoDB (Portal_DB) -------------------------------------------------
  statement {
    sid    = "DynamoDB"
    effect = "Allow"
    actions = [
      "dynamodb:Describe*",
      "dynamodb:List*",
      "dynamodb:CreateTable",
      "dynamodb:DeleteTable",
      "dynamodb:UpdateTable",
      "dynamodb:UpdateTimeToLive",
      "dynamodb:TagResource",
      "dynamodb:UntagResource",
    ]
    # 本 Platform の DynamoDB テーブル（命名規則 prefix）に限定。
    resources = [
      "arn:aws:dynamodb:${var.aws_region}:${local.account_id}:table/${local.name_prefix}-*",
    ]
  }

  # --- S3 (Portal_Storage 等、Platform が作成するバケット) -------------------
  # state/artifact バケットは別 statement / 別ロールで管理。ここでは Platform 用
  # バケット作成に必要なアクションを付与する（バケット名パターンで制約）。
  statement {
    sid    = "PlatformS3Manage"
    effect = "Allow"
    actions = [
      "s3:CreateBucket",
      "s3:DeleteBucket",
      "s3:PutBucketPolicy",
      "s3:GetBucketPolicy",
      "s3:PutBucketPublicAccessBlock",
      "s3:GetBucketPublicAccessBlock",
      "s3:PutBucketVersioning",
      "s3:GetBucketVersioning",
      "s3:PutEncryptionConfiguration",
      "s3:GetEncryptionConfiguration",
      "s3:PutBucketTagging",
      "s3:GetBucketTagging",
      "s3:PutBucketAcl",
    ]
    resources = [
      "arn:aws:s3:::${local.name_prefix}-*",
    ]
  }

  # --- CloudFront -----------------------------------------------------------
  statement {
    sid    = "CloudFront"
    effect = "Allow"
    actions = [
      "cloudfront:Get*",
      "cloudfront:List*",
      "cloudfront:CreateDistribution",
      "cloudfront:UpdateDistribution",
      "cloudfront:DeleteDistribution",
      "cloudfront:CreateOriginAccessControl",
      "cloudfront:UpdateOriginAccessControl",
      "cloudfront:DeleteOriginAccessControl",
      "cloudfront:TagResource",
      "cloudfront:UntagResource",
    ]
    resources = ["*"] # CloudFront はグローバルリソースのため "*"（TODO: タグ Condition）
  }

  # --- WAF (WAFv2) ----------------------------------------------------------
  statement {
    sid    = "WAF"
    effect = "Allow"
    actions = [
      "wafv2:Get*",
      "wafv2:List*",
      "wafv2:CreateWebACL",
      "wafv2:UpdateWebACL",
      "wafv2:DeleteWebACL",
      "wafv2:AssociateWebACL",
      "wafv2:DisassociateWebACL",
      "wafv2:TagResource",
      "wafv2:UntagResource",
    ]
    resources = ["*"]
  }

  # --- Cognito --------------------------------------------------------------
  statement {
    sid    = "Cognito"
    effect = "Allow"
    actions = [
      "cognito-idp:Describe*",
      "cognito-idp:List*",
      "cognito-idp:CreateUserPool",
      "cognito-idp:DeleteUserPool",
      "cognito-idp:UpdateUserPool",
      "cognito-idp:CreateUserPoolClient",
      "cognito-idp:DeleteUserPoolClient",
      "cognito-idp:UpdateUserPoolClient",
      "cognito-idp:CreateUserPoolDomain",
      "cognito-idp:DeleteUserPoolDomain",
      "cognito-idp:TagResource",
      "cognito-idp:UntagResource",
    ]
    resources = ["*"]
  }

  # --- API Gateway ----------------------------------------------------------
  statement {
    sid    = "APIGateway"
    effect = "Allow"
    actions = [
      "apigateway:GET",
      "apigateway:POST",
      "apigateway:PUT",
      "apigateway:PATCH",
      "apigateway:DELETE",
    ]
    # API Gateway のリソースは /restapis, /apis 等。account 内に限定。
    resources = [
      "arn:aws:apigateway:${var.aws_region}::/*",
    ]
  }

  # --- Lambda ---------------------------------------------------------------
  statement {
    sid    = "Lambda"
    effect = "Allow"
    actions = [
      "lambda:Get*",
      "lambda:List*",
      "lambda:CreateFunction",
      "lambda:DeleteFunction",
      "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration",
      "lambda:AddPermission",
      "lambda:RemovePermission",
      "lambda:TagResource",
      "lambda:UntagResource",
      "lambda:CreateEventSourceMapping",
      "lambda:DeleteEventSourceMapping",
      "lambda:UpdateEventSourceMapping",
    ]
    resources = [
      "arn:aws:lambda:${var.aws_region}:${local.account_id}:function:${local.name_prefix}-*",
      "arn:aws:lambda:${var.aws_region}:${local.account_id}:event-source-mapping:*",
    ]
  }

  # --- Secrets Manager ------------------------------------------------------
  statement {
    sid    = "SecretsManager"
    effect = "Allow"
    actions = [
      "secretsmanager:Describe*",
      "secretsmanager:List*",
      "secretsmanager:GetResourcePolicy",
      "secretsmanager:CreateSecret",
      "secretsmanager:DeleteSecret",
      "secretsmanager:UpdateSecret",
      "secretsmanager:PutSecretValue",
      "secretsmanager:TagResource",
      "secretsmanager:UntagResource",
    ]
    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${local.account_id}:secret:${local.name_prefix}-*",
    ]
  }

  # --- CloudWatch Logs ------------------------------------------------------
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:Describe*",
      "logs:List*",
      "logs:CreateLogGroup",
      "logs:DeleteLogGroup",
      "logs:PutRetentionPolicy",
      "logs:TagResource",
      "logs:UntagResource",
      "logs:TagLogGroup",
      "logs:UntagLogGroup",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:/${var.project}-${var.env}/*",
      "arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:*",
    ]
  }

  # --- CloudWatch Alarms / Dashboards --------------------------------------
  statement {
    sid    = "CloudWatch"
    effect = "Allow"
    actions = [
      "cloudwatch:Describe*",
      "cloudwatch:List*",
      "cloudwatch:GetDashboard",
      "cloudwatch:PutMetricAlarm",
      "cloudwatch:DeleteAlarms",
      "cloudwatch:PutDashboard",
      "cloudwatch:DeleteDashboards",
      "cloudwatch:TagResource",
      "cloudwatch:UntagResource",
    ]
    resources = ["*"]
  }

  # --- IAM（必要な範囲）------------------------------------------------------
  # Platform が作成するロール/ポリシー（命名 prefix）に限定。
  # 権限昇格を防ぐため account 全体の IAM 管理権限は付与しない。
  # TODO: iam:PassRole は渡す先サービスを Condition(iam:PassedToService) で制限する。
  statement {
    sid    = "IAMManageScoped"
    effect = "Allow"
    actions = [
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:GetPolicy",
      "iam:GetPolicyVersion",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:ListPolicyVersions",
      "iam:ListInstanceProfilesForRole",
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:UpdateRole",
      "iam:CreatePolicy",
      "iam:DeletePolicy",
      "iam:CreatePolicyVersion",
      "iam:DeletePolicyVersion",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:TagPolicy",
      "iam:UntagPolicy",
      "iam:CreateOpenIDConnectProvider", # IRSA 用
      "iam:DeleteOpenIDConnectProvider",
      "iam:TagOpenIDConnectProvider",
    ]
    resources = [
      "arn:aws:iam::${local.account_id}:role/${local.name_prefix}-*",
      "arn:aws:iam::${local.account_id}:policy/${local.name_prefix}-*",
      "arn:aws:iam::${local.account_id}:oidc-provider/*",
    ]
  }

  statement {
    sid    = "IAMPassRoleScoped"
    effect = "Allow"
    actions = [
      "iam:PassRole",
    ]
    resources = [
      "arn:aws:iam::${local.account_id}:role/${local.name_prefix}-*",
    ]
    # PassRole 先を本 Platform が実際に利用する AWS サービスに限定する（権限昇格の抑止）。
    # 過剰付与を避けるため、Platform 構成に必要なサービスのみを列挙する。
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values = [
        "ecs-tasks.amazonaws.com",
        "eks.amazonaws.com",
        "eks-fargate-pods.amazonaws.com",
        "lambda.amazonaws.com",
        "codebuild.amazonaws.com",
      ]
    }
  }
}

resource "aws_iam_policy" "terraform_exec" {
  name        = "${local.name_prefix}-terraform-exec-policy"
  # 最小権限方針: 管理者相当の権限や Action/Resource 全許可ワイルドカードは使用しない。
  description = "Least-privilege(ish) policy for Terraform execution via CodeBuild (service-scoped, no full wildcard)."
  policy      = data.aws_iam_policy_document.terraform_exec.json

  tags = {
    Name = "${local.name_prefix}-terraform-exec-policy"
  }
}

resource "aws_iam_role_policy_attachment" "terraform_exec" {
  role       = aws_iam_role.terraform_exec.name
  policy_arn = aws_iam_policy.terraform_exec.arn
}

# ===========================================================================
# CodeBuild サービスロール
# ===========================================================================
# CodeBuild 自体の実行に必要な権限（ログ出力、artifact S3 R/W、terraform-exec の assume）。
data "aws_iam_policy_document" "codebuild_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "codebuild" {
  name               = "${local.name_prefix}-codebuild-role"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume.json

  tags = {
    Name = "${local.name_prefix}-codebuild-role"
    Role = "codebuild-service"
  }
}

data "aws_iam_policy_document" "codebuild" {
  # CodeBuild 自身のログ
  statement {
    sid    = "CodeBuildLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:/aws/codebuild/${local.name_prefix}-*",
      "arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:/aws/codebuild/${local.name_prefix}-*:*",
    ]
  }

  # artifact S3 の読み書き（plan バイナリの受け渡し等）
  statement {
    sid    = "CodeBuildArtifacts"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.artifacts.arn,
      "${aws_s3_bucket.artifacts.arn}/*",
    ]
  }

  # Terraform 実行は terraform-exec-role を assume して行う（権限分離）。
  statement {
    sid       = "AssumeTerraformExec"
    effect    = "Allow"
    actions   = ["sts:AssumeRole"]
    resources = [aws_iam_role.terraform_exec.arn]
  }

  # CodeBuild レポート/バッチ用の最小権限（任意）
  statement {
    sid    = "CodeBuildReports"
    effect = "Allow"
    actions = [
      "codebuild:CreateReportGroup",
      "codebuild:CreateReport",
      "codebuild:UpdateReport",
      "codebuild:BatchPutTestCases",
      "codebuild:BatchPutCodeCoverages",
    ]
    resources = [
      "arn:aws:codebuild:${var.aws_region}:${local.account_id}:report-group/${local.name_prefix}-*",
    ]
  }
}

resource "aws_iam_role_policy" "codebuild" {
  name   = "${local.name_prefix}-codebuild-policy"
  role   = aws_iam_role.codebuild.id
  policy = data.aws_iam_policy_document.codebuild.json
}

# CodeBuild が terraform-exec-role を assume できるよう、terraform-exec-role の
# 信頼ポリシー（data.aws_iam_policy_document.terraform_exec_assume）の Principal に
# 本 codebuild-role の ARN を指定している（AssumeRole 分離設計）。
# 呼び出し元（codebuild-role）側には上記 AssumeTerraformExec statement で
# sts:AssumeRole を許可済みであり、双方向で整合している。

# ===========================================================================
# CodePipeline サービスロール
# ===========================================================================
data "aws_iam_policy_document" "codepipeline_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["codepipeline.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "codepipeline" {
  name               = "${local.name_prefix}-codepipeline-role"
  assume_role_policy = data.aws_iam_policy_document.codepipeline_assume.json

  tags = {
    Name = "${local.name_prefix}-codepipeline-role"
    Role = "codepipeline-service"
  }
}

data "aws_iam_policy_document" "codepipeline" {
  # artifact S3
  statement {
    sid    = "PipelineArtifacts"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:GetBucketLocation",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.artifacts.arn,
      "${aws_s3_bucket.artifacts.arn}/*",
    ]
  }

  # CodeBuild 起動
  statement {
    sid    = "PipelineStartBuild"
    effect = "Allow"
    actions = [
      "codebuild:BatchGetBuilds",
      "codebuild:StartBuild",
    ]
    resources = [aws_codebuild_project.terraform.arn]
  }

  # CodeStar Connections（Source: GitHub 等）
  statement {
    sid    = "PipelineUseConnection"
    effect = "Allow"
    actions = [
      "codestar-connections:UseConnection",
    ]
    # 接続 ARN が指定されていればそれに限定、なければ account 内の connection に限定。
    resources = [
      var.codestar_connection_arn != "" ? var.codestar_connection_arn : "arn:aws:codestar-connections:${var.aws_region}:${local.account_id}:connection/*",
    ]
  }
}

resource "aws_iam_role_policy" "codepipeline" {
  name   = "${local.name_prefix}-codepipeline-policy"
  role   = aws_iam_role.codepipeline.id
  policy = data.aws_iam_policy_document.codepipeline.json
}
