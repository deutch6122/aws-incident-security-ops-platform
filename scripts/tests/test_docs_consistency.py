"""Documentation consistency tests for Task 19.2 / 19.3.

Static, read-only checks (no AWS, Docker, Terraform, or network) that assert
the top-level README, runbook, and architecture doc contain the sections the
task requires. This keeps the docs aligned with the implemented deploy scripts
and the A->B one-way / Product_A-Product_B separation invariants.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
RUNBOOK = REPO_ROOT / "docs" / "runbook" / "runbook.md"
ARCH = REPO_ROOT / "docs" / "architecture" / "architecture-overview.md"
OPERATION = REPO_ROOT / "docs" / "operation" / "operation.md"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing doc: {path}"
    return path.read_text(encoding="utf-8")


def test_readme_has_build_and_teardown_headings() -> None:
    text = _read(README)
    assert "Bootstrap" in text
    assert "Infra_Pipeline" in text
    assert "App_Deploy" in text
    # teardown / removal section present
    assert ("削除" in text) or ("撤去" in text), "README missing teardown section"


def test_readme_mentions_cost_and_security_notes() -> None:
    text = _read(README)
    for keyword in ("NAT", "Aurora", "EKS", "CloudFront"):
        assert keyword in text, f"README missing cost note: {keyword}"
    # security notes
    assert "CIDR" in text, "README missing ALB CIDR note"
    assert ("Secrets Manager" in text) or ("シークレット" in text)


def test_runbook_covers_operational_topics() -> None:
    text = _read(RUNBOOK)
    assert "DLQ" in text, "runbook missing DLQ handling"
    assert ("Portal" in text) or ("閲覧" in text), "runbook missing Portal check"
    assert ("A→B" in text) or ("A->B" in text), "runbook missing A->B linkage"
    assert ("ロールバック" in text) or ("rollback" in text.lower()), "runbook missing rollback"


def test_architecture_states_one_way_and_separation() -> None:
    text = _read(ARCH)
    assert "Product_A" in text and "Product_B" in text, "architecture missing A/B separation"
    assert ("A→B" in text) or ("A->B" in text), "architecture missing A->B linkage"
    # one-way / no B->A
    assert ("一方向" in text) or ("B→A" in text) or ("B->A" in text), (
        "architecture does not state the one-way (no B->A) property"
    )


def test_operation_demo_scenario_present() -> None:
    text = _read(OPERATION)
    assert "seed_alarm_events" in text, "operation missing sample alarm seeding step"
    assert ("デモ" in text) or ("シナリオ" in text), "operation missing demo scenario"
