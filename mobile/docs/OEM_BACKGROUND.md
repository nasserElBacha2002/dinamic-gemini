# OEM / background restrictions (Fase 3)

## Estrategia WorkManager (honest)

No se usa un Worker nativo no-op que aparenta drenar la cola.

- Recuperación de uploads/jobs: **al reabrir la app** (SQLite + JS).
- Captura activa: **Foreground Service** mientras el proceso vive.
- Unique work names quedan reservados por si se implementa un worker HTTP nativo real.
- Flag `workManagerScheduling` default **off**.

## Ayuda al operador

No abrir Settings automáticamente. Mostrar texto de ayuda si FGS falla o la cola no avanza:

1. Ajustes → Apps → Dinamic Captura → Batería → Sin restricciones (si el fabricante lo ofrece).
2. Permitir notificaciones.
3. Reabrir la app y usar **Diagnóstico**.

## Work ownership

- `upload-session-{id}` — wake para drain de uploads
- `job-monitor-{id}` — wake para reanudar poll de job
- `remote-delete-{id}` — wake para DELETE remoto pendiente

Fuente de verdad: **SQLite**. WorkManager no duplica HTTP.
