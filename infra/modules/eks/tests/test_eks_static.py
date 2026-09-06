"""Static Task 10.1 eks-module configuration tests; no Terraform or AWS access."""

from __future__ import annotations

import re
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
MAIN = (MODULE_DIR / "main.tf").read_text(encoding="utf-8")
VARIABLES = (MODULE_DIR / "variables.tf").read_text(encoding="utf-8")
OUTPUTS = (MODULE_DIR / "outputs.tf").read_text(encoding="utf-8")
VERSIONS = (MODULE_DIR / "versions.tf").read_text(encoding="utf-8")
README = (MODULE_DIR / "README.md").read_text(encoding="utf-8")


def _resource_block(resource_type: str, resource_name: str) -> str:
    match = re.search(
        rf'resource "{resource_type}" "{resource_name}" \{{(.*?)(?=\nresource |\ndata |\Z)',
        MAIN,
        re.DOTALL,
    )
    assert match, f"{resource_type}.{resource_name} was not found"
    return match.group(1)


def test_versions_pin_terraform_and_aws_provider() -> None:
    assert 'required_version = ">= 1.10"' in VERSIONS
    assert 'source  = "hashicorp/aws"' in VERSIONS
    assert 'version = "~> 5.0"' in VERSIONS


def test_cluster_enables_control_plane_logging_and_uses_private_subnets() -> None:
    cluster = _resource_block("aws_eks_cluster", "this")
    assert "enabled_cluster_log_types = var.enabled_cluster_log_types" in cluster
    assert "subnet_ids              = var.private_subnet_ids" in cluster
    assert "security_group_ids      = [var.eks_security_group_id]" in cluster
    # Fargate pods run in private subnets: variable requires >= 2 distinct.
    subnets = re.search(r'variable "private_subnet_ids" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert subnets and "length(var.private_subnet_ids) >= 2" in subnets.group(1)


def test_oidc_provider_created_with_sts_audience() -> None:
    oidc = _resource_block("aws_iam_openid_connect_provider", "this")
    assert 'client_id_list  = ["sts.amazonaws.com"]' in oidc
    assert "aws_eks_cluster.this.identity[0].oidc[0].issuer" in oidc
    assert "data.tls_certificate.oidc.certificates[0].sha1_fingerprint" in oidc


def test_three_fargate_profiles_including_aws_observability() -> None:
    for name, ns in (
        ("workers", "var.worker_namespace"),
        ("kube_system", '"kube-system"'),
        ("aws_observability", '"aws-observability"'),
    ):
        block = _resource_block("aws_eks_fargate_profile", name)
        assert f"namespace = {ns}" in block
        assert "subnet_ids             = var.private_subnet_ids" in block
        assert "pod_execution_role_arn = aws_iam_role.fargate_pod_execution.arn" in block


def test_no_fluent_bit_daemonset_reference() -> None:
    # The design forbids a Fluent Bit DaemonSet; the built-in log router is used.
    # The words may appear only in explanatory comments stating it is NOT used.
    assert "daemonset" in README.lower()  # README explains why it is NOT used
    # No Kubernetes DaemonSet object is declared in this Terraform module.
    assert "kind = \"DaemonSet\"" not in MAIN
    assert "kubernetes_daemonset" not in MAIN
    assert "aws-observability" in MAIN
    assert "built-in log router" in MAIN or "log router" in MAIN


def test_fargate_pod_execution_role_has_logging_grant() -> None:
    logging = _resource_block("aws_iam_role_policy", "fargate_logging")
    for action in ("logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"):
        assert action in logging
    assert "AmazonEKSFargatePodExecutionRolePolicy" in MAIN


def test_worker_irsa_trust_is_split_by_service_account() -> None:
    for role_name, subject in (
        ("alarm_worker", "local.alarm_worker_sa_subject"),
        ("finding_worker", "local.finding_worker_sa_subject"),
    ):
        role = _resource_block("aws_iam_role", role_name)
        assert "sts:AssumeRoleWithWebIdentity" in role
        assert "aws_iam_openid_connect_provider.this.arn" in role
        assert subject in role
        assert '"sts.amazonaws.com"' in role
    assert "alarm_worker_sa_subject" in MAIN
    assert "finding_worker_sa_subject" in MAIN
    assert 'cronjob_sa_subject        = "system:serviceaccount:${var.worker_namespace}:${var.cronjob_service_account_name}"' in MAIN


def test_worker_roles_are_scoped_to_their_own_queue() -> None:
    alarm = _resource_block("aws_iam_role_policy", "alarm_worker")
    finding = _resource_block("aws_iam_role_policy", "finding_worker")
    for policy in (alarm, finding):
        assert "sqs:ReceiveMessage" in policy
        assert "sqs:DeleteMessage" in policy
        assert "secretsmanager:GetSecretValue" in policy
        assert "Resource = [var.db_secret_arn]" in policy
    assert "Resource = [var.alarm_queue_arn]" in alarm
    assert "var.finding_queue_arn" not in alarm
    assert "Resource = [var.finding_queue_arn]" in finding
    assert "var.alarm_queue_arn" not in finding
    assert "sqs_queue_arns" not in MAIN + VARIABLES


def test_cronjob_role_writes_only_reports_prefix_and_two_tables() -> None:
    role = _resource_block("aws_iam_role", "cronjob")
    assert "local.cronjob_sa_subject" in role
    policy = _resource_block("aws_iam_role_policy", "cronjob")
    assert "secretsmanager:GetSecretValue" in policy
    assert "Resource = [var.db_secret_arn]" in policy
    assert "s3:PutObject" in policy
    assert 'Resource = ["${var.portal_reports_bucket_arn}/reports/*"]' in policy
    assert "dynamodb:PutItem" in policy
    assert "var.report_metadata_table_arn" in policy
    assert "var.public_status_items_table_arn" in policy
    assert "dynamodb:UpdateItem" not in policy
    assert "s3:GetObject" not in policy


def test_arn_reference_variables_validate_arns() -> None:
    secret = re.search(r'variable "db_secret_arn" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert secret and "arn:aws" in secret.group(1) and "secretsmanager:" in secret.group(1)
    for name in ("alarm_queue_arn", "finding_queue_arn"):
        sqs = re.search(rf'variable "{name}" \{{(.*?)\n\}}', VARIABLES, re.DOTALL)
        assert sqs and "arn:aws" in sqs.group(1) and "sqs:" in sqs.group(1)


def test_version_and_public_access_inputs_follow_approved_contract() -> None:
    version = re.search(r'variable "eks_kubernetes_version" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert version and 'default     = "1.36"' in version.group(1)
    cidrs = re.search(r'variable "eks_public_access_cidrs" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert cidrs and "default" not in cidrs.group(1)
    assert '"0.0.0.0/0"' in cidrs.group(1)
    assert '"::/0"' in cidrs.group(1)
    assert 'variable "eks_operator_principal_arn"' in VARIABLES


def test_no_plaintext_secret_material() -> None:
    corpus = (MAIN + VARIABLES + OUTPUTS + README).lower()
    for forbidden in ("password=", "postgresql://", "bearer ", "authorization:", "secret_value", "master_password"):
        assert forbidden not in corpus


def test_name_prefix_and_common_tags_used() -> None:
    assert "var.name_prefix" in MAIN
    assert "merge(var.common_tags" in MAIN


def test_outputs_expose_expected_ids_without_secret() -> None:
    for output in (
        "cluster_name",
        "cluster_arn",
        "cluster_oidc_issuer_url",
        "oidc_provider_arn",
        "fargate_profile_arn",
        "alarm_worker_role_arn",
        "finding_worker_role_arn",
        "cronjob_role_arn",
        "fargate_pod_execution_role_arn",
    ):
        assert f'output "{output}"' in OUTPUTS


def test_fargate_logging_manifests_use_builtin_router_and_ordered_namespace() -> None:
    manifests = MODULE_DIR.parents[2] / "apps/eks-workers/k8s"
    namespaces = (manifests / "00-namespace.yaml").read_text(encoding="utf-8")
    logging = (manifests / "40-fargate-logging.yaml").read_text(encoding="utf-8")
    assert "name: aws-observability" in namespaces
    assert "aws-observability: enabled" in namespaces
    assert "kind: ConfigMap" in logging
    assert "name: aws-logging" in logging
    assert "Name                cloudwatch_logs" in logging
    assert "kind: DaemonSet" not in logging


def test_worker_manifests_bind_three_distinct_service_accounts() -> None:
    manifests = MODULE_DIR.parents[2] / "apps/eks-workers/k8s"
    service_accounts = (manifests / "10-serviceaccounts.yaml").read_text(encoding="utf-8")
    assert service_accounts.count("kind: ServiceAccount") == 3
    assert "name: eks-alarm-worker" in service_accounts
    assert "name: eks-finding-worker" in service_accounts
    assert "name: eks-cronjob" in service_accounts
    assert "serviceAccountName: eks-alarm-worker" in (
        manifests / "20-alarm-event-processor.yaml"
    ).read_text(encoding="utf-8")
    assert "serviceAccountName: eks-finding-worker" in (
        manifests / "21-security-finding-worker.yaml"
    ).read_text(encoding="utf-8")
