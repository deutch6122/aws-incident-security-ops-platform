#!/usr/bin/env bash
#
# deploy-frontend.sh — App_Deploy for Status Portal static frontend (Product_B).
#
# Task 19.1 — Requirements 22.1, 22.4. Deploys ONLY the application layer:
#   verify static files -> aws s3 sync -> CloudFront invalidation.
# Separate from the infra terraform apply (Req 22.1); NEVER calls terraform.
#
# Safety design:
#   * DEFAULT IS DRY-RUN (print-only). Without --execute every real command
#     (aws s3 / cloudfront) is only echoed, never run. The dry-run path never
#     invokes the AWS CLI.
#   * Real ARNs / account ids / domains / secrets are NOT embedded. Everything
#     comes from environment variables / placeholders.
#
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"

usage() {
  cat <<'USAGE'
Usage: deploy-frontend.sh [--execute] [-h|--help]

Deploy the Status Portal static frontend: verify static files -> aws s3 sync
-> CloudFront invalidation. App_Deploy only; does NOT run terraform.

Options:
  --execute        Run the real aws s3/cloudfront commands. Omitted => dry-run.
  --dry-run        Explicitly dry-run (this is the default).
  -h, --help       Show this help and exit.

Required environment variables:
  AWS_REGION                   AWS region (e.g. ap-northeast-1).
  S3_BUCKET                    Portal_Storage bucket name for the static site.
  CLOUDFRONT_DISTRIBUTION_ID   CloudFront distribution id to invalidate.

Optional environment variables:
  FRONTEND_DIR                 Path to built static files
                               (default: apps/portal-frontend/src/public).
  INVALIDATION_PATHS           CloudFront invalidation paths (default: /*).

Examples:
  # dry-run (default): prints the commands, touches nothing
  AWS_REGION=ap-northeast-1 \
    S3_BUCKET=ops-platform-dev-portal-REPLACE_WITH_SUFFIX \
    CLOUDFRONT_DISTRIBUTION_ID=REPLACE_WITH_DISTRIBUTION_ID \
    scripts/deploy-frontend.sh

  # actually deploy (explicit opt-in)
  ... same env ... scripts/deploy-frontend.sh --execute
USAGE
}

# --- argument parsing --------------------------------------------------------
EXECUTE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute|--no-dry-run) EXECUTE=1; shift ;;
    --dry-run) EXECUTE=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "$SCRIPT_NAME: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

FRONTEND_DIR="${FRONTEND_DIR:-apps/portal-frontend/src/public}"
INVALIDATION_PATHS="${INVALIDATION_PATHS:-/*}"

# --- required-env validation -------------------------------------------------
require_env() {
  local missing=()
  local name
  for name in "$@"; do
    if [[ -z "${!name:-}" ]]; then
      missing+=("$name")
    fi
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "$SCRIPT_NAME: missing required environment variable(s): ${missing[*]}" >&2
    echo "Run '$SCRIPT_NAME --help' for usage." >&2
    exit 1
  fi
}

require_env AWS_REGION S3_BUCKET CLOUDFRONT_DISTRIBUTION_ID

# --- run helper: dry-run echoes, --execute runs -----------------------------
# In dry-run the real command is ONLY printed (aws never invoked).
run() {
  if [[ "$EXECUTE" -eq 1 ]]; then
    echo "+ $*"
    "$@"
  else
    echo "[dry-run] $*"
  fi
}

if [[ "$EXECUTE" -eq 0 ]]; then
  echo "[dry-run] deploy-frontend: print-only. No aws call made. Re-run with --execute to deploy."
fi
echo "[info] frontend dir: ${FRONTEND_DIR}"
echo "[info] S3 bucket: ${S3_BUCKET}"
echo "[info] CloudFront distribution: ${CLOUDFRONT_DISTRIBUTION_ID}"

# 1) verify the static files exist before doing anything (always, no AWS I/O)
if [[ ! -d "${FRONTEND_DIR}" ]]; then
  echo "$SCRIPT_NAME: frontend directory not found: ${FRONTEND_DIR}" >&2
  exit 1
fi
if [[ ! -f "${FRONTEND_DIR}/index.html" ]]; then
  echo "$SCRIPT_NAME: expected entrypoint not found: ${FRONTEND_DIR}/index.html" >&2
  exit 1
fi
echo "[info] verified static files under ${FRONTEND_DIR}"

# 2) aws s3 sync (upload static assets)
run aws s3 sync "${FRONTEND_DIR}/" "s3://${S3_BUCKET}/" \
  --region "${AWS_REGION}" \
  --delete

# 3) CloudFront invalidation
run aws cloudfront create-invalidation \
  --distribution-id "${CLOUDFRONT_DISTRIBUTION_ID}" \
  --paths "${INVALIDATION_PATHS}"

if [[ "$EXECUTE" -eq 1 ]]; then MODE="execute"; else MODE="dry-run"; fi
echo "[done] deploy-frontend completed (${MODE} mode). App_Deploy only; terraform not invoked."
