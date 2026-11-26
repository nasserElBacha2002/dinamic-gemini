# DJI Fly — primera transmisión productiva (OpenCloud)

Prerrequisito: administrador habilitó `LIVE_STREAM_ENABLED` y MediaMTX con `authHTTP` hacia el backend.

## En la aplicación web (inventario autorizado)

1. Abrí el inventario del relevamiento.
2. **Transmisión en vivo** → elegí código de pasillo (puede ser antes de importar el pasillo).
3. **Preparar transmisión** → copiá:
   - URL RTMP (o **Copiar URL con usuario/contraseña** si DJI Fly usa un solo campo)
   - Usuario y contraseña de **publicación** (no los del visor ni del enlace público)
4. (Opcional) **Generar enlace público** para espectadores sin login.

## En DJI Fly (RC 2 + Air 3S — validado en Fase 2)

1. Transmisión en vivo → personalizada → RTMP.
2. Pegá la URL y credenciales de publicación del paso 3.
3. Iniciá transmisión antes o durante el vuelo del pasillo.

## Cortar transmisión

1. En el diálogo interno: **Cortar transmisión** → confirmar.
2. El dron no debe volver a publicar hasta que operador pulse **Preparar transmisión** otra vez.
3. El enlace público existente sigue vigente según su vencimiento; no se revoca al cortar.

## Rehabilitar mismo pasillo

**Preparar transmisión** nuevamente → mismo usuario/contraseña determinísticos → nueva sesión RTMP en DJI.

## Pendiente físico

Validar en OpenCloud con RTMP público/TLS según configuración Nginx del VPS (no declarado OK hasta prueba del operador).