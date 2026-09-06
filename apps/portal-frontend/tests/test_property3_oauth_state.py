# Feature: dev-full-stack-wiring, Property 3: OAuth state 検証
# **Validates: Requirements 13.1, 13.2**
"""Execute the frontend JavaScript state predicate with generated inputs."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings
from hypothesis import strategies as st

AUTH_JS = Path(__file__).resolve().parents[1] / "src/public/js/auth.js"
NODE = shutil.which("node")

RUNNER = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const window = {PORTAL_CONFIG: {}};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), {window, Uint8Array});
const [sent, returned] = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(window.PortalAuth.statesMatch(sent, returned)));
"""


@pytest.mark.skipif(NODE is None, reason="node is required for frontend JavaScript tests")
@settings(max_examples=120, deadline=None)
@given(
    sent=st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=80),
    returned=st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=80),
)
def test_state_matches_only_for_the_same_nonempty_value(sent: str, returned: str) -> None:
    result = subprocess.run(
        [NODE, "-e", RUNNER, str(AUTH_JS)],
        input=json.dumps([sent, returned]),
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) is (bool(sent) and sent == returned)
