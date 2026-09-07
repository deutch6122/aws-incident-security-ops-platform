"""terraform-exec-role の最小権限を静的検証する（Req 17.2, 21.1）。

- "AdministratorAccess" を付与していないこと
- Action:"*" + Resource:"*" の全許可ワイルドカードが含まれないこと
terraform 実行・AWS 認証は不要。コメントを除去したうえで実コードを検査する。
"""

from __future__ import annotations

import re

from conftest import read_tf, strip_comments


def _iam_code_no_comments() -> str:
    return strip_comments(read_tf("iam.tf"))


def test_no_administrator_access():
    """AdministratorAccess 等の管理者相当マネージドポリシーを付与していないこと。

    マネージドポリシー ARN（arn:aws:iam::aws:policy/AdministratorAccess）や
    `managed_policy_arns` への Administrator/PowerUser 系の付与を検出したら失敗させる。
    説明文（description）中の言及は最小権限方針の記述であり許容する。
    """
    code = _iam_code_no_comments()

    forbidden = [
        "arn:aws:iam::aws:policy/AdministratorAccess",
        "arn:aws:iam::aws:policy/PowerUserAccess",
        "arn:aws:iam::aws:policy/IAMFullAccess",
    ]
    for arn in forbidden:
        assert arn not in code, f"管理者相当のマネージドポリシーが付与されている: {arn}"

    # policy_arn / managed_policy_arns への Administrator 付与を検出
    assert not re.search(
        r'(policy_arn|managed_policy_arns)\s*=.*Administrator', code, flags=re.DOTALL
    ), "Administrator 系マネージドポリシーの attach を検出（最小権限違反）"


def test_no_full_wildcard_allow():
    """Action:"*" と Resource:"*" を同時に許可する全許可 statement が存在しないこと。

    HCL の statement ブロックを走査し、actions に "*" 単独、かつ resources に "*"
    のみを含む Allow statement を検出したら失敗させる。
    """
    code = _iam_code_no_comments()

    # policy document の statement ブロックを粗く抽出
    statements = re.findall(r"statement\s*\{(.*?)\n\s*\}", code, flags=re.DOTALL)
    assert statements, "statement ブロックが抽出できなかった（テスト前提の破綻）"

    for stmt in statements:
        # actions のリスト内に "*" 単独が含まれるか
        actions_block = re.search(r"actions\s*=\s*\[(.*?)\]", stmt, flags=re.DOTALL)
        resources_block = re.search(r"resources\s*=\s*\[(.*?)\]", stmt, flags=re.DOTALL)
        if not actions_block or not resources_block:
            continue
        action_items = re.findall(r'"([^"]*)"', actions_block.group(1))
        resource_items = re.findall(r'"([^"]*)"', resources_block.group(1))

        has_action_star = any(a.strip() == "*" for a in action_items)
        has_resource_star = any(r.strip() == "*" for r in resource_items)

        assert not (has_action_star and has_resource_star), (
            f"Action:'*' + Resource:'*' の全許可 statement を検出（最小権限違反）: {stmt[:200]}"
        )


def test_terraform_exec_role_exists():
    """terraform-exec-role とそのポリシーが定義されていること。"""
    code = read_tf("iam.tf")
    assert 'resource "aws_iam_role" "terraform_exec"' in code
    assert 'resource "aws_iam_policy" "terraform_exec"' in code
    assert 'resource "aws_iam_role_policy_attachment" "terraform_exec"' in code


def test_no_notaction_escalation():
    """NotAction による広域許可（実質全許可）を使っていないこと。"""
    code = _iam_code_no_comments()
    assert "NotAction" not in code and "not_actions" not in code, (
        "NotAction/not_actions による広域許可は使用しないこと"
    )


def test_terraform_exec_trust_uses_codebuild_role_not_service():
    """terraform-exec-role の信頼ポリシーが codebuild-role を Principal(AWS) にしていること。

    AssumeRole 分離設計: サービスプリンシパル codebuild.amazonaws.com 直 assume ではなく、
    codebuild-role（aws_iam_role.codebuild.arn）を type=AWS の Principal に指定する。
    """
    code = read_tf("iam.tf")
    m = re.search(
        r'data\s+"aws_iam_policy_document"\s+"terraform_exec_assume"\s*\{(.*?)\n\}',
        code,
        flags=re.DOTALL,
    )
    assert m, "terraform_exec_assume の policy document が見つからない"
    block = m.group(1)

    # principals ブロック内で type = "AWS" かつ codebuild ロール ARN を参照している。
    assert re.search(r'type\s*=\s*"AWS"', block), (
        "terraform-exec-role の信頼ポリシー Principal が type=AWS になっていない"
    )
    assert "aws_iam_role.codebuild.arn" in block, (
        "terraform-exec-role の信頼ポリシーが codebuild-role の ARN を参照していない"
    )
    # サービスプリンシパルでの直 assume（type=Service + codebuild.amazonaws.com）でないこと。
    assert not re.search(
        r'type\s*=\s*"Service"[^}]*codebuild\.amazonaws\.com', block, flags=re.DOTALL
    ), "terraform-exec-role がサービスプリンシパル codebuild.amazonaws.com で直 assume されている"


def test_passrole_has_passedtoservice_condition():
    """iam:PassRole の statement に iam:PassedToService の condition が存在すること。"""
    code = read_tf("iam.tf")
    m = re.search(
        r'sid\s*=\s*"IAMPassRoleScoped"(.*?)\n  \}',
        code,
        flags=re.DOTALL,
    )
    assert m, "IAMPassRoleScoped statement が見つからない"
    block = m.group(1)
    assert "iam:PassRole" in block, "IAMPassRoleScoped に iam:PassRole がない"
    assert 'variable = "iam:PassedToService"' in block, (
        "iam:PassRole に iam:PassedToService の condition がない"
    )
    assert re.search(r'test\s*=\s*"StringEquals"', block), (
        "iam:PassedToService condition が StringEquals になっていない"
    )
    assert 'values   = ["ecs-tasks.amazonaws.com"]' in block or (
        'values = ["ecs-tasks.amazonaws.com"]' in block
    )
    for forbidden_service in (
        "eks.amazonaws.com",
        "eks-fargate-pods.amazonaws.com",
        "lambda.amazonaws.com",
        "codebuild.amazonaws.com",
    ):
        assert forbidden_service not in block


def test_passrole_allowlist_contains_exactly_four_task_roles():
    code = read_tf("iam.tf")
    match = re.search(
        r'sid\s*=\s*"IAMPassRoleScoped"(.*?)\n  \}',
        code,
        flags=re.DOTALL,
    )
    assert match
    block = match.group(1)
    expected_suffixes = (
        "-ecs-task-execution-role",
        "-ecs-task-role",
        "-migration-execution-role",
        "-migration-task-role",
    )
    for suffix in expected_suffixes:
        assert block.count(suffix) == 1
    assert block.count(":role/") == 4
    assert "role/${local.name_prefix}-*" not in block
    assert "data.aws_partition.current.partition" in block


def test_codebuild_can_assume_terraform_exec():
    """codebuild-role 側に terraform-exec-role への sts:AssumeRole 許可があること（整合）。"""
    code = read_tf("iam.tf")
    m = re.search(
        r'sid\s*=\s*"AssumeTerraformExec"(.*?)\n  \}',
        code,
        flags=re.DOTALL,
    )
    assert m, "AssumeTerraformExec statement が見つからない"
    block = m.group(1)
    assert "sts:AssumeRole" in block
    assert "aws_iam_role.terraform_exec.arn" in block, (
        "codebuild-role が terraform-exec-role の ARN を assume 対象にしていない"
    )


def test_terraform_exec_can_read_versioned_artifacts_after_assume():
    """apply stage が assume 後に plan artifact / Lambda package を照合できること。"""
    code = read_tf("iam.tf")
    assert 'sid       = "TerraformArtifactBucketList"' in code
    assert 'sid    = "TerraformArtifactObjectRead"' in code
    assert '"s3:GetObject"' in code
    assert '"s3:GetObjectVersion"' in code
    assert '"${aws_s3_bucket.artifacts.arn}/*"' in code
    assert 'sid    = "TerraformArtifactKmsDecrypt"' in code
    assert '"kms:Decrypt"' in code
    assert '"kms:DescribeKey"' in code
    assert "aws_kms_key.artifacts.arn" in code


def test_terraform_exec_can_confirm_platform_s3_bucket_creation():
    """Terraform can verify managed S3 buckets after CreateBucket."""
    code = read_tf("iam.tf")
    match = re.search(
        r'sid\s*=\s*"PlatformS3Manage"(.*?)\n  \}',
        code,
        flags=re.DOTALL,
    )
    assert match, "PlatformS3Manage statement が見つからない"
    block = match.group(1)
    assert '"s3:CreateBucket"' in block
    assert '"s3:ListBucket"' in block
    assert '"s3:GetBucketLocation"' in block
    assert '"s3:GetBucketAcl"' in block
    assert '"s3:GetBucketOwnershipControls"' in block
    assert '"s3:GetLifecycleConfiguration"' in block
    assert '"s3:GetBucketObjectLockConfiguration"' in block
    assert '"s3:GetObjectLockConfiguration"' not in block
    assert '"arn:aws:s3:::${local.name_prefix}-*"' in block


def test_terraform_exec_has_provider_follow_up_permissions():
    """Cover the exact provider read/update calls observed after partial apply."""
    code = read_tf("iam.tf")
    required_actions = (
        "secretsmanager:GetSecretValue",
        "apigateway:TagResource",
        "cognito-idp:GetUserPoolMfaConfig",
        "ecr:GetLifecyclePolicy",
        "ecs:PutClusterCapacityProviders",
        "ec2:CreateFlowLogs",
        "wafv2:PutLoggingConfiguration",
        "logs:PutResourcePolicy",
        "kms:TagResource",
        "kms:CreateGrant",
        "iam:CreateServiceLinkedRole",
        "iam:GetRole",
    )
    for action in required_actions:
        assert f'"{action}"' in code, f"required Terraform execution action is missing: {action}"


def test_service_passrole_permissions_are_exactly_scoped():
    """EKS, Lambda, and Flow Logs receive only their dedicated service role."""
    code = read_tf("iam.tf")
    expected = {
        "IAMPassRoleEKSCluster": ("-eks-cluster-role", "eks.amazonaws.com"),
        "IAMPassRoleEKSFargate": (
            "-eks-fargate-exec-role",
            "eks.amazonaws.com",
        ),
        "IAMPassRoleLambdaPortal": ("-lambda-portal-role", "lambda.amazonaws.com"),
        "IAMPassRoleVpcFlowLogs": (
            "-vpc-flowlogs-role",
            "vpc-flow-logs.amazonaws.com",
        ),
    }
    for sid, (role_suffix, service) in expected.items():
        match = re.search(rf'sid\s*=\s*"{sid}"(.*?)\n  \}}', code, flags=re.DOTALL)
        assert match, f"{sid} statement is missing"
        block = match.group(1)
        assert '"iam:PassRole"' in block
        assert block.count(":role/") == 1
        assert role_suffix in block
        assert 'variable = "iam:PassedToService"' in block
        assert service in block
        assert "role/${local.name_prefix}-*" not in block


def test_waf_kms_management_is_limited_to_us_east_1_account_resources():
    code = read_tf("iam.tf")
    match = re.search(
        r'data\s+"aws_iam_policy_document"\s+"terraform_exec_kms"\s*\{(.*?)\n\}',
        code,
        flags=re.DOTALL,
    )
    assert match, "terraform_exec_kms policy document is missing"
    block = match.group(1)
    assert '"kms:CreateKey"' in block
    assert '"kms:TagResource"' in block
    assert "kms:us-east-1:${local.account_id}:key/*" in block
    assert "kms:us-east-1:${local.account_id}:alias/${local.name_prefix}-waf-logs" in block
    assert "KMSManageAuroraMasterSecretKey" in code
    assert "KMSTagNewAuroraMasterSecretKey" in code
    tag_match = re.search(
        r'sid\s*=\s*"KMSTagNewAuroraMasterSecretKey"(.*?)\n  \}',
        code,
        flags=re.DOTALL,
    )
    assert tag_match, "Aurora KMS creation-time tag statement is missing"
    tag_block = tag_match.group(1)
    assert 'resources = ["*"]' in tag_block
    assert "kms:${var.aws_region}:${local.account_id}:key/*" in code
    assert "aws:RequestTag/Project" in code
    assert "aws:RequestTag/Environment" in code
    assert "aws:TagKeys" in code
    assert "aws:ResourceTag/Project" in code
    assert "aws:ResourceTag/Environment" in code
    assert "kms:${var.aws_region}:${local.account_id}:alias/${local.name_prefix}-aurora-master-secret" in code
    assert "terraform_exec_kms.json" in code


def test_eks_service_linked_role_creation_is_condition_scoped():
    code = read_tf("iam.tf")
    expected = {
        "IAMCreateEksServiceLinkedRole": (
            '"iam:CreateServiceLinkedRole"',
            "role/aws-service-role/eks.amazonaws.com/AWSServiceRoleForAmazonEKS",
            '"eks.amazonaws.com"',
        ),
        "IAMReadEksFargateServiceLinkedRole": (
            '"iam:GetRole"',
            "role/aws-service-role/eks-fargate.amazonaws.com/AWSServiceRoleForAmazonEKSForFargate",
            None,
        ),
        "IAMCreateEksFargateServiceLinkedRole": (
            '"iam:CreateServiceLinkedRole"',
            "role/aws-service-role/eks-fargate.amazonaws.com/AWSServiceRoleForAmazonEKSForFargate",
            '"eks-fargate.amazonaws.com"',
        ),
    }
    for sid, (action, resource, service_name) in expected.items():
        match = re.search(rf'sid\s*=\s*"{sid}"(.*?)\n  \}}', code, flags=re.DOTALL)
        assert match, f"{sid} statement is missing"
        block = match.group(1)
        assert action in block
        assert resource in block
        if service_name is not None:
            assert 'variable = "iam:AWSServiceName"' in block
            assert service_name in block
        if "EksFargateServiceLinkedRole" in sid:
            assert "AWSServiceRoleForAmazonEKSForFargate*" in block
