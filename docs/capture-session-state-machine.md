# Capture Session State Machine (v3)

Definición operativa de estados y transiciones del flujo de ingesta.

## Estados

- `DRAFT`
- `IMPORTING`
- `READY_FOR_REVIEW`
- `ASSIGNMENT_PROPOSED`
- `CONFIRMING`
- `CONFIRMED` (reservado para fases futuras)
- `CANCELLED`
- `FAILED`

## Acciones del módulo

- crear sesión
- subir ítems (`items`)
- cerrar sesión (`close`)
- cancelar sesión (`cancel`)
- ajustar offset (`clock-offset`)
- ejecutar preview (`preview-assignment`)
- materializar (`materialize`)

## Reglas por estado

## DRAFT

- **allowed**
  - subir ítems
  - cerrar sesión (solo si hay >=1 ítem importado)
  - cancelar sesión
  - ajustar offset
- **forbidden**
  - preview
  - materializar
- **transitions**
  - `DRAFT -> IMPORTING` (primer upload importado)
  - `DRAFT -> READY_FOR_REVIEW` (close con ítems válidos)
  - `DRAFT -> CANCELLED` (cancel)

## IMPORTING

- **allowed**
  - subir ítems
  - cerrar sesión
  - cancelar sesión
  - ajustar offset
- **forbidden**
  - preview sin cierre
  - materializar
- **transitions**
  - `IMPORTING -> READY_FOR_REVIEW` (close)
  - `IMPORTING -> CANCELLED` (cancel)

## READY_FOR_REVIEW

- **allowed**
  - preview
  - ajustar offset
  - cancelar sesión
  - close idempotente (permanece READY_FOR_REVIEW)
- **forbidden**
  - subir ítems (sesión cerrada)
  - materializar sin preview válido
- **transitions**
  - `READY_FOR_REVIEW -> ASSIGNMENT_PROPOSED` (preview)
  - `READY_FOR_REVIEW -> CANCELLED` (cancel)

## ASSIGNMENT_PROPOSED

- **allowed**
  - materializar
  - preview (re-run)
  - ajustar offset (resetea preview y vuelve a READY_FOR_REVIEW)
  - cancelar sesión
- **forbidden**
  - subir ítems
  - close
- **transitions**
  - `ASSIGNMENT_PROPOSED -> CONFIRMING` (materialize)
  - `ASSIGNMENT_PROPOSED -> READY_FOR_REVIEW` (clock-offset update)
  - `ASSIGNMENT_PROPOSED -> CANCELLED` (cancel)

## CONFIRMING

- **allowed**
  - consulta de detalle/listado
  - reintento de materialización con misma idempotency key (replay)
- **forbidden**
  - subir ítems
  - close
  - preview
  - clock-offset
  - materializar con key distinta
- **transitions**
  - `CONFIRMING -> CONFIRMED` (fases futuras, no implementado en R1)

## CONFIRMED

- **allowed**
  - solo lectura
- **forbidden**
  - close
  - cancel
  - upload
  - preview
  - materialize
  - clock-offset

## CANCELLED

- **allowed**
  - solo lectura
  - cancel idempotente
- **forbidden**
  - upload
  - preview
  - materialize
  - close
  - clock-offset

## FAILED

- **allowed**
  - solo lectura
- **forbidden**
  - upload
  - preview
  - materialize
  - close
  - clock-offset

## Transiciones clave (resumen)

- `DRAFT -> IMPORTING -> READY_FOR_REVIEW -> ASSIGNMENT_PROPOSED -> CONFIRMING`
- `ASSIGNMENT_PROPOSED -> READY_FOR_REVIEW` (por cambio de offset)
- `* -> CANCELLED` en estados permitidos

## Notas de implementación

- `preview` requiere sesión cerrada (`closed_at != null`).
- `materialize` requiere estado `ASSIGNMENT_PROPOSED` y candidatos `IMPORTED + PROPOSED`.
- `CONFIRMING` en fase actual significa “materializado y bloqueado para mutaciones del flujo”.
