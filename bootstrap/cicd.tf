# ---------------------------------------------------------------------------
# CI/CD 土台: artifact S3 / CodeBuild / CodePipeline（Infra_Pipeline）
# ---------------------------------------------------------------------------
# 対応要件: Req 21.1, 21.2, 21.3, 21.4, 21.5, 23.1, 23.2, 23.3
#
# パイプライン構成（Req 21.3）:
#   Source(main) -> fmt -> validate -> plan -> 手動承認 -> apply
#   手動承認が付与されなければ apply ステージへ進まない（Req 21.4, 23.3）。
#   本体インフラの作成/更新はローカル継続 apply ではなくパイプラインで行う（Req 21.5）。
# ---------------------------------------------------------------------------

# ===========================================================================
# artifact 用 S3 バケット
# ===========================================================================
resource "aws_s3_bucket" "artifacts" {
  bucket = local.artifact_bucket_name

  tags = {
    Name = "${local.name_prefix}-cicd-artifacts"
    Role = "cicd-artifacts"
  }
}

# バージョニング有効
resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

# サーバーサイド暗号化（AES256）
resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# public access block 全項目 true
resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ===========================================================================
# CodeBuild プロジェクト（Terraform 実行用）
# ===========================================================================
# コンピュートは小さめ（BUILD_GENERAL1_SMALL）。標準 Ubuntu イメージを使用し、
# buildspec 内で Terraform を実行する（Terraform は事前導入 or install phase で用意）。
resource "aws_codebuild_project" "terraform" {
  name         = "${local.name_prefix}-terraform-build"
  description  = "Terraform fmt/validate/plan/apply を実行する CodeBuild プロジェクト（Infra_Pipeline）"
  service_role = aws_iam_role.codebuild.arn

  artifacts {
    type = "CODEPIPELINE"
  }

  environment {
    type            = "LINUX_CONTAINER"
    compute_type    = "BUILD_GENERAL1_SMALL" # 小さめ（コスト最適化）
    image           = "aws/codebuild/amazonlinux2-x86_64-standard:5.0"
    privileged_mode = false

    # terraform-exec-role を assume するための ARN を環境変数で渡す。
    environment_variable {
      name  = "TERRAFORM_EXEC_ROLE_ARN"
      value = aws_iam_role.terraform_exec.arn
    }
    environment_variable {
      name  = "AWS_REGION"
      value = var.aws_region
    }
  }

  # 各ステージの buildspec は CodePipeline の各アクションで上書き指定する
  # （BuildspecOverride）。ここではデフォルトを plan にしておく。
  source {
    type = "CODEPIPELINE"
    # STAGE 環境変数（fmt/validate/plan/apply）で処理を分岐するディスパッチャ buildspec。
    # 各ステージ専用の buildspec-*.yml も同ディレクトリに用意している（可読性/個別実行用）。
    buildspec = "bootstrap/buildspec/buildspec.yml"
  }

  logs_config {
    cloudwatch_logs {
      group_name = "/aws/codebuild/${local.name_prefix}-terraform-build"
    }
  }

  tags = {
    Name = "${local.name_prefix}-terraform-build"
  }
}

# ===========================================================================
# CodePipeline（Infra_Pipeline）
# ===========================================================================
# ステージ: Source -> Fmt -> Validate -> Plan -> Approval(手動承認) -> Apply
resource "aws_codepipeline" "infra" {
  name     = "${local.name_prefix}-infra-pipeline"
  role_arn = aws_iam_role.codepipeline.arn

  artifact_store {
    type     = "S3"
    location = aws_s3_bucket.artifacts.bucket
  }

  # --- Source: main ブランチ（Req 21.2）------------------------------------
  stage {
    name = "Source"

    action {
      name             = "Source"
      category         = "Source"
      owner            = "AWS"
      provider         = "CodeStarSourceConnection"
      version          = "1"
      output_artifacts = ["source_output"]

      configuration = {
        ConnectionArn    = var.codestar_connection_arn
        FullRepositoryId = var.source_repository_id
        BranchName       = var.source_branch
        # push 検知でパイプライン起動（Req 21.2）。
        DetectChanges = "true"
      }
    }
  }

  # --- fmt（Req 21.3）------------------------------------------------------
  stage {
    name = "Fmt"

    action {
      name             = "TerraformFmt"
      category         = "Build"
      owner            = "AWS"
      provider         = "CodeBuild"
      version          = "1"
      input_artifacts  = ["source_output"]
      output_artifacts = ["fmt_output"]

      configuration = {
        ProjectName = aws_codebuild_project.terraform.name
        # 各アクションで buildspec を上書き。
        EnvironmentVariables = jsonencode([
          { name = "STAGE", value = "fmt", type = "PLAINTEXT" },
        ])
        # buildspec の上書き（fmt 段階）。
        # 注: BuildspecOverride は CodePipeline の CodeBuild アクションでは
        #     'Buildspec' 環境変数ではなくアクション設定として渡せないため、
        #     プロジェクト側 or 環境変数 STAGE で分岐する運用も可。
        #     ここでは可読性のため buildspec を明示するコメントを残す。
      }
    }
  }

  # --- validate（Req 21.3）-------------------------------------------------
  stage {
    name = "Validate"

    action {
      name             = "TerraformValidate"
      category         = "Build"
      owner            = "AWS"
      provider         = "CodeBuild"
      version          = "1"
      input_artifacts  = ["source_output"]
      output_artifacts = ["validate_output"]

      configuration = {
        ProjectName = aws_codebuild_project.terraform.name
        EnvironmentVariables = jsonencode([
          { name = "STAGE", value = "validate", type = "PLAINTEXT" },
        ])
      }
    }
  }

  # --- plan（作成/変更/削除一覧 + コスト影響大リソース明示）（Req 23.1, 23.2）--
  stage {
    name = "Plan"

    action {
      name             = "TerraformPlan"
      category         = "Build"
      owner            = "AWS"
      provider         = "CodeBuild"
      version          = "1"
      input_artifacts  = ["source_output"]
      output_artifacts = ["plan_output"]

      configuration = {
        ProjectName = aws_codebuild_project.terraform.name
        EnvironmentVariables = jsonencode([
          { name = "STAGE", value = "plan", type = "PLAINTEXT" },
        ])
      }
    }
  }

  # --- 手動承認（承認なしでは apply しない）（Req 21.4, 23.3）----------------
  stage {
    name = "Approval"

    action {
      name     = "ManualApproval"
      category = "Approval"
      owner    = "AWS"
      provider = "Manual"
      version  = "1"

      configuration = {
        CustomData = "plan-output（作成/変更/削除リソースとコスト影響大リソース）を確認のうえ承認してください。承認するまで apply は実行されません。"
      }
    }
  }

  # --- apply（承認後のみ到達）（Req 21.3）-----------------------------------
  # Apply は承認済み plan（plan_output の tfplan.binary）を、Terraform コード一式
  # （source_output）に対して適用する必要がある。plan_output には plan バイナリと
  # サマリしか含まれないため、コード一式を持つ source_output も入力に加え、
  # PrimarySource を source_output に設定する（複数 input の場合は PrimarySource 必須）。
  # buildspec 側では plan_output のセカンダリソースディレクトリ（環境変数
  # CODEBUILD_SRC_DIR_plan_output）経由で tfplan.binary を参照する。
  stage {
    name = "Apply"

    action {
      name            = "TerraformApply"
      category        = "Build"
      owner           = "AWS"
      provider        = "CodeBuild"
      version         = "1"
      # source_output（コード一式）と plan_output（tfplan.binary）の両方を渡す。
      input_artifacts = ["source_output", "plan_output"]

      configuration = {
        ProjectName = aws_codebuild_project.terraform.name
        # 複数 input のうちプライマリソース（作業ディレクトリ）を source_output に固定。
        PrimarySource = "source_output"
        EnvironmentVariables = jsonencode([
          { name = "STAGE", value = "apply", type = "PLAINTEXT" },
          # plan_output（セカンダリソース）のアーティファクト名を buildspec に渡す。
          { name = "PLAN_ARTIFACT_NAME", value = "plan_output", type = "PLAINTEXT" },
        ])
      }
    }
  }
}
