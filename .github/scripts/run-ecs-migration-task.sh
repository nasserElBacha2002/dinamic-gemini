#!/usr/bin/env bash
set -euo pipefail

# Run one-off ECS task inside AWS/VPC for migration commands.
# Required env:
#   AWS_REGION
#   ECS_CLUSTER
#   MIGRATION_TASK_DEFINITION
#   MIGRATION_CONTAINER_NAME
#   MIGRATION_SUBNETS              # comma-separated subnet ids
#   MIGRATION_SECURITY_GROUPS      # comma-separated sg ids
#   MIGRATION_COMMAND              # shell command executed as /bin/sh -lc "<cmd>"
# Optional:
#   MIGRATION_ASSIGN_PUBLIC_IP     # ENABLED|DISABLED (default DISABLED)
#   MIGRATION_LAUNCH_TYPE          # default FARGATE
#   MIGRATION_PLATFORM_VERSION     # default LATEST

for var in \
  AWS_REGION \
  ECS_CLUSTER \
  MIGRATION_TASK_DEFINITION \
  MIGRATION_CONTAINER_NAME \
  MIGRATION_SUBNETS \
  MIGRATION_SECURITY_GROUPS \
  MIGRATION_COMMAND
do
  if [[ -z "${!var:-}" ]]; then
    echo "ERROR: missing required env var: ${var}" >&2
    exit 2
  fi
done

MIGRATION_ASSIGN_PUBLIC_IP="${MIGRATION_ASSIGN_PUBLIC_IP:-DISABLED}"
MIGRATION_LAUNCH_TYPE="${MIGRATION_LAUNCH_TYPE:-FARGATE}"
MIGRATION_PLATFORM_VERSION="${MIGRATION_PLATFORM_VERSION:-LATEST}"

echo "Starting ECS migration task"
echo " - cluster: ${ECS_CLUSTER}"
echo " - task_definition: ${MIGRATION_TASK_DEFINITION}"
echo " - container: ${MIGRATION_CONTAINER_NAME}"
echo " - launch_type: ${MIGRATION_LAUNCH_TYPE}"
echo " - assign_public_ip: ${MIGRATION_ASSIGN_PUBLIC_IP}"
echo " - command: ${MIGRATION_COMMAND}"

NETWORK_JSON="$(python3 - <<'PY'
import json, os
subnets = [x.strip() for x in os.environ["MIGRATION_SUBNETS"].split(",") if x.strip()]
sgs = [x.strip() for x in os.environ["MIGRATION_SECURITY_GROUPS"].split(",") if x.strip()]
cfg = {
    "awsvpcConfiguration": {
        "subnets": subnets,
        "securityGroups": sgs,
        "assignPublicIp": os.environ.get("MIGRATION_ASSIGN_PUBLIC_IP", "DISABLED"),
    }
}
print(json.dumps(cfg))
PY
)"

OVERRIDES_JSON="$(python3 - <<'PY'
import json, os
print(json.dumps({
    "containerOverrides": [{
        "name": os.environ["MIGRATION_CONTAINER_NAME"],
        "command": ["/bin/sh", "-lc", os.environ["MIGRATION_COMMAND"]],
    }]
}))
PY
)"

RUN_OUT="$(aws ecs run-task \
  --region "${AWS_REGION}" \
  --cluster "${ECS_CLUSTER}" \
  --task-definition "${MIGRATION_TASK_DEFINITION}" \
  --launch-type "${MIGRATION_LAUNCH_TYPE}" \
  --platform-version "${MIGRATION_PLATFORM_VERSION}" \
  --network-configuration "${NETWORK_JSON}" \
  --overrides "${OVERRIDES_JSON}" \
  --count 1 \
  --started-by "gha-migrate-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}")"

TASK_ARN="$(python3 - <<'PY' "${RUN_OUT}"
import json, sys
data = json.loads(sys.argv[1])
failures = data.get("failures", [])
if failures:
    print("FAILURE: ecs run-task returned failures:", file=sys.stderr)
    for f in failures:
        print(f" - arn={f.get('arn')} reason={f.get('reason')} detail={f.get('detail')}", file=sys.stderr)
    sys.exit(10)
tasks = data.get("tasks", [])
if not tasks:
    print("FAILURE: ecs run-task returned no tasks", file=sys.stderr)
    sys.exit(11)
print(tasks[0]["taskArn"])
PY
)"

echo "Task ARN: ${TASK_ARN}"
echo "Waiting for task to stop..."
aws ecs wait tasks-stopped \
  --region "${AWS_REGION}" \
  --cluster "${ECS_CLUSTER}" \
  --tasks "${TASK_ARN}"

DESC_OUT="$(aws ecs describe-tasks \
  --region "${AWS_REGION}" \
  --cluster "${ECS_CLUSTER}" \
  --tasks "${TASK_ARN}")"

python3 - <<'PY' "${DESC_OUT}"
import json, os, sys
data = json.loads(sys.argv[1])
tasks = data.get("tasks", [])
if not tasks:
    print("FAILURE: describe-tasks returned no tasks", file=sys.stderr)
    sys.exit(20)
t = tasks[0]
containers = t.get("containers", [])
target = None
for c in containers:
    if c.get("name") == os.environ["MIGRATION_CONTAINER_NAME"]:
        target = c
        break
if target is None and containers:
    target = containers[0]

print("Task stopped:")
print(f" - lastStatus: {t.get('lastStatus')}")
print(f" - stopCode: {t.get('stopCode')}")
print(f" - stoppedReason: {t.get('stoppedReason')}")
if target is not None:
    print(f" - container: {target.get('name')}")
    print(f" - exitCode: {target.get('exitCode')}")
    print(f" - reason: {target.get('reason')}")
    print(f" - runtimeId: {target.get('runtimeId')}")

task_id = (t.get("taskArn") or "").split("/")[-1]
if task_id and target is not None and target.get("name"):
    print("CloudWatch log stream hint:")
    print(f" - <awslogs-stream-prefix>/{target.get('name')}/{task_id}")

exit_code = None if target is None else target.get("exitCode")
if exit_code is None:
    print("FAILURE: migration container exitCode is unavailable.", file=sys.stderr)
    sys.exit(21)
if int(exit_code) != 0:
    print(f"FAILURE: migration container exited with code {exit_code}", file=sys.stderr)
    sys.exit(int(exit_code))
print("ECS migration task completed successfully.")
PY
