# Fase 7 — Signed URLs (auditoría; no implementado)

## Verificación de infraestructura actual

El cliente móvil y el worker nativo suben vía **multipart a FastAPI** (`AisleAssetsApi.uploadBatch`). No hay endpoints de URL firmada / PUT directo a object storage en el camino de aisle assets.

## Decisión

**No implementar signed URLs ni resumable uploads** hasta:

1. Baseline de throughput multipart post Fase 2 (prepare paralelo + debounce)
2. Confirmar proveedor de storage, IAM, CORS, expiración, lifecycle
3. Adaptar worker nativo al mismo contrato

## Criterio para retomar

Si p95 de transferencia HTTP sigue dominando el tiempo total tras Alt A, diseñar:

1. `POST .../upload-sessions` → URL firmada
2. PUT directo
3. Confirmación idempotente al backend
4. Cleanup de objetos no confirmados
