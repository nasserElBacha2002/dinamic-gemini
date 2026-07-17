# Runbook — Dinamic Captura (móvil)

## App no detecta fotos

1. Verificar permiso fotos (completo/parcial Android 14+).
2. Confirmar sesión `active` y FGS visible.
3. Forzar “Escanear”.
4. Exportar diagnóstico → adjuntar a ticket.

## FGS no aparece

1. Revisar optimización de batería del OEM.
2. Verificar notificaciones habilitadas.
3. Reiniciar captura.
4. Si falla start: código `FGS_START_FAILED`.

## Upload no avanza

1. Banner offline / `paused_auth`.
2. Abrir Cargas → Reintentar.
3. Verificar límites (`upload-limits`).
4. Espacio libre insuficiente → `CAPTURE_STORAGE_LOW`.

## Token vencido

1. App debe ir a login (`paused_auth`).
2. Tras login, cola se reanuda sin nuevos IDs.
3. Si no: exportar diagnóstico + logout/login.

## Sin conexión

1. Captura local continúa.
2. Cola pausada `offline`.
3. Al volver online, reanudar automáticamente.

## Pasillo bloqueado / job activo

1. Mensaje `JOB_ALREADY_RUNNING` / aisle inactive.
2. No borrar assets remotos.
3. Abrir procesamiento o elegir otro pasillo.

## Job fallido

1. Ver pantalla Procesamiento + `last_processing_error`.
2. Reintentar process solo si listo.
3. Escalar con job_id remoto.

## Reinicio / force close

1. Reabrir app → Inventarios / Pasillos (trabajos pendientes visibles en el pasillo).
2. Cola y jobs se restauran desde SQLite.
3. Force stop: no hay recovery hasta abrir app (limitación Android).

## Datos a adjuntar

- Versión app + build + SHA.
- Export diagnóstico (sin tokens/fotos).
- Inventario/pasillo IDs.
- Hora aproximada del fallo.
