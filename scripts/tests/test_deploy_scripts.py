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
    for needle in ("aws_secret_access_key", "aws_access_key_id", "-----begin", "password="):
        assert needle not in lowered, f"{name} contains sensitive literal: {needle!r}"


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
