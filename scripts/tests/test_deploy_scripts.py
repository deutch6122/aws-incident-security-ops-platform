"""Static tests for the Task 19.1 App_Deploy shell scripts.

These tests DO NOT execute the deploy scripts. They only read the sources and
run ``bash -n`` (syntax check). No AWS, Docker, kubectl, Terraform, or network
access is involved. The goal is to assert the safety design statically:

* the three deploy scripts exist,
* each uses ``set -euo pipefail``,
* each provides ``--help``,
* dry-run is the default and real commands (docker/aws/kubectl) go through a
  ``run`` helper that only echoes unless ``--execute`` is given,
* ``--execute`` is required to actually run,
* no real secret / ARN / 12-digit account id is embedded,
* terraform apply/destroy is never invoked.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]

DEPLOY_SCRIPTS = (
    "deploy-ecs.sh",
    "deploy-eks.sh",
    "deploy-frontend.sh",
    "deploy-migration.sh",
)

_ACCOUNT_ID_RE = re.compile(r"\b\d{12}\b")
_ARN_RE = re.compile(r"arn:aws:", re.IGNORECASE)
_BEARER_RE = re.compile(r"bearer\s+\S+", re.IGNORECASE)
# A real (non-comment) terraform apply/destroy invocation line.
_TERRAFORM_EXEC_RE = re.compile(r"^\s*[^#\n]*\bterraform\b[^\n]*\b(apply|destroy)\b", re.MULTILINE)


def _read(name: str) -> str:
    return (SCRIPTS_DIR / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", DEPLOY_SCRIPTS)
def test_deploy_script_exists(name: str) -> None:
    assert (SCRIPTS_DIR / name).is_file(), f"missing deploy script: {name}"


@pytest.mark.parametrize("name", DEPLOY_SCRIPTS)
def test_has_shebang_and_strict_mode(name: str) -> None:
    text = _read(name)
    assert text.startswith("#!/usr/bin/env bash"), f"{name} missing bash shebang"
    assert "set -euo pipefail" in text, f"{name} missing 'set -euo pipefail'"


@pytest.mark.parametrize("name", DEPLOY_SCRIPTS)
def test_has_help(name: str) -> None:
    text = _read(name)
    # accepts both -h and --help in the case statement, and a usage function
    assert "usage()" in text, f"{name} missing usage() function"
    assert "-h|--help" in text or "--help" in text, f"{name} missing --help handling"


@pytest.mark.parametrize("name", DEPLOY_SCRIPTS)
def test_dry_run_is_default(name: str) -> None:
    text = _read(name)
    # EXECUTE starts at 0 (dry-run). --execute flips it to 1.
    assert "EXECUTE=0" in text, f"{name} does not default EXECUTE to 0 (dry-run)"
    assert "--execute" in text, f"{name} has no --execute opt-in"


@pytest.mark.parametrize("name", DEPLOY_SCRIPTS)
def test_run_helper_guards_real_commands(name: str) -> None:
    text = _read(name)
    # A run() helper must exist and branch on EXECUTE, echoing in dry-run.
    assert "run()" in text, f"{name} missing run() helper"
    assert 'if [[ "$EXECUTE" -eq 1 ]]' in text, f"{name} run() does not branch on EXECUTE"
    # Real tool invocations must be routed through the run helper, never called
    # bare on their own line in the deploy steps.
    for tool in ("docker", "aws", "kubectl"):
        bare = re.compile(rf"^\s*{tool}\s", re.MULTILINE)
        for match in bare.finditer(text):
            line = text[match.start(): text.find("\n", match.start())]
            raise AssertionError(
                f"{name} calls '{tool}' directly outside run(): {line.strip()!r}"
            )


@pytest.mark.parametrize("name", DEPLOY_SCRIPTS)
def test_execute_required_for_real_commands(name: str) -> None:
    text = _read(name)
    # In the run helper, the actual execution ("$@") must be inside the
    # EXECUTE==1 branch; the else branch only echoes [dry-run].
    assert '"$@"' in text, f"{name} run() never executes the command under --execute"
    assert "[dry-run]" in text, f"{name} run() has no dry-run echo branch"


@pytest.mark.parametrize("name", DEPLOY_SCRIPTS)
def test_no_sensitive_literals(name: str) -> None:
    text = _read(name)
    assert not _ARN_RE.search(text), f"{name} contains an ARN literal"
    assert not _ACCOUNT_ID_RE.search(text), f"{name} contains a 12-digit account id"
    assert not _BEARER_RE.search(text), f"{name} contains a bearer token"
    lowered = text.lower()
    for needle in ("-----begin", "password="):
        assert needle not in lowered, f"{name} contains sensitive literal: {needle!r}"
    # Credential environment-variable names are allowed for STS AssumeRole,
    # but a literal credential assignment is not.
    for credential_name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        assert not re.search(
            rf"{credential_name}\s*=\s*['\"][A-Za-z0-9+/]{{8,}}",
            text,
        ), f"{name} contains a literal value for {credential_name}"


@pytest.mark.parametrize("name", DEPLOY_SCRIPTS)
def test_no_terraform_apply_or_destroy(name: str) -> None:
    text = _read(name)
    match = _TERRAFORM_EXEC_RE.search(text)
    assert match is None, (
        f"{name} appears to invoke terraform apply/destroy: {match.group(0).strip()!r}"
    )


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
@pytest.mark.parametrize("name", DEPLOY_SCRIPTS)
def test_bash_syntax_check(name: str) -> None:
    """Run `bash -n` (syntax check only; does not execute the script)."""
    result = subprocess.run(
        ["bash", "-n", str(SCRIPTS_DIR / name)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"bash -n failed for {name}: {result.stderr}"


def test_migration_script_has_private_fargate_wait_and_exit_checks() -> None:
    text = _read("deploy-migration.sh")
    for required_env in (
        "MIGRATION_LAUNCHER_ROLE_ARN",
        "ECS_CLUSTER",
        "ECS_TASK_DEFINITION",
        "PRIVATE_SUBNET_IDS",
        "MIGRATION_SECURITY_GROUP_ID",
    ):
        assert required_env in text
    assert "aws sts assume-role" in text
    assert "aws ecs run-task" in text
    assert "--launch-type FARGATE" in text
    assert "assignPublicIp=DISABLED" in text
    assert "aws ecs wait tasks-stopped" in text
    assert "aws ecs describe-tasks" in text
    assert 'if [[ "$EXIT_CODE" != "0" ]]' in text


def test_migration_default_dry_run_executes_no_aws(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    aws_marker = tmp_path / "aws-was-called"
    fake_aws = fake_bin / "aws"
    fake_aws.write_text(
        f"#!/usr/bin/env bash\ntouch '{aws_marker}'\nexit 99\n",
        encoding="utf-8",
    )
    fake_aws.chmod(0o755)

    env = {
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "AWS_REGION": "ap-northeast-1",
        "MIGRATION_LAUNCHER_ROLE_ARN": "<migration-launcher-role-arn>",
        "ECS_CLUSTER": "<migration-cluster-arn>",
        "ECS_TASK_DEFINITION": "<migration-task-definition-arn>",
        "PRIVATE_SUBNET_IDS": "subnet-EXAMPLE1,subnet-EXAMPLE2",
        "MIGRATION_SECURITY_GROUP_ID": "sg-EXAMPLE",
    }
    result = subprocess.run(
        ["bash", str(SCRIPTS_DIR / "deploy-migration.sh")],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not aws_marker.exists()
    assert "[dry-run] aws sts assume-role" in result.stdout
    assert "assignPublicIp=DISABLED" in result.stdout


def _write_fake_envsubst(fake_bin: Path) -> None:
    executable = fake_bin / "envsubst"
    executable.write_text(
        """#!/usr/bin/env python3
import os
import re
import sys

allowed = set(re.findall(r"\\$\\{([A-Za-z_][A-Za-z0-9_]*)\\}", " ".join(sys.argv[1:])))
source = sys.stdin.read()
for name in allowed:
    source = source.replace("${" + name + "}", os.environ.get(name, ""))
sys.stdout.write(source)
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)


def _eks_dry_run_env(fake_bin: Path) -> dict[str, str]:
    return {
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "AWS_REGION": "ap-northeast-1",
        "AWS_ACCOUNT_ID": "111122223333",
        "EKS_CLUSTER": "ops-platform-dev-eks",
        "ALARM_ECR_REPO": "ops-platform-dev-alarm-event-processor",
        "FINDING_ECR_REPO": "ops-platform-dev-security-finding-worker",
        "SUMMARY_ECR_REPO": "ops-platform-dev-monthly-summary-cronjob",
        "EKS_ALARM_WORKER_ROLE_ARN": "alarm-role-reference",
        "EKS_FINDING_WORKER_ROLE_ARN": "finding-role-reference",
        "EKS_CRONJOB_ROLE_ARN": "cronjob-role-reference",
        "WORKER_DB_SECRET_ARN": "database-secret-reference",
        "ALARM_QUEUE_URL": "https://example.invalid/alarm",
        "FINDING_QUEUE_URL": "https://example.invalid/finding",
        "WORKER_LOG_GROUP_NAME": "/ops-platform-dev/eks/workers",
        "PORTAL_REPORTS_BUCKET": "ops-platform-dev-portal-example",
        "PORTAL_REPORT_METADATA_TABLE": "ops-platform-dev-report-metadata",
        "PORTAL_PUBLIC_STATUS_ITEMS_TABLE": "ops-platform-dev-public-status-items",
    }


def test_eks_script_uses_three_distinct_images_and_linux_amd64() -> None:
    text = _read("deploy-eks.sh")
    for name in ("ALARM_ECR_REPO", "FINDING_ECR_REPO", "SUMMARY_ECR_REPO"):
        assert name in text
    for image in ("ALARM_WORKER_IMAGE", "FINDING_WORKER_IMAGE", "SUMMARY_CRONJOB_IMAGE"):
        assert image in text
    assert "docker build --platform linux/amd64" in text
    assert "envsubst" in text
    assert "unresolved placeholder found" in text
    assert text.index('"00-namespace.yaml"') < text.index('"40-fargate-logging.yaml"')
    assert text.index('"40-fargate-logging.yaml"') < text.index('"10-serviceaccounts.yaml"')


def test_eks_manifests_reference_distinct_workload_images_and_queues() -> None:
    manifests = SCRIPTS_DIR.parent / "apps/eks-workers/k8s"
    alarm = (manifests / "20-alarm-event-processor.yaml").read_text(encoding="utf-8")
    finding = (manifests / "21-security-finding-worker.yaml").read_text(encoding="utf-8")
    summary = (manifests / "30-monthly-summary-cronjob.yaml").read_text(encoding="utf-8")
    assert "${ALARM_WORKER_IMAGE}" in alarm
    assert "${FINDING_WORKER_IMAGE}" in finding
    assert "${SUMMARY_CRONJOB_IMAGE}" in summary
    assert "${ALARM_QUEUE_URL}" in alarm and "${FINDING_QUEUE_URL}" not in alarm
    assert "${FINDING_QUEUE_URL}" in finding and "${ALARM_QUEUE_URL}" not in finding


def test_eks_default_dry_run_renders_but_executes_no_external_tool(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_fake_envsubst(fake_bin)
    markers = []
    for tool in ("docker", "aws", "kubectl"):
        marker = tmp_path / f"{tool}-was-called"
        markers.append(marker)
        executable = fake_bin / tool
        executable.write_text(
            f"#!/usr/bin/env bash\ntouch '{marker}'\nexit 99\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)

    result = subprocess.run(
        ["bash", str(SCRIPTS_DIR / "deploy-eks.sh"), "--tag", "v1"],
        capture_output=True,
        text=True,
        env=_eks_dry_run_env(fake_bin),
        cwd=SCRIPTS_DIR.parent,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not any(marker.exists() for marker in markers)
    assert "manifests rendered and validated" in result.stdout
    assert "--platform linux/amd64" in result.stdout
    assert "40-fargate-logging.yaml" in result.stdout


def test_eks_unresolved_placeholder_fails_before_external_commands(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_fake_envsubst(fake_bin)
    marker = tmp_path / "external-tool-was-called"
    for tool in ("docker", "aws", "kubectl"):
        executable = fake_bin / tool
        executable.write_text(
            f"#!/usr/bin/env bash\ntouch '{marker}'\nexit 99\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)

    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "placeholder.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\ndata:\n  value: ${UNAPPROVED_VALUE}\n",
        encoding="utf-8",
    )
    env = _eks_dry_run_env(fake_bin)
    env["K8S_DIR"] = str(manifests)
    result = subprocess.run(
        ["bash", str(SCRIPTS_DIR / "deploy-eks.sh")],
        capture_output=True,
        text=True,
        env=env,
        cwd=SCRIPTS_DIR.parent,
        check=False,
    )
    assert result.returncode != 0
    assert "unresolved placeholder found" in result.stderr
    assert not marker.exists()


def _frontend_dry_run_env(fake_bin: Path) -> dict[str, str]:
    return {
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "AWS_REGION": "ap-northeast-1",
        "S3_BUCKET": "ops-platform-dev-portal-example",
        "CLOUDFRONT_DISTRIBUTION_ID": "EXAMPLEDISTRIBUTION",
        "COGNITO_USER_POOL_ID": "ap-northeast-1_example",
        "COGNITO_APP_CLIENT_ID": "exampleclientid",
        "COGNITO_DOMAIN": "example.auth.ap-northeast-1.amazoncognito.com",
        "COGNITO_REDIRECT_URI": "https://portal.example/callback",
        "COGNITO_LOGOUT_URI": "https://portal.example/",
    }


def test_frontend_script_generates_config_and_scans_before_sync() -> None:
    text = _read("deploy-frontend.sh")
    for name in (
        "COGNITO_USER_POOL_ID",
        "COGNITO_APP_CLIENT_ID",
        "COGNITO_DOMAIN",
        "COGNITO_REDIRECT_URI",
        "COGNITO_LOGOUT_URI",
    ):
        assert name in text
    assert 'cat > "$GENERATED_DIR/config.js"' in text
    assert "unresolved placeholder found" in text
    assert text.index("unresolved placeholder found") < text.index("run aws s3 sync")
    assert 'run aws s3 sync "${GENERATED_DIR}/"' in text


def test_frontend_default_dry_run_generates_config_without_aws(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "aws-was-called"
    fake_aws = fake_bin / "aws"
    fake_aws.write_text(
        f"#!/usr/bin/env bash\ntouch '{marker}'\nexit 99\n",
        encoding="utf-8",
    )
    fake_aws.chmod(0o755)
    result = subprocess.run(
        ["bash", str(SCRIPTS_DIR / "deploy-frontend.sh")],
        capture_output=True,
        text=True,
        env=_frontend_dry_run_env(fake_bin),
        cwd=SCRIPTS_DIR.parent,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    assert "generated config.js" in result.stdout
    assert "[dry-run] aws s3 sync" in result.stdout


def test_frontend_placeholder_failure_prevents_aws(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "aws-was-called"
    fake_aws = fake_bin / "aws"
    fake_aws.write_text(
        f"#!/usr/bin/env bash\ntouch '{marker}'\nexit 99\n",
        encoding="utf-8",
    )
    fake_aws.chmod(0o755)
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text(
        "<html><script src='config.js'></script><p>REPLACE_WITH_UNRESOLVED</p></html>",
        encoding="utf-8",
    )
    (frontend / "config.js").write_text("placeholder", encoding="utf-8")
    env = _frontend_dry_run_env(fake_bin)
    env["FRONTEND_DIR"] = str(frontend)
    result = subprocess.run(
        ["bash", str(SCRIPTS_DIR / "deploy-frontend.sh")],
        capture_output=True,
        text=True,
        env=env,
        cwd=SCRIPTS_DIR.parent,
        check=False,
    )
    assert result.returncode != 0
    assert "unresolved placeholder found" in result.stderr
    assert not marker.exists()
