# DIN-508 Phase 2 — Guía de validación física DJI Air 3S

**Estado:** infraestructura local lista; **sin vuelo real en esta ejecución**.

## Prerrequisitos

1. MediaMTX POC en ejecución (`infrastructure/din-508-mediamtx`).
2. Teléfono/controlador con **internet** (Wi‑Fi o datos) alcanzando la IP del host MediaMTX.
3. Para pruebas fuera de LAN: túnel o DNS **no configurado en esta fase** (no abrir firewall público sin autorización).

## Derivar URL del canal

```bash
cd infrastructure/din-508-mediamtx
python3 scripts/channel_id.py "<inventory_uuid>" "<código_pasillo_trimmed>"
# Usa strip + mayúsculas (CI SQL); A01 y a01 producen el mismo path.
```

Ejemplo salida: `live/550e8400-e29b-41d4-a716-446655440001/2d4196bc46b61307`

## RTMP para DJI Fly (formato probado con MediaMTX 1.11.3)

FFmpeg validó publicación con:

```
rtmp://<HOST>:19350/<path>?user=<POC_PUB_*_USER>&pass=<POC_PUB_*_PASS>
```

**Pendiente confirmar en DJI Fly** si acepta `user`/`pass` en query string en el campo URL personalizada, o si exige formato `rtmp://host/app/stream` sin query. Si Fly no admite query auth, Phase 3 debe usar clave en path + `authHTTP` vía FastAPI.

### RTMPS

- MediaMTX POC: `rtmpEncryption: "no"` (puerto 19350 plano).
- RTMPS en DJI Fly: **no verificado**; requiere TLS en edge o `rtmps://` en despliegue productivo.

## Pasos operador (manual)

1. Derivar `<path>` con inventario + código de pasillo (no hace falta pasillo en SQL).
2. Copiar URL RTMP completa con credenciales de **publicación** del canal.
3. DJI Fly → transmisión → plataforma **RTMP** personalizada → pegar URL → iniciar live.
4. Verificar HLS en navegador (`poc/hls-viewer.html` + credenciales de **lectura**).
5. Detener live en DJI Fly al finalizar pasillo.
6. **Mismo canal, vuelo consecutivo:** repetir paso 3 con la misma URL.
7. **Cambio de pasillo:** nuevo `channel_id.py` → nueva URL RTMP.

## Checklist de evidencia (campo)

- [ ] RTMP personalizado disponible en el controlador usado (RC 2 vs RC-N3)
- [ ] Resolución / FPS / codec reales (screenshot o log DJI)
- [ ] Reproducción HLS y latencia percibida
- [ ] Pérdida de red y reconexión
- [ ] Dos vuelos seguidos, mismo canal
- [ ] Cambio de canal entre pasillos
- [ ] Conteo de toques manuales en DJI Fly

## Conectividad

| Puerto | Uso |
|--------|-----|
| 19350/TCP | RTMP ingest (POC) |
| 8888/TCP | HLS (solo red de confianza en POC) |

No modificar VPS productivo ni abrir puertos públicos sin aprobación explícita.