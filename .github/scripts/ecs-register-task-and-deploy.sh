#!/usr/bin/env bash
# Register a new ECS task definition with an ECR digest-pinned image, set GIT_SHA on the target
# container, then update the service to that revision + force-new-deployment.
# Same script for API and worker: only ECS_* / ECR_* env differs per step.
#
# Rationale: mutable tags (including implicit default) cause drift; digest pins the exact layer.
# Force-only deploy does not change revision; a new revision ties the service to this image.
# CI pushes only :$GITHUB_SHA; this resolves digest for that tag (not `latest`).
#
# Required env: AWS_REGION, ECS_CLUSTER, ECS_SERVICE, ECS_TASK_DEFINITION_FAMILY,
#               ECS_CONTAINER_NAME, ECR_REGISTRY, ECR_REPOSITORY, IMAGE_TAG
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

echo "ecs-register-task-and-deploy: service=${ECS_SERVICE} family=${ECS_TASK_DEFINITION_FAMILY} repo=${ECR_REPOSITORY} tag=${IMAGE_TAG}"

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
echo "image=${IMAGE_URI}"

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

NEW_REV="$(aws ecs register-task-definition \
  --region "${AWS_REGION}" \
  --cli-input-json "file://${TMP}" \
  --query 'taskDefinition.revision' \
  --output text)"

echo "registered ${ECS_TASK_DEFINITION_FAMILY}:${NEW_REV}"

aws ecs update-service \
  --region "${AWS_REGION}" \
  --cluster "${ECS_CLUSTER}" \
  --service "${ECS_SERVICE}" \
  --task-definition "${ECS_TASK_DEFINITION_FAMILY}:${NEW_REV}" \
  --force-new-deployment

echo "update-service submitted (${ECS_SERVICE} → revision ${NEW_REV})"
