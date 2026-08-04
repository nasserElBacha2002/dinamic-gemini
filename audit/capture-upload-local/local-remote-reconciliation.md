# Local–remote reconciliation (Fase 6)

Clasificador puro: `mobile/src/features/localRemoteReconciliation/classify.ts`

Outcomes: `MATCHED` | `LOCAL_ONLY` | `SERVER_ONLY` | `CONFLICT` | `MANUAL_RESOLUTION_REQUIRED`

Política: **nunca borrar** el valor local; solo clasificar diferencias (código/cantidad).

UI de resolución autorizada y persistencia de decisiones: pendiente de endurecimiento (comparar con preliminary reconciliation existente en servidor).

Flag: `localRemoteReconciliation` (default on).
