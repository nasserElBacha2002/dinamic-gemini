# DIN-508 — MediaMTX POC (Phase 2)

Infraestructura **aislada** para ingestión RTMP y reproducción HLS. No depende de `backend/docker-compose.yml`.

## Requisitos

- Docker + Compose v2
- FFmpeg (pruebas sintéticas)
- Python 3.11+ (render de config y probes)

## Inicio rápido

```bash
cd infrastructure/din-508-mediamtx
cp .env.example .env
# Editar .env: contraseñas locales (no versionar)

python3 scripts/render_mediamtx_config.py
bash ../../backend/scripts/ensure_mediamtx_docker_network.sh
docker compose build
docker compose up -d
docker compose ps
```

## Canales

Los paths se derivan de inventario + código de pasillo sin usar el código crudo en el path:

```bash
python3 scripts/channel_id.py <inventory_uuid> "<aisle_code>"
# → live/<uuid>/<16-hex-sha256>
```

La transmisión no requiere que el pasillo exista en SQL Server.

## Pruebas

```bash
./scripts/run_poc_validation.sh
```

Evidencia sanitizada: `DIN-508/phase-2/phase-2-tests.txt`

Visor HLS mínimo: abrir `poc/hls-viewer.html` y pegar la URL `http://127.0.0.1:8888/<path>/index.m3u8` con credenciales de lectura.

## Detener

```bash
docker compose down
```