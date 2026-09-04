#!/usr/bin/env bash
#
# deploy-ecs.sh — App_Deploy for Backend_API (Product_A / ECS Fargate).
#
# Task 19.1 — Requirements 22.1, 22.2. Deploys ONLY the application layer:
#   docker build -> ECR push -> ECS service update (force new deployment).
# It is intentionally separate from the infra terraform apply (Req 22.1) and
# NEVER calls terraform.
#
# Safety design:
#   * DEFAULT IS DRY-RUN (print-only). Without --execute every real command
#     (docker / aws) is only echoed, never run. The dry-run path never invokes
#     docker or the AWS CLI.
#   * Real ARNs / account ids / domains / secrets are NOT embedded. Everything
#     comes from environment variables / placeholders.
#
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"

usage() {
  cat <<'USAGE'
Usage: deploy-ecs.sh [--execute] [--tag <image-tag>] [-h|--help]

Deploy Backend_API to ECS Fargate: docker build -> ECR push -> ECS service
update (force new deployment). App_Deploy only; does NOT run terraform.

Options:
  --execute        Run the real docker/aws commands. Omitted => dry-run (print only).
  --dry-run        Explicitly dry-run (this is the default).
  --tag <tag>      Image tag to build/push (default: value of IMAGE_TAG or "latest").
  -h, --help       Show this help and exit.

Required environment variables:
  AWS_REGION       AWS region (e.g. ap-northeast-1).
  AWS_ACCOUNT_ID   AWS account id that owns the ECR registry.
  ECR_REPO         ECR repository name for backend-api (e.g. ops-platform-dev-backend-api).
  ECS_CLUSTER      ECS cluster name (e.g. ops-platform-dev-cluster).
  ECS_SERVICE      ECS service name (e.g. ops-platform-dev-backend-api).

Optional environment variables:
  IMAGE_TAG        Default image tag when --tag is not given (default: latest).
  APP_DIR          Path to the backend-api build context (default: apps/backend-api).

Examples:
  # dry-run (default): prints the commands, touches nothing
  AWS_REGION=ap-northeast-1 AWS_ACCOUNT_ID=<account-id> \
    ECR_REPO=ops-platform-dev-backend-api \
    ECS_CLUSTER=ops-platform-dev-cluster \
    ECS_SERVICE=ops-platform-dev-backend-api \
    scripts/deploy-ecs.sh --tag v1

  # actually deploy (explicit opt-in)
  ... same env ... scripts/deploy-ecs.sh --tag v1 --execute
USAGE
}

# --- argument parsing --------------------------------------------------------
EXECUTE=0
IMAGE_TAG="${IMAGE_TAG:-latest}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute|--no-dry-run) EXECUTE=1; shift ;;
    --dry-run) EXECUTE=0; shift ;;
    --tag) IMAGE_TAG="${2:?--tag requires a value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "$SCRIPT_NAME: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

APP_DIR="${APP_DIR:-apps/backend-api}"

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

require_env AWS_REGION AWS_ACCOUNT_ID ECR_REPO ECS_CLUSTER ECS_SERVICE

# --- run helper: dry-run echoes, --execute runs -----------------------------
# In dry-run the real command is ONLY printed (docker/aws never invoked).
run() {
  if [[ "$EXECUTE" -eq 1 ]]; then
    echo "+ $*"
    "$@"
  else
    echo "[dry-run] $*"
  fi
}

REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${REGISTRY}/${ECR_REPO}:${IMAGE_TAG}"

if [[ "$EXECUTE" -eq 0 ]]; then
  echo "[dry-run] deploy-ecs: print-only. No docker/aws call made. Re-run with --execute to deploy."
fi
echo "[info] target image: ${IMAGE_URI}"
echo "[info] ECS cluster/service: ${ECS_CLUSTER}/${ECS_SERVICE}"

# 1) docker build
run docker build -t "${IMAGE_URI}" "${APP_DIR}"

# 2) ECR login + push
run bash -c "aws ecr get-login-password --region '${AWS_REGION}' | docker login --username AWS --password-stdin '${REGISTRY}'"
run docker push "${IMAGE_URI}"

# 3) ECS service update (force new deployment)
run aws ecs update-service \
  --region "${AWS_REGION}" \
  --cluster "${ECS_CLUSTER}" \
  --service "${ECS_SERVICE}" \
  --force-new-deployment

if [[ "$EXECUTE" -eq 1 ]]; then MODE="execute"; else MODE="dry-run"; fi
echo "[done] deploy-ecs completed (${MODE} mode). App_Deploy only; terraform not invoked."
