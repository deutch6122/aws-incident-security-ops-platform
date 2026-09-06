#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_PATH="${PORTAL_LAMBDA_OUTPUT:-${SCRIPT_DIR}/dist/portal-api.zip}"
STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/portal-lambda-build.XXXXXX")"
trap 'rm -rf "${STAGE_DIR}"' EXIT

mkdir -p "${STAGE_DIR}/package" "$(dirname "${OUTPUT_PATH}")"

if [[ -n "${PORTAL_LAMBDA_VENDOR_DIR:-}" ]]; then
  cp -R "${PORTAL_LAMBDA_VENDOR_DIR}/." "${STAGE_DIR}/package/"
else
  python3 -m pip install \
    --disable-pip-version-check \
    --no-cache-dir \
    --no-compile \
    --requirement "${SCRIPT_DIR}/requirements.txt" \
    --target "${STAGE_DIR}/package"
fi

cp -R "${SCRIPT_DIR}/app" "${STAGE_DIR}/package/app"
find "${STAGE_DIR}/package" -type d -name __pycache__ -prune -exec rm -rf {} +
find "${STAGE_DIR}/package" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

python3 - "${STAGE_DIR}/package" "${OUTPUT_PATH}" <<'PY'
from pathlib import Path
import stat
import sys
import zipfile

source = Path(sys.argv[1])
output = Path(sys.argv[2])
fixed_time = (1980, 1, 1, 0, 0, 0)

with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
        if not path.is_file():
            continue
        relative = path.relative_to(source).as_posix()
        info = zipfile.ZipInfo(relative, fixed_time)
        info.create_system = 3
        mode = 0o755 if path.stat().st_mode & stat.S_IXUSR else 0o644
        info.external_attr = (stat.S_IFREG | mode) << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
PY

python3 - "${OUTPUT_PATH}" <<'PY'
from base64 import b64encode
from hashlib import sha256
from pathlib import Path
import sys

package = Path(sys.argv[1])
digest = sha256(package.read_bytes()).digest()
print(f"Created {package}")
print(f"SHA256(base64)={b64encode(digest).decode('ascii')}")
PY
