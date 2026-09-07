#!/usr/bin/env bash
#
# Run the dedicated DB migration as one ECS Fargate task. This script defaults
# to print-only dry-run and never invokes Terraform.
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"

usage() {
  cat <<'USAGE'
Usage: deploy-migration.sh [--execute] [-h|--help]

Run the dedicated database migration task on ECS Fargate. The default is a
print-only dry-run. --execute is required for every AWS API operation.

Required environment variables:
  AWS_REGION
  MIGRATION_LAUNCHER_ROLE_ARN
  ECS_CLUSTER
  ECS_TASK_DEFINITION
  PRIVATE_SUBNET_IDS          Comma-separated private-app subnet IDs
  MIGRATION_SECURITY_GROUP_ID Dedicated migration security group ID

Optional environment variables:
  ROLE_SESSION_NAME           Default: ops-platform-db-migration

Example (dry-run):
  AWS_REGION=ap-northeast-1 \
  MIGRATION_LAUNCHER_ROLE_ARN=<migration-launcher-role-arn> \
  ECS_CLUSTER=<migration-cluster-arn> \
  ECS_TASK_DEFINITION=<migration-task-definition-arn> \
  PRIVATE_SUBNET_IDS=subnet-EXAMPLE1,subnet-EXAMPLE2 \
  MIGRATION_SECURITY_GROUP_ID=sg-EXAMPLE \
  scripts/deploy-migration.sh
USAGE
}

EXECUTE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute|--no-dry-run) EXECUTE=1; shift ;;
    --dry-run) EXECUTE=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "${SCRIPT_NAME}: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

require_env() {
  local missing=()
  local name
  for name in "$@"; do
    if [[ -z "${!name:-}" ]]; then
      missing+=("$name")
    fi
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "${SCRIPT_NAME}: missing required environment variable(s): ${missing[*]}" >&2
    exit 1
  fi
}

require_env \
  AWS_REGION \
  MIGRATION_LAUNCHER_ROLE_ARN \
  ECS_CLUSTER \
  ECS_TASK_DEFINITION \
  PRIVATE_SUBNET_IDS \
  MIGRATION_SECURITY_GROUP_ID

ROLE_SESSION_NAME="${ROLE_SESSION_NAME:-ops-platform-db-migration}"
NETWORK_CONFIGURATION="awsvpcConfiguration={subnets=[${PRIVATE_SUBNET_IDS}],securityGroups=[${MIGRATION_SECURITY_GROUP_ID}],assignPublicIp=DISABLED}"

run() {
  if [[ "$EXECUTE" -eq 1 ]]; then
    echo "+ $*" >&2
    "$@"
  else
    echo "[dry-run] $*"
  fi
}

capture() {
  if [[ "$EXECUTE" -ne 1 ]]; then
    echo "${SCRIPT_NAME}: internal error: capture called during dry-run" >&2
    return 1
  fi
  echo "+ $*" >&2
  "$@"
}

if [[ "$EXECUTE" -eq 0 ]]; then
  echo "[dry-run] migration is print-only; AWS CLI is not executed."
  run aws sts assume-role \
    --region "$AWS_REGION" \
    --role-arn "$MIGRATION_LAUNCHER_ROLE_ARN" \
    --role-session-name "$ROLE_SESSION_NAME"
  run aws ecs run-task \
    --region "$AWS_REGION" \
    --cluster "$ECS_CLUSTER" \
    --task-definition "$ECS_TASK_DEFINITION" \
    --launch-type FARGATE \
    --count 1 \
    --network-configuration "$NETWORK_CONFIGURATION"
  run aws ecs wait tasks-stopped \
    --region "$AWS_REGION" \
    --cluster "$ECS_CLUSTER" \
    --tasks '<task-arn-returned-by-run-task>'
  run aws ecs describe-tasks \
    --region "$AWS_REGION" \
    --cluster "$ECS_CLUSTER" \
    --tasks '<task-arn-returned-by-run-task>'
  echo "[done] migration dry-run completed; no AWS call was made."
  exit 0
fi

read -r AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN <<<"$(
  capture aws sts assume-role \
    --region "$AWS_REGION" \
    --role-arn "$MIGRATION_LAUNCHER_ROLE_ARN" \
    --role-session-name "$ROLE_SESSION_NAME" \
    --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' \
    --output text
)"
if [[ -z "$AWS_ACCESS_KEY_ID" || -z "$AWS_SECRET_ACCESS_KEY" || -z "$AWS_SESSION_TOKEN" ]]; then
  echo "${SCRIPT_NAME}: AssumeRole did not return temporary credentials" >&2
  exit 1
fi
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN

TASK_ARN="$(
  capture aws ecs run-task \
    --region "$AWS_REGION" \
    --cluster "$ECS_CLUSTER" \
    --task-definition "$ECS_TASK_DEFINITION" \
    --launch-type FARGATE \
    --count 1 \
    --network-configuration "$NETWORK_CONFIGURATION" \
    --query 'tasks[0].taskArn' \
    --output text
)"
if [[ -z "$TASK_ARN" || "$TASK_ARN" == "None" ]]; then
  echo "${SCRIPT_NAME}: ECS did not return a migration task ARN" >&2
  exit 1
fi
echo "[info] migration task ARN: $TASK_ARN"

run aws ecs wait tasks-stopped \
  --region "$AWS_REGION" \
  --cluster "$ECS_CLUSTER" \
  --tasks "$TASK_ARN"

EXIT_CODE="$(
  capture aws ecs describe-tasks \
    --region "$AWS_REGION" \
    --cluster "$ECS_CLUSTER" \
    --tasks "$TASK_ARN" \
    --query 'tasks[0].containers[0].exitCode' \
    --output text
)"
STOPPED_REASON="$(
  capture aws ecs describe-tasks \
    --region "$AWS_REGION" \
    --cluster "$ECS_CLUSTER" \
    --tasks "$TASK_ARN" \
    --query 'tasks[0].stoppedReason' \
    --output text
)"
CONTAINER_REASON="$(
  capture aws ecs describe-tasks \
    --region "$AWS_REGION" \
    --cluster "$ECS_CLUSTER" \
    --tasks "$TASK_ARN" \
    --query 'tasks[0].containers[0].reason' \
    --output text
)"

if [[ "$EXIT_CODE" != "0" ]]; then
  echo "${SCRIPT_NAME}: migration task failed (exitCode=${EXIT_CODE:-unknown}, stoppedReason=${STOPPED_REASON:-unknown}, containerReason=${CONTAINER_REASON:-unknown})" >&2
  exit 1
fi

echo "[done] migration task stopped successfully with exitCode=0."
