# Capture Session Guardrails (R1)

Reglas obligatorias para preservar arquitectura, determinismo e integración con pipeline.

## Invariantes críticos

- Nunca crear `SourceAsset` durante upload a staging (`/items`).
- Solo `materialize` crea `SourceAsset` desde `CaptureSessionItem`.
- Preview es determinístico (orden temporal + heurística explícita del módulo).
- Materialización es idempotente por `(session_id, idempotency_key)`.
- El pipeline (`process_aisle`) consume exclusivamente `SourceAsset`.

## Reglas de implementación

- Rutas API deben mantenerse delgadas: parsear -> use case -> serializar.
- Errores de negocio en captura deben salir como estructura `code/detail`.
- No introducir lógica de pipeline dentro de flujo de captura.
- No acoplar UI a supuestos implícitos; usar estados y códigos documentados.

## Reglas de estados

- Bloquear acciones inválidas según estado (`DRAFT/IMPORTING/READY_FOR_REVIEW/ASSIGNMENT_PROPOSED/CONFIRMING`).
- `CONFIRMING` en fase actual significa: materializado + bloqueado para mutaciones del flujo de captura.
- G1 (inventory-level operable): `upload`, `close` y `cancel` se permiten sin `aisle_id`.
- G1 (fuera de alcance para sesiones sin pasillo): `preview`, `clock-offset` y `materialize` siguen acoplados a sesión aisle-bound y deben responder con error estructurado cuando no aplique.
- G2 (batch staging): contrato HTTP **201** con `items[]` + `errors[]` por archivo en multipart válido; errores de **toda** la petición siguen siendo HTTP de error. Política de transporte en UI: chunks secuenciales (sin POSTs paralelos por tanda). Ver `docs/capture-session-api-contract.md` (sección 6 y “Política de errores”).
- G3 (temporal grouping, inventory-level): segmentación por gap de tiempo sobre ítems importados con `effective_capture_time`; no asigna pasillos ni materializa. Contrato y errores: `docs/capture-session-api-contract.md` (sección “Temporal grouping (G3)”).

## Reglas de datos y trazabilidad

- Mantener `adjusted_capture_time`, `assignment_reason`, `preview_target_position_id` como resultado de preview.
- Mantener metadata mínima de trazabilidad en `SourceAsset.metadata_json` durante materialización.
- Ante evidencia insuficiente, priorizar estados explícitos y no inferencias implícitas.

## Anti-patrones prohibidos

- Saltarse materialización y procesar desde staging.
- Crear un segundo camino de creación de `SourceAsset` fuera de use case de materialización.
- Modificar schema/estados core en R1 para resolver necesidades de UI.
- Introducir integración directa de dron en este track.
