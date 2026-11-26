# DIN-508 Phase 2 — Guía de validación física DJI Air 3S

**Estado:** validación física **ejecutada** (Air 3S + RC 2 → RTMP path corto `dji` → HLS 200). Ver sección RC 2 / micrófono para limitaciones de DJI Fly.

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

**Campo (RC 2, Fly ≥ 1.16.0):** probado con URL en un solo campo, query `user` / `pass`, path corto vía `POC_STREAM_PATH_A=dji` (ver `infrastructure/din-508-mediamtx/.env.example`). Si Fly no admite query auth en otros modelos de control, Phase 3 debe usar clave en path + `authHTTP` vía FastAPI.

### RTMPS

- MediaMTX POC: `rtmpEncryption: "no"` (puerto 19350 plano).
- RTMPS en DJI Fly: **no verificado**; requiere TLS en edge o `rtmps://` en despliegue productivo.

## DJI RC 2 — micrófono obligatorio para **iniciar** RTMP (no es MediaMTX)

Desde **DJI Fly v1.16.0**, en **RC 2 / RC Pro / Smart Controller** (sin micrófono integrado) la app **no arranca** la transmisión RTMP hasta detectar un micrófono en el **USB‑C inferior**. No se puede omitir desde el servidor ni con la URL RTMP.

| Objetivo operativo | Qué hacer |
|--------------------|-----------|
| **No llevar mic dedicado al inventario** | Usar **RC‑N2/RC‑N3 + teléfono** (el mic del teléfono satisface a DJI) o **RC Pro 2** (mic integrado). |
| **Seguir con RC 2** | Micrófono USB‑C mínimo en el kit de campo (auricular con mic o adaptador USB‑C → 3.5 mm). No hace falta hablar: DJI exige **pista de audio en el stream**, no uso de voz. El operador puede silenciar en el reproductor HLS. |
| **Android sin cable extra** | Apps de terceros que simulan mic Bluetooth hacia el RC 2 (no aplican en iPhone). No validado en este repo. |
| **Bajar versión de DJI Fly** | Versiones &lt; 1.16 permitían RTMP sin mic; **no recomendado** (compatibilidad Air 3S / seguridad / soporte DJI). |

**Dinamic no puede eliminar este requisito en software propio** mientras el ingest sea RTMP saliente de DJI Fly en RC 2. Decisiones de producto: estándar de controlador en campo o ítem de kit barato en cada maletín RC 2.

## Pasos operador (manual)

1. Derivar `<path>` con inventario + código de pasillo (no hace falta pasillo en SQL).
2. Copiar URL RTMP completa con credenciales de **publicación** del canal.
3. DJI Fly → transmisión → plataforma **RTMP** personalizada → pegar URL → iniciar live.
4. Verificar HLS en navegador (`poc/hls-viewer.html` + credenciales de **lectura**).
5. Detener live en DJI Fly al finalizar pasillo.
6. **Mismo canal, vuelo consecutivo:** repetir paso 3 con la misma URL.
7. **Cambio de pasillo:** nuevo `channel_id.py` → nueva URL RTMP.

## Checklist de evidencia (campo)

- [x] RTMP personalizado (RC 2 + Fly, path `dji`, query auth)
- [x] Publicación MediaMTX (`2 tracks: H264, MPEG-4 Audio`)
- [x] HLS playlist HTTP 200 con credencial de lectura
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