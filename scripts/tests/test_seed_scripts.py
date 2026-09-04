"""Static/unit tests for the Task 18.1 sample-data seed scripts.

No AWS, Docker, moto, or Terraform. boto3 is monkeypatched via a fake to prove
the --execute path can send without any real AWS I/O, and dry-run is verified
never to touch it. Also asserts payloads are non-sensitive and Product_B only.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import seed_alarm_events
import seed_finding_events
import seed_portal_reports
from seed import common

_ACCOUNT_ID_RE = re.compile(r"\b\d{12}\b")
_ARN_RE = re.compile(r"arn:aws:")

ALL_SCRIPTS = (seed_alarm_events, seed_finding_events, seed_portal_reports)


# --- import-time safety: boto3 not imported at import time -------------------
def test_boto3_not_imported_at_import_time() -> None:
    for mod in list(sys.modules):
        if mod == "boto3" or mod.startswith("boto3."):
            del sys.modules[mod]
    importlib.import_module("seed.common")
    importlib.reload(seed_alarm_events)
    importlib.reload(seed_finding_events)
    importlib.reload(seed_portal_reports)
    assert "boto3" not in sys.modules


# --- default is dry-run ------------------------------------------------------
@pytest.mark.parametrize("mod", ALL_SCRIPTS)
def test_default_is_dry_run(mod) -> None:
    parser = common.base_arg_parser("t")
    if mod is seed_portal_reports:
        parser.add_argument("--report-metadata-table", default="t")
        parser.add_argument("--public-status-table", default="t")
        parser.add_argument("--reports-bucket", default="t")
    options = common.parse_options(parser, [])
    assert options.dry_run is True
    assert options.execute is False


@pytest.mark.parametrize("mod", ALL_SCRIPTS)
def test_execute_flag_enables_execute(mod) -> None:
    parser = common.base_arg_parser("t")
    if mod is seed_portal_reports:
        parser.add_argument("--report-metadata-table", default="t")
        parser.add_argument("--public-status-table", default="t")
        parser.add_argument("--reports-bucket", default="t")
    for flag in ("--execute", "--no-dry-run"):
        options = common.parse_options(parser, [flag])
        assert options.execute is True
        assert options.dry_run is False


# --- dry-run never touches boto3 / never sends -------------------------------
def _fail_if_called(*args, **kwargs):
    raise AssertionError("get_boto3_client must not be called in dry-run")


@pytest.mark.parametrize(
    "mod",
    [seed_alarm_events, seed_finding_events],
)
def test_event_scripts_dry_run_does_not_call_boto3(mod, monkeypatch, capsys) -> None:
    monkeypatch.setattr(mod, "get_boto3_client", _fail_if_called)
    assert mod.main([]) == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "--execute" in out  # hints how to actually send


def test_portal_dry_run_does_not_call_boto3(monkeypatch, capsys) -> None:
    monkeypatch.setattr(seed_portal_reports, "get_boto3_client", _fail_if_called)
    assert seed_portal_reports.main([]) == 0
    out = capsys.readouterr().out
    assert "dry-run" in out


# --- --execute path uses only fake boto3 (no real AWS) -----------------------
class _FakeEventsClient:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def put_events(self, Entries):  # noqa: N803 - boto3 kwarg name
        self.entries.extend(Entries)
        return {"FailedEntryCount": 0}


@pytest.mark.parametrize("mod", [seed_alarm_events, seed_finding_events])
def test_event_scripts_execute_uses_fake_client(mod, monkeypatch) -> None:
    fake = _FakeEventsClient()
    monkeypatch.setattr(mod, "get_boto3_client", lambda service, region: fake)
    assert mod.main(["--execute", "--count", "4"]) == 0
    assert len(fake.entries) == 4
    for entry in fake.entries:
        assert entry["Source"] == "ops-platform.sample"


class _FakeDynamoClient:
    def __init__(self) -> None:
        self.puts: list[tuple[str, dict]] = []

    def put_item(self, TableName, Item):  # noqa: N803
        self.puts.append((TableName, Item))


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: list[tuple[str, str]] = []

    def put_object(self, Bucket, Key, Body, ContentType):  # noqa: N803
        self.objects.append((Bucket, Key))


def test_portal_execute_writes_only_product_b(monkeypatch) -> None:
    dynamo = _FakeDynamoClient()
    s3 = _FakeS3Client()

    def fake_client(service, region):
        return {"dynamodb": dynamo, "s3": s3}[service]

    monkeypatch.setattr(seed_portal_reports, "get_boto3_client", fake_client)
    assert seed_portal_reports.main(
        [
            "--execute",
            "--count",
            "3",
            "--report-metadata-table",
            "ops-platform-dev-report-metadata",
            "--public-status-table",
            "ops-platform-dev-public-status-items",
            "--reports-bucket",
            "ops-platform-dev-portal-REPLACE_WITH_SUFFIX",
        ]
    ) == 0
    # 3 report items + 3 status items = 6 dynamo puts; 3 S3 report files.
    assert len(dynamo.puts) == 6
    assert len(s3.objects) == 3
    tables = {t for t, _ in dynamo.puts}
    assert tables == {
        "ops-platform-dev-report-metadata",
        "ops-platform-dev-public-status-items",
    }
    # Product_B only: no Aurora/incidents/backend table referenced.
    for table, _ in dynamo.puts:
        assert "aurora" not in table.lower()
        assert "incident" not in table.lower()


# --- non-sensitive payloads --------------------------------------------------
def _assert_all_non_sensitive(payloads) -> None:
    import json

    for payload in payloads:
        text = json.dumps(payload, ensure_ascii=False, default=str)
        assert not _ARN_RE.search(text), f"ARN leaked: {text}"
        assert not _ACCOUNT_ID_RE.search(text), f"account id leaked: {text}"
        low = text.lower()
        for needle in ("password=", "secret", "bearer ", "authorization:"):
            assert needle not in low, f"sensitive term {needle!r} in {text}"


def test_alarm_payloads_non_sensitive() -> None:
    _assert_all_non_sensitive(seed_alarm_events.build_alarm_events(10))


def test_finding_payloads_non_sensitive() -> None:
    _assert_all_non_sensitive(seed_finding_events.build_finding_events(10))


def test_portal_payloads_non_sensitive() -> None:
    _assert_all_non_sensitive(seed_portal_reports.build_report_items(12))
    _assert_all_non_sensitive(seed_portal_reports.build_public_status_items(12))
    _assert_all_non_sensitive(
        [seed_portal_reports.build_report_file("202401")]
    )


def test_assert_non_sensitive_rejects_real_looking_values() -> None:
    with pytest.raises(ValueError):
        common.assert_non_sensitive({"acct": "123456789012"})
    with pytest.raises(ValueError):
        common.assert_non_sensitive({"arn": "arn:aws:s3:::real-bucket"})
    with pytest.raises(ValueError):
        common.assert_non_sensitive({"h": "Bearer abc.def.ghi"})


# --- source files themselves contain no sensitive literals -------------------
def test_script_sources_have_no_sensitive_literals() -> None:
    for path in SCRIPTS_DIR.glob("seed_*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "aws_secret_access_key" not in text
        assert "postgresql://" not in text
        assert not _ACCOUNT_ID_RE.search(text)
        assert not _ARN_RE.search(text)
