# DIN-508 Phase 2 — Physical DJI validation status

| Field | Value |
|-------|--------|
| **Status** | `PENDING_PHYSICAL_VALIDATION` |
| Drone available this run | **No** |
| FFmpeg synthetic validation | **Completed** (see `phase-2-tests.txt`) |
| DJI Fly RTMP field test | **Not executed** |

## Blockers for field test

- Hardware Air 3S + controlador no utilizado en esta sesión
- Alcance explícito: no abrir RTMP a internet pública en esta fase

## Ready for operator

- `physical-dji-validation-guide.md`
- Infra reproducible en `infrastructure/din-508-mediamtx/README.md`

## Claims **not** made

- Compatibilidad definitiva DJI Fly + query-string RTMP auth
- Latencia / resolución reales del dron
- Comportamiento de reconexión en 4G