"""Task 18 deterministic Lambda package tests; no network or AWS access."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import subprocess
import zipfile


APP_DIR = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = APP_DIR / "build.sh"


def _build(output: Path, vendor: Path) -> bytes:
    env = os.environ.copy()
    env["PORTAL_LAMBDA_OUTPUT"] = str(output)
    env["PORTAL_LAMBDA_VENDOR_DIR"] = str(vendor)
    subprocess.run(["bash", str(BUILD_SCRIPT)], cwd=APP_DIR, env=env, check=True)
    return output.read_bytes()


def test_two_builds_have_identical_hash_and_canonical_metadata(tmp_path: Path) -> None:
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "pinned_dependency.py").write_text("VERSION = '1.0.0'\n", encoding="utf-8")

    first = _build(tmp_path / "first.zip", vendor)
    second = _build(tmp_path / "second.zip", vendor)

    assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()

    with zipfile.ZipFile(tmp_path / "first.zip") as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert "app/handler.py" in names
        assert "pinned_dependency.py" in names
        for item in archive.infolist():
            assert item.date_time == (1980, 1, 1, 0, 0, 0)
            assert stat.S_IMODE(item.external_attr >> 16) in {0o644, 0o755}


def test_runtime_dependencies_are_fully_pinned() -> None:
    requirements = (APP_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines()
    active = [line.strip() for line in requirements if line.strip() and not line.startswith("#")]
    assert active
    assert all("==" in line and not line.startswith(("-", "http")) for line in active)
