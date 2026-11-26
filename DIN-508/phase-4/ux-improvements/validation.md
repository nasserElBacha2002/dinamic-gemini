# DIN-508 — Persistencia de transmisión y simplificación de interfaz

## Diagnóstico (causa demostrada)

| Observación | Conclusión |
|-------------|------------|
| Refrescar o cerrar el modal reiniciaba la UI a «sin canal preparado» | **Solo pérdida de estado React**: el `useEffect` en `LiveStreamDialog` ponía `prepared` en `null` en cada apertura. **No** se llamaba a `stop` ni se desmontaba el publisher RTMP. |
| Llamar a `prepare` al reabrir para recuperar credenciales | **Riesgo real**: `prepare` hace upsert y **limpia `publish_blocked_at`**, rehabilitando publicación tras un corte. La recuperación debe ser **read-only**. |

## Cambios implementados

1. **Backend**: `GET /live-stream/channel` (recuperación sin mutar persistencia) y `GET /live-stream/channels` (resumen por inventario).
2. **Modal**: recupera canal vía API; RTMP en acordeón; sin visor HLS interno; enlaces públicos listados (URL solo en sesión tras generar).
3. **Detalle de inventario**: barra con estado en vivo por pasillo, cortar y gestionar, con polling cada 8 s.

## Validación manual pendiente (entorno con RTMP/HLS)

Checklist del alcance (requiere DJI + MediaMTX + backend desplegado):

1. Cerrar/abrir modal sin interrumpir publicación ni rehabilitar tras corte.
2. Refrescar página y recuperar estado «En vivo».
3. Navegar y volver; cerrar sesión (visor público sigue).
4. No regenerar credenciales al reabrir (mismo usuario RTMP).
5. Generar/abrir enlace público; cortar desde barra externa.
6. Aislamiento entre pasillos con varios canales preparados.

## Validación automatizada ejecutada

| Comando | Resultado |
|---------|-----------|
| `uv run pytest tests/unit/live_stream/test_get_prepared_channel.py tests/unit/live_stream/test_prepare_channel_idempotent.py` | 2 passed |
| `npm run test -- tests/features/liveStream/liveStreamPresence.test.ts` | 2 passed |
| `npm run typecheck` | OK |
| `npm run build` | OK |

No se ejecutó deploy ni pruebas E2E con RTMP real en esta pasada.