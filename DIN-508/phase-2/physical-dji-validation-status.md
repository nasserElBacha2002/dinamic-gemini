# DIN-508 Phase 2 — Physical DJI validation status

| Field | Value |
|-------|--------|
| **Status** | `PHYSICAL_VALIDATION_COMPLETED` (RTMP + HLS local) |
| Drone available this run | **Yes** (Air 3S + RC 2) |
| FFmpeg synthetic validation | **Completed** (see `phase-2-tests.txt`) |
| DJI Fly RTMP field test | **Completed** (path `dji`; ver guía RC 2 / mic) |

## Blockers for field test

- Hardware Air 3S + controlador no utilizado en esta sesión
- Alcance explícito: no abrir RTMP a internet pública en esta fase

## Ready for operator

- `physical-dji-validation-guide.md`
- Infra reproducible en `infrastructure/din-508-mediamtx/README.md`

## Claims **not** made

- RTMP sin micrófono en **RC 2** con Fly ≥ 1.16.0 (bloqueo DJI; ver guía)
- Latencia / resolución medidas con instrumentación
- Comportamiento de reconexión en 4G

## Field notes (2026-11-26)

- Contraseñas MediaMTX: `%` rechazado por MediaMTX v1.11.3 en `authInternalUsers`.
- Operador: mic USB‑C requerido por DJI para **iniciar** live en RC 2; servidor no modifica ese requisito.