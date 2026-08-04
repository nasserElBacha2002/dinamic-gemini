# Capture / upload state machine (parcial)

## Estados de sesión existentes (preservados)

`preparing` → `active` ↔ `paused` → `finishing` → `review` → `uploading` → …

## Semántica añadida (Fase 1)

- `finishing` + `finishStage` (UI ephemeral): `checking_media` | `validating` | `closing` | `preparing_review`
- Freeze watermark: no es un status nuevo; es metadata de set cerrado.

## Estados futuros (Fase 3 — no implementados)

`LOCAL_PROCESSING`, `LOCAL_COMPLETED`, `EXPORT_READY`, `UPLOAD_PENDING`, etc.

El cierre local **no** debe depender de upload/`/process`. Hoy el producto aún acopla procesamiento de pasillo a assets remotos.
