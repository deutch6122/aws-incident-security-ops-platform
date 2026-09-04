# dev root / Infra_Pipeline contract

This document is the Task 4 contract between the dev Terraform root and the bootstrap-owned `Infra_Pipeline`. It does not define a second pipeline.

## Ownership boundary

| Owner | Responsibility |
| --- | --- |
| `bootstrap/` | The only `aws_codepipeline` and `aws_codebuild_project`; CodeBuild/CodePipeline service roles; artifact S3; `terraform-exec-role`; CodeStar source connection settings and the `codebuild-role → terraform-exec-role` AssumeRole boundary. |
| `infra/environments/dev/` | The deployable Terraform root, its backend example/key, dev inputs/tags, and implemented module wiring. It must not declare pipeline or build resources. |

The IAM boundary is intentional: CodeBuild runs under `codebuild-role`, assumes `terraform-exec-role`, and `iam:PassRole` is constrained by `iam:PassedToService`. Do not duplicate or weaken that arrangement in the dev root.

## Canonical values

The root variables and `terraform.tfvars.example` make the following repository contract visible:

| Contract | Canonical value | Bootstrap reference |
| --- | --- | --- |
| Terraform working directory | `infra/environments/dev` | `TF_WORKDIR` in `bootstrap/buildspec/buildspec*.yml` |
| S3 state key | `environments/dev/terraform.tfstate` | `backend.tf` copied from `backend.tf.example` after Bootstrap emits the state bucket name |
| Region | `ap-northeast-1` | Bootstrap and dev provider inputs |
| Source branch | `main` | `bootstrap` `source_branch` default |

The backend block cannot interpolate Terraform input variables. Copy `backend.tf.example` to ignored `backend.tf`, replace only the Bootstrap-created bucket placeholder, and preserve the canonical key and `use_lockfile = true`.

## Execution and approval contract

`bootstrap/cicd.tf` owns the only stage sequence:

```text
Source → Fmt → Validate → Plan → Approval → Apply
```

The buildspecs operate on `infra/environments/dev`. `Plan` produces `plan_output`; `Apply` receives both `source_output` and `plan_output`, sets `PrimarySource = "source_output"`, and applies the approved plan binary only after the Manual Approval stage. The Plan buildspec must present resource create/change/delete information and explicitly call out Aurora, NAT Gateway, EKS, and CloudFront as high-cost review items.

No local ongoing apply is part of this contract. Terraform and AWS commands were not executed while adding this contract.
