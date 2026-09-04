"""Make the scripts/ directory importable so seed scripts and the seed package
can be imported as top-level modules in tests. No AWS or Terraform access."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
