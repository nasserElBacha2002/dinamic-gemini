# Capture finish — design (Fase 1)

## Problema

Omitir el rescan completo cuando SQLite solo tiene fotos `stable` podía perder fotos ya indexadas en MediaStore pero aún no admitidas.

## Solución

1. Sesión → `finishing` + detach listener + emit UI inmediato.
2. Consulta ligera `queryNewPhotosSince` + `detectNewPhotos` (sin mutar si count==0).
3. Si candidatos nuevos **o** validaciones pendientes → `runScanOnce(..., true)` + wait validations + segundo check.
4. Si no → skip full admit path (solo 1 query MediaStore).
5. Stop FGS → reload → readiness → `markCaptureFrozen` → `review`.

## Budgets

| Caso | Objetivo |
|------|----------|
| Todo estable, 0 candidatos | &lt; 1s (medición Fase 0 en device) |
| Con validaciones | Progreso por etapa; timeout 15s |

## Freeze

Persistido en `capture_sessions`:

- `capture_frozen_at`
- `capture_frozen_photo_count`
- `capture_freeze_generation` (idempotente, incrementa)

Upload/CSV futuros deben respetar el set congelado (Fases 3–4).
