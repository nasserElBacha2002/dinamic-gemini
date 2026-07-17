# OEM / background restrictions (Fase 3)

## Comportamiento esperado

| Situación | Comportamiento |
|-----------|----------------|
| App en foreground + FGS | Captura y notificación activas |
| Pantalla bloqueada | FGS mantiene sesión si el SO lo permite |
| Doze / Battery Saver | Uploads diferidos; WorkManager wake + restore al abrir |
| App standby | Cola en SQLite; drain al reabrir |
| Force stop | **No** hay work tras force-stop; al abrir se recupera estado |
| OEM agresivo (Xiaomi/etc.) | Puede matar FGS; documentar desactivar optimización **con consentimiento** |

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
