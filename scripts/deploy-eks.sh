#!/usr/bin/env bash
#
# deploy-eks.sh — App_Deploy for EKS workers (Product_A / EKS Fargate).
#
# Task 19.1 — Requirements 22.1, 22.3. Deploys ONLY the application layer:
#   docker build -> ECR push -> kubectl apply (k8s manifests).
# Separate from the infra terraform apply (Req 22.1); NEVER calls terraform.
#
# Safety design:
#   * DEFAULT IS DRY-RUN (print-only). Without --execute every real command
#     (docker / aws / kubectl) is only echoed, never run. The dry-run path
#     never invokes docker, the AWS CLI, or kubectl.
#   * Real ARNs / account ids / domains / secrets are NOT embedded. Everything
#     comes from environment variables / placeholders.
#
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"

usage() {
  cat <<'USAGE'
Usage: deploy-eks.sh [--execute] [--tag <image-tag>] [-h|--help]

Deploy EKS workers: docker build -> ECR push -> kubectl apply. App_Deploy
only; does NOT run terraform.

Options:
  --execute        Run the real docker/aws/kubectl commands. Omitted => dry-run.
  --dry-run        Explicitly dry-run (this is the default).
  --tag <tag>      Image tag to build/push (default: value of IMAGE_TAG or "latest").
  -h, --help       Show this help and exit.

Required environment variables:
  AWS_REGION       AWS region (e.g. ap-northeast-1).
  AWS_ACCOUNT_ID   AWS account id that owns the ECR registry.
  ECR_REPO         ECR repository name for eks-workers (e.g. ops-platform-dev-eks-workers).
  EKS_CLUSTER      EKS cluster name (e.g. ops-platform-dev-eks).

Optional environment variables:
  IMAGE_TAG        Default image tag when --tag is not given (default: latest).
  APP_DIR          Path to the eks-workers build context (default: apps/eks-workers).
  K8S_DIR          Directory of k8s manifests to apply (default: apps/eks-workers/k8s).
  K8S_NAMESPACE    Namespace for the workers (default: workers).

Examples:
  # dry-run (default): prints the commands, touches nothing
  AWS_REGION=ap-northeast-1 AWS_ACCOUNT_ID=<account-id> \
    ECR_REPO=ops-platform-dev-eks-workers \
    EKS_CLUSTER=ops-platform-dev-eks \
    scripts/deploy-eks.sh --tag v1

  # actually deploy (explicit opt-in)
  ... same env ... scripts/deploy-eks.sh --tag v1 --execute
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

APP_DIR="${APP_DIR:-apps/eks-workers}"
K8S_DIR="${K8S_DIR:-apps/eks-workers/k8s}"
K8S_NAMESPACE="${K8S_NAMESPACE:-workers}"

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

require_env AWS_REGION AWS_ACCOUNT_ID ECR_REPO EKS_CLUSTER

# --- run helper: dry-run echoes, --execute runs -----------------------------
# In dry-run the real command is ONLY printed (docker/aws/kubectl never invoked).
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
  echo "[dry-run] deploy-eks: print-only. No docker/aws/kubectl call made. Re-run with --execute to deploy."
fi
echo "[info] target image: ${IMAGE_URI}"
echo "[info] EKS cluster: ${EKS_CLUSTER} (namespace: ${K8S_NAMESPACE})"
echo "[info] manifests dir: ${K8S_DIR}"

# 1) docker build
run docker build -t "${IMAGE_URI}" "${APP_DIR}"

# 2) ECR login + push
run bash -c "aws ecr get-login-password --region '${AWS_REGION}' | docker login --username AWS --password-stdin '${REGISTRY}'"
run docker push "${IMAGE_URI}"

# 3) refresh kubeconfig for the target cluster
run aws eks update-kubeconfig --region "${AWS_REGION}" --name "${EKS_CLUSTER}"

# 4) kubectl apply of the workers manifests
run kubectl apply -n "${K8S_NAMESPACE}" -f "${K8S_DIR}"

if [[ "$EXECUTE" -eq 1 ]]; then MODE="execute"; else MODE="dry-run"; fi
echo "[done] deploy-eks completed (${MODE} mode). App_Deploy only; terraform not invoked."
