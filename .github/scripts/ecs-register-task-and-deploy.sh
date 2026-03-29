#!/usr/bin/env bash
# Generic ECS deploy: digest-pin image, register new task definition revision, update service.
#
# Use for both API and worker: set ECS_SERVICE / ECS_TASK_DEFINITION_FAMILY / ECS_CONTAINER_NAME /
# ECR_REPOSITORY per invocation (same script, different env).
#
# Why digest (@sha256:...) not a tag:
#   Tags are mutable; ECS can resolve "latest" or retagged SHA to unexpected layers. Pinning digest
#   guarantees the running task uses the exact image built in CI.
#
# Why a new task definition revision every deploy:
#   `update-service --force-new-deployment` alone restarts tasks on the *existing* revision. If the
#   revision still references an ambiguous image, you get drift. Registering a revision with an
#   explicit image URI ties the service to that artifact.
#
# Why not push `latest`:
#   Same mutability problem. CI only pushes immutable `:GITHUB_SHA` tags; this script resolves digest
#   for that tag after push.
#
# Required env:
#   AWS_REGION
#   ECS_CLUSTER
#   ECS_SERVICE
#   ECS_TASK_DEFINITION_FAMILY   # family name only (e.g. backend, worker-api)
#   ECS_CONTAINER_NAME             # container name inside the task definition to retarget
#   ECR_REGISTRY                   # xxx.dkr.ecr.region.amazonaws.com
#   ECR_REPOSITORY                 # repository name only (no registry / no tag)
#   IMAGE_TAG                      # immutable tag (full commit SHA recommended)
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

echo "=== ecs-register-task-and-deploy ==="
echo "service=${ECS_SERVICE} family=${ECS_TASK_DEFINITION_FAMILY} container=${ECS_CONTAINER_NAME}"
echo "repository=${ECR_REPOSITORY} tag=${IMAGE_TAG}"

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

echo "Updating service ${ECS_SERVICE} → taskDefinition ${ECS_TASK_DEFINITION_FAMILY}:${NEW_REV}..."
aws ecs update-service \
  --region "${AWS_REGION}" \
  --cluster "${ECS_CLUSTER}" \
  --service "${ECS_SERVICE}" \
  --task-definition "${ECS_TASK_DEFINITION_FAMILY}:${NEW_REV}" \
  --force-new-deployment

echo "Done. Service ${ECS_SERVICE} rollout started (revision ${NEW_REV}, digest ${DIGEST})."
