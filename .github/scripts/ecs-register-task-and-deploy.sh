#!/usr/bin/env bash
# Register a new ECS task definition revision with a digest-pinned image, then point the
# service at that revision. Eliminates "untagged ECR image" + force-only deploy drift.
#
# Required env:
#   AWS_REGION
#   ECS_CLUSTER
#   ECS_SERVICE
#   ECS_TASK_DEFINITION_FAMILY   # e.g. backend (not revision)
#   ECS_CONTAINER_NAME            # container in task def to set image on
#   ECR_REGISTRY                 # xxx.dkr.ecr.region.amazonaws.com
#   ECR_REPOSITORY               # repo name only
#   IMAGE_TAG                    # immutable tag, typically full commit SHA
#
set -euo pipefail

for var in \
  AWS_REGION \
  ECS_CLUSTER \
  ECS_SERVICE \
  ECS_TASK_DEFINITION_FAMILY \
  ECS_CONTAINER_NAME \
  ECR_REGISTRY \
  ECR_REPOSITORY \
  IMAGE_TAG
do
  if [[ -z "${!var:-}" ]]; then
    echo "ERROR: missing required env var: ${var}" >&2
    exit 2
  fi
done

echo "Resolving image digest for ${ECR_REPOSITORY}:${IMAGE_TAG}..."
DIGEST="$(aws ecr describe-images \
  --region "${AWS_REGION}" \
  --repository-name "${ECR_REPOSITORY}" \
  --image-ids "imageTag=${IMAGE_TAG}" \
  --query 'imageDetails[0].imageDigest' \
  --output text)"

if [[ -z "${DIGEST}" || "${DIGEST}" == "None" ]]; then
  echo "ERROR: could not resolve digest for ${ECR_REPOSITORY}:${IMAGE_TAG}" >&2
  exit 3
fi

IMAGE_URI="${ECR_REGISTRY}/${ECR_REPOSITORY}@${DIGEST}"
echo "Pinned image URI: ${IMAGE_URI}"

TD_JSON="$(aws ecs describe-task-definition \
  --region "${AWS_REGION}" \
  --task-definition "${ECS_TASK_DEFINITION_FAMILY}" \
  --query 'taskDefinition' \
  --output json)"

MATCH="$(echo "${TD_JSON}" | jq --arg NAME "${ECS_CONTAINER_NAME}" '[.containerDefinitions[] | select(.name == $NAME)] | length')"
if [[ "${MATCH}" -ne 1 ]]; then
  echo "ERROR: expected exactly one containerDefinition named '${ECS_CONTAINER_NAME}', found ${MATCH}" >&2
  exit 4
fi

NEW_TD="$(echo "${TD_JSON}" | jq \
  --arg IMG "${IMAGE_URI}" \
  --arg NAME "${ECS_CONTAINER_NAME}" \
  --arg SHA "${IMAGE_TAG}" \
  '
  del(
    .taskDefinitionArn,
    .revision,
    .status,
    .requiresAttributes,
    .compatibilities,
    .registeredAt,
    .registeredBy,
    .deregisteredAt
  )
  | .containerDefinitions |= map(
      if .name == $NAME then
        .image = $IMG
        | (.environment // []) as $env
        | .environment = (($env | map(select(.name != "GIT_SHA"))) + [{name: "GIT_SHA", value: $SHA}])
      else . end
    )
  ')"

TMP="$(mktemp)"
trap 'rm -f "${TMP}"' EXIT
echo "${NEW_TD}" > "${TMP}"

echo "Registering new task definition revision for family ${ECS_TASK_DEFINITION_FAMILY}..."
NEW_REV="$(aws ecs register-task-definition \
  --region "${AWS_REGION}" \
  --cli-input-json "file://${TMP}" \
  --query 'taskDefinition.revision' \
  --output text)"

echo "Registered ${ECS_TASK_DEFINITION_FAMILY}:${NEW_REV}"

echo "Updating service ${ECS_SERVICE} → ${ECS_TASK_DEFINITION_FAMILY}:${NEW_REV}..."
aws ecs update-service \
  --region "${AWS_REGION}" \
  --cluster "${ECS_CLUSTER}" \
  --service "${ECS_SERVICE}" \
  --task-definition "${ECS_TASK_DEFINITION_FAMILY}:${NEW_REV}" \
  --force-new-deployment

echo "ECS service update submitted. Rollout in progress."
