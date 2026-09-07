#!/usr/bin/env bash
#
# deploy-eks.sh — App_Deploy for three EKS Fargate workloads.
#
# The script never invokes Terraform. It builds one deterministic worker code
# base, tags it into three dedicated ECR repositories, renders Kubernetes
# manifests to a temporary directory, rejects unresolved placeholders, and only
# performs external commands when --execute is explicitly supplied.
#
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"

usage() {
  cat <<'USAGE'
Usage: deploy-eks.sh [--execute] [--tag <image-tag>] [-h|--help]

Build and deploy the three EKS worker workloads. The default is dry-run; the
script does not call Docker, AWS CLI, or kubectl unless --execute is supplied.
Terraform is never called.

Options:
  --execute        Run Docker, AWS CLI, and kubectl commands.
  --dry-run        Print commands only (default).
  --tag <tag>      Image tag (default: IMAGE_TAG or "latest").
  -h, --help       Show this help and exit.

Required environment variables:
  AWS_REGION
  AWS_ACCOUNT_ID
  EKS_CLUSTER
  ALARM_ECR_REPO
  FINDING_ECR_REPO
  SUMMARY_ECR_REPO
  EKS_ALARM_WORKER_ROLE_ARN
  EKS_FINDING_WORKER_ROLE_ARN
  EKS_CRONJOB_ROLE_ARN
  WORKER_DB_SECRET_ARN
  WORKER_DB_HOST
  WORKER_DB_PORT
  WORKER_DB_NAME
  ALARM_QUEUE_URL
  FINDING_QUEUE_URL
  WORKER_LOG_GROUP_NAME
  PORTAL_REPORTS_BUCKET
  PORTAL_REPORT_METADATA_TABLE
  PORTAL_PUBLIC_STATUS_ITEMS_TABLE

Optional environment variables:
  IMAGE_TAG        Default image tag when --tag is omitted (default: latest).
  APP_DIR          Worker build context (default: apps/eks-workers).
  K8S_DIR          Source manifest directory (default: apps/eks-workers/k8s).

Example (dry-run):
  AWS_REGION=ap-northeast-1 AWS_ACCOUNT_ID=<account-id> \
    EKS_CLUSTER=ops-platform-dev-eks \
    ALARM_ECR_REPO=ops-platform-dev-alarm-event-processor \
    FINDING_ECR_REPO=ops-platform-dev-security-finding-worker \
    SUMMARY_ECR_REPO=ops-platform-dev-monthly-summary-cronjob \
    EKS_ALARM_WORKER_ROLE_ARN=<alarm-role-arn> \
    EKS_FINDING_WORKER_ROLE_ARN=<finding-role-arn> \
    EKS_CRONJOB_ROLE_ARN=<cronjob-role-arn> \
    WORKER_DB_SECRET_ARN=<database-secret-arn> \
    WORKER_DB_HOST=<aurora-writer-endpoint> WORKER_DB_PORT=5432 WORKER_DB_NAME=opsplatform \
    ALARM_QUEUE_URL=<alarm-queue-url> FINDING_QUEUE_URL=<finding-queue-url> \
    WORKER_LOG_GROUP_NAME=/ops-platform-dev/eks/workers \
    PORTAL_REPORTS_BUCKET=<reports-bucket> \
    PORTAL_REPORT_METADATA_TABLE=ops-platform-dev-report-metadata \
    PORTAL_PUBLIC_STATUS_ITEMS_TABLE=ops-platform-dev-public-status-items \
    scripts/deploy-eks.sh --tag v1
USAGE
}

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

require_env \
  AWS_REGION AWS_ACCOUNT_ID EKS_CLUSTER \
  ALARM_ECR_REPO FINDING_ECR_REPO SUMMARY_ECR_REPO \
  EKS_ALARM_WORKER_ROLE_ARN EKS_FINDING_WORKER_ROLE_ARN EKS_CRONJOB_ROLE_ARN \
  WORKER_DB_SECRET_ARN WORKER_DB_HOST WORKER_DB_PORT WORKER_DB_NAME \
  ALARM_QUEUE_URL FINDING_QUEUE_URL WORKER_LOG_GROUP_NAME \
  PORTAL_REPORTS_BUCKET PORTAL_REPORT_METADATA_TABLE PORTAL_PUBLIC_STATUS_ITEMS_TABLE

if [[ "$ALARM_ECR_REPO" == "$FINDING_ECR_REPO" || \
      "$ALARM_ECR_REPO" == "$SUMMARY_ECR_REPO" || \
      "$FINDING_ECR_REPO" == "$SUMMARY_ECR_REPO" ]]; then
  echo "$SCRIPT_NAME: ALARM_ECR_REPO, FINDING_ECR_REPO, and SUMMARY_ECR_REPO must be distinct." >&2
  exit 1
fi

if [[ ! -d "$APP_DIR" ]]; then
  echo "$SCRIPT_NAME: APP_DIR does not exist: $APP_DIR" >&2
  exit 1
fi
if [[ ! -d "$K8S_DIR" ]]; then
  echo "$SCRIPT_NAME: K8S_DIR does not exist: $K8S_DIR" >&2
  exit 1
fi
if ! command -v envsubst >/dev/null 2>&1; then
  echo "$SCRIPT_NAME: envsubst is required to render manifests (install gettext)." >&2
  exit 1
fi

run() {
  if [[ "$EXECUTE" -eq 1 ]]; then
    echo "+ $*"
    "$@"
  else
    echo "[dry-run] $*"
  fi
}

REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
export ALARM_WORKER_IMAGE="${REGISTRY}/${ALARM_ECR_REPO}:${IMAGE_TAG}"
export FINDING_WORKER_IMAGE="${REGISTRY}/${FINDING_ECR_REPO}:${IMAGE_TAG}"
export SUMMARY_CRONJOB_IMAGE="${REGISTRY}/${SUMMARY_ECR_REPO}:${IMAGE_TAG}"

RENDER_DIR="$(mktemp -d "${TMPDIR:-/tmp}/deploy-eks.XXXXXX")"
cleanup() {
  rm -rf "$RENDER_DIR"
}
trap cleanup EXIT

# Restrict envsubst to the approved deployment contract. This prevents an
# unrelated shell variable in a manifest from being expanded accidentally.
ENV_SUBST_VARS='${AWS_REGION} ${ALARM_WORKER_IMAGE} ${FINDING_WORKER_IMAGE} ${SUMMARY_CRONJOB_IMAGE} ${EKS_ALARM_WORKER_ROLE_ARN} ${EKS_FINDING_WORKER_ROLE_ARN} ${EKS_CRONJOB_ROLE_ARN} ${WORKER_DB_SECRET_ARN} ${WORKER_DB_HOST} ${WORKER_DB_PORT} ${WORKER_DB_NAME} ${ALARM_QUEUE_URL} ${FINDING_QUEUE_URL} ${WORKER_LOG_GROUP_NAME} ${PORTAL_REPORTS_BUCKET} ${PORTAL_REPORT_METADATA_TABLE} ${PORTAL_PUBLIC_STATUS_ITEMS_TABLE}'

shopt -s nullglob
manifest_files=("$K8S_DIR"/*.yaml)
shopt -u nullglob
if [[ ${#manifest_files[@]} -eq 0 ]]; then
  echo "$SCRIPT_NAME: no YAML manifests found in $K8S_DIR" >&2
  exit 1
fi

for source_file in "${manifest_files[@]}"; do
  rendered_file="$RENDER_DIR/$(basename "$source_file")"
  envsubst "$ENV_SUBST_VARS" < "$source_file" > "$rendered_file"
done

if grep -REn '\$\{[A-Za-z_][A-Za-z0-9_]*\}|REPLACE_WITH_[A-Za-z0-9_]+' "$RENDER_DIR" >&2; then
  echo "$SCRIPT_NAME: unresolved placeholder found; nothing was deployed." >&2
  exit 1
fi

if [[ "$EXECUTE" -eq 0 ]]; then
  echo "[dry-run] deploy-eks: manifests rendered and validated; no docker/aws/kubectl call made."
fi
echo "[info] alarm image:   $ALARM_WORKER_IMAGE"
echo "[info] finding image: $FINDING_WORKER_IMAGE"
echo "[info] summary image: $SUMMARY_CRONJOB_IMAGE"
echo "[info] EKS cluster:   $EKS_CLUSTER"

# One codebase is built once and tagged into three dedicated repositories.
run docker build --platform linux/amd64 \
  -t "$ALARM_WORKER_IMAGE" \
  -t "$FINDING_WORKER_IMAGE" \
  -t "$SUMMARY_CRONJOB_IMAGE" \
  "$APP_DIR"

run bash -c "aws ecr get-login-password --region '${AWS_REGION}' | docker login --username AWS --password-stdin '${REGISTRY}'"
run docker push "$ALARM_WORKER_IMAGE"
run docker push "$FINDING_WORKER_IMAGE"
run docker push "$SUMMARY_CRONJOB_IMAGE"
run aws eks update-kubeconfig --region "$AWS_REGION" --name "$EKS_CLUSTER"

ensure_coredns_ready() {
  if run kubectl rollout status deployment/coredns -n kube-system --timeout=30s; then
    echo "[info] CoreDNS is already ready."
  else
    echo "[info] CoreDNS is not ready; restarting it so it can be scheduled on the kube-system Fargate profile."
    run kubectl rollout restart deployment/coredns -n kube-system
    run kubectl rollout status deployment/coredns -n kube-system --timeout=300s
  fi

  run kubectl get pods -n kube-system -l k8s-app=kube-dns
}

# In new all-Fargate clusters, CoreDNS can remain Pending if its pods were
# created before the kube-system Fargate profile became active. Workers rely on
# CoreDNS to resolve STS/SQS/Secrets Manager endpoints for IRSA and runtime AWS
# calls, so verify or recycle CoreDNS before deploying application workloads.
ensure_coredns_ready

# Logging prerequisites must be applied before ServiceAccounts and workloads.
apply_order=(
  "00-namespace.yaml"
  "40-fargate-logging.yaml"
  "10-serviceaccounts.yaml"
  "20-alarm-event-processor.yaml"
  "21-security-finding-worker.yaml"
  "30-monthly-summary-cronjob.yaml"
)
for manifest_name in "${apply_order[@]}"; do
  rendered_file="$RENDER_DIR/$manifest_name"
  if [[ ! -f "$rendered_file" ]]; then
    echo "$SCRIPT_NAME: required manifest is missing: $K8S_DIR/$manifest_name" >&2
    exit 1
  fi
  run kubectl apply -f "$rendered_file"
done

if [[ "$EXECUTE" -eq 1 ]]; then MODE="execute"; else MODE="dry-run"; fi
echo "[done] deploy-eks completed ($MODE mode). App_Deploy only; terraform not invoked."
