"""Shared helpers for the sample-data seed scripts.

This module is intentionally free of any import-time AWS dependency. boto3 is
imported lazily inside :func:`get_boto3_client` so that:

* importing any seed script (for ``--help`` or for tests) needs no AWS
  credentials and performs no network I/O, and
* the default dry-run path never touches boto3 at all.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

# --------------------------------------------------------------------------- #
# Safety: patterns that must never appear in generated sample payloads.        #
# These guard against a real ARN / account id / secret / token / real domain   #
# leaking into the dummy data. Tests assert generated payloads do not match.   #
# --------------------------------------------------------------------------- #
_ACCOUNT_ID_RE = re.compile(r"\b\d{12}\b")
_ARN_RE = re.compile(r"arn:aws:", re.IGNORECASE)
_BEARER_RE = re.compile(r"bearer\s+\S+", re.IGNORECASE)
_SENSITIVE_SUBSTRINGS = (
    "aws_secret_access_key",
    "aws_access_key_id",
    "password=",
    "postgresql://",
    "authorization:",
    "-----begin",  # PEM private key marker
)


def assert_non_sensitive(payload: Any) -> None:
    """Raise ``ValueError`` if *payload* appears to contain sensitive data.

    Placeholders such as ``000000000000`` or ``EXAMPLE`` are treated as dummy
    values: the 12-digit check rejects any all-numeric 12-char run, so seed
    payloads must use the explicit placeholder helpers below rather than a
    real account id.
    """

    text = json.dumps(payload, ensure_ascii=False, default=str)
    lowered = text.lower()
    for needle in _SENSITIVE_SUBSTRINGS:
        if needle in lowered:
            raise ValueError(f"sample payload contains sensitive substring: {needle!r}")
    if _ARN_RE.search(text):
        raise ValueError("sample payload contains an ARN-like value")
    if _BEARER_RE.search(text):
        raise ValueError("sample payload contains a bearer token")
    if _ACCOUNT_ID_RE.search(text):
        raise ValueError("sample payload contains a 12-digit account-id-like value")


# --------------------------------------------------------------------------- #
# CLI plumbing shared by every seed script.                                    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RunOptions:
    """Parsed CLI options common to all seed scripts."""

    execute: bool
    count: int
    region: str

    @property
    def dry_run(self) -> bool:
        return not self.execute


def base_arg_parser(description: str) -> argparse.ArgumentParser:
    """Build an ArgumentParser preconfigured with the shared safety flags.

    dry-run is the default. Real delivery to AWS requires ``--execute`` (alias
    ``--no-dry-run``).
    """

    parser = argparse.ArgumentParser(description=description)
    exec_group = parser.add_mutually_exclusive_group()
    exec_group.add_argument(
        "--execute",
        "--no-dry-run",
        dest="execute",
        action="store_true",
        help="Actually send the sample data to AWS. Omitted => dry-run (print only).",
    )
    exec_group.add_argument(
        "--dry-run",
        dest="execute",
        action="store_false",
        help="Print the payloads without sending them (this is the default).",
    )
    parser.set_defaults(execute=False)
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Number of dummy records to generate (default: 3).",
    )
    parser.add_argument(
        "--region",
        default="ap-northeast-1",
        help="AWS region used only when --execute is set (default: ap-northeast-1).",
    )
    return parser


def parse_options(parser: argparse.ArgumentParser, argv: list[str] | None = None) -> RunOptions:
    ns = parser.parse_args(argv)
    if ns.count < 1:
        parser.error("--count must be >= 1")
    return RunOptions(execute=ns.execute, count=ns.count, region=ns.region)


def print_dry_run(kind: str, payloads: Iterable[Any]) -> int:
    """Print payloads for a dry run and return how many were printed."""

    items = list(payloads)
    print(f"[dry-run] would send {len(items)} {kind} record(s). "
          f"No AWS call made. Re-run with --execute to send.")
    for i, payload in enumerate(items, start=1):
        print(f"--- {kind} #{i} ---")
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return len(items)


def get_boto3_client(service: str, region: str):  # pragma: no cover - exercised only under --execute
    """Lazily import boto3 and return a client.

    Imported here (not at module top) so importing the seed scripts performs no
    AWS I/O and requires no credentials. Only reached on the ``--execute`` path.
    """

    import boto3  # local import: lazy, no import-time AWS dependency

    return boto3.client(service, region_name=region)
