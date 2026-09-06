"""Property 4: globally unique Portal and ALB access-log bucket names."""

from __future__ import annotations

import re
from pathlib import Path

from hypothesis import given, settings, strategies as st

from naming import MAX_S3_BUCKET_NAME_LENGTH, NAME_PREFIX, globally_unique_bucket_name

DEV_ROOT = Path(__file__).resolve().parents[1]
PORTAL_MAIN = (DEV_ROOT.parents[1] / "modules" / "s3-portal" / "main.tf").read_text(
    encoding="utf-8"
)
ROOT_LOCALS = (DEV_ROOT / "locals.tf").read_text(encoding="utf-8")

AWS_REGIONS = st.sampled_from(
    [
        "ap-northeast-1",
        "ap-southeast-2",
        "eu-central-1",
        "us-east-1",
        "us-west-2",
        "us-gov-west-1",
    ]
)
ACCOUNT_IDS = st.integers(min_value=0, max_value=999_999_999_999).map(
    lambda value: f"{value:012d}"
)


# Feature: dev-full-stack-wiring, Property 4
# **Validates: Requirements 16.1, 16.2, 16.3**
@given(account_id=ACCOUNT_IDS, region=AWS_REGIONS)
@settings(max_examples=120)
def test_portal_and_alb_bucket_names_are_unique_and_bounded(
    account_id: str, region: str
) -> None:
    suffix = f"{account_id}-{region}"
    portal = globally_unique_bucket_name(
        f"{NAME_PREFIX}-portal-storage", account_id, region
    )
    alb_logs = globally_unique_bucket_name(
        f"{NAME_PREFIX}-alb-logs", account_id, region
    )

    assert portal != alb_logs
    assert portal.endswith(f"-{suffix}")
    assert alb_logs.endswith(f"-{suffix}")
    assert len(portal) <= MAX_S3_BUCKET_NAME_LENGTH
    assert len(alb_logs) <= MAX_S3_BUCKET_NAME_LENGTH
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", portal)
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", alb_logs)


def test_property_helper_matches_both_terraform_formulas() -> None:
    assert 'bucket_suffix   = "${data.aws_caller_identity.current.account_id}-${var.aws_region}"' in PORTAL_MAIN
    assert 'bucket_stem_src = "${var.name_prefix}-portal-storage"' in PORTAL_MAIN
    assert 'bucket_name = "${local.bucket_stem}-${local.bucket_suffix}"' in PORTAL_MAIN

    assert 'alb_access_logs_suffix   = "${data.aws_caller_identity.current.account_id}-${var.aws_region}"' in ROOT_LOCALS
    assert 'alb_access_logs_stem_src = "${local.name_prefix}-alb-logs"' in ROOT_LOCALS
    assert 'alb_access_logs_bucket   = "${local.alb_access_logs_stem}-${local.alb_access_logs_suffix}"' in ROOT_LOCALS
