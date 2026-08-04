# Upload performance — baseline & optimization (parcial)

## Estrategia elegida

**Alternativa A — optimizar multipart actual** (sin signed URLs).

## Hecho en este PR

- Debounce de `emit()` / `refreshCachedSessions` (120 ms).
- Eventos HTTP vs confirmación local separados.
- `bytes_per_second` en batch completed.
- Heal / orphan instrumentados.

## Pendiente Fase 2

- Prepare paralelo 2–3 (Wi‑Fi) / 1–2 (cellular)
- Perfiles de compresión adaptativos adicionales
- Snapshots incrementales por sesión (no listar todas)
- Comparativa throughput vs baseline de campo

## No hacer aún

Signed URL / resumable sin auditoría de storage/IAM.
