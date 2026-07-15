# Infraestructura externa — límites de carga multipart

La app aplica límites por request (`MAX_FILES_PER_UPLOAD_REQUEST`, `MAX_UPLOAD_FILE_SIZE_MB`,
`MAX_UPLOAD_REQUEST_SIZE_MB`). El reverse proxy y el balanceador **deben** alinearse.

| Control | Valor sugerido | Notas |
|---------|----------------|-------|
| `client_max_body_size` (Nginx) | ≥ `MAX_UPLOAD_REQUEST_SIZE_MB` + overhead multipart (~10%) | Ver tablas abajo |
| `proxy_read_timeout` / `proxy_send_timeout` | ≥ 120s–600s según tamaño/red | Evitar 504 en lotes |
| `proxy_request_buffering` | `on` (default) o `off` si se hace stream | Documentar elección en el host |
| Memoria contenedor API | Suficiente para N archivos spooled + overhead (p. ej. ≥1–2 GiB) | Ver OOM / exit 137 |
| Disco temporal | Espacio para `SpooledTemporaryFile` / uploads | `/tmp` del contenedor |
| Timeout ALB / Cloudflare | ≥ timeouts proxy | Fuera del repo |
| Storage provider | Rate limits / object size caps | Alinear con `MAX_UPLOAD_FILE_SIZE_MB` |

No establecer valores ilimitados. El frontend divide selecciones grandes; el proxy no debe ser el único cuello de botella ni un “whitelist infinito”.

---

## Defaults históricos (compatibilidad)

Si las variables no se definen, el backend usa defaults de **compatibilidad histórica**:

| Variable | Default histórico | Significado |
|----------|-------------------|-------------|
| `MAX_UPLOAD_FILE_SIZE_MB` | **500** | (también vía alias `MAX_UPLOAD_SIZE_MB`) |
| `MAX_UPLOAD_REQUEST_SIZE_MB` | **1024** | Debe ser **≥** tamaño por archivo |
| `MAX_FILES_PER_UPLOAD_REQUEST` | **10** | Por request; el frontend auto-divide selecciones mayores |

Estos defaults **no** son la configuración recomendada para cargas típicas de fotografías.
El arranque falla si `MAX_UPLOAD_REQUEST_SIZE_MB < MAX_UPLOAD_FILE_SIZE_MB` o si alguno es `≤ 0`.

Hints informativos (no forzados por el servidor; expuestos en `GET /api/v3/config/upload-limits`):

| Variable | Default | Semántica |
|----------|---------|-----------|
| `UPLOAD_BATCH_CONCURRENCY` | 2 | Requests de lote concurrentes en el cliente |
| `UPLOAD_RETRY_ATTEMPTS` | 3 | **Reintentos adicionales** tras el intento inicial (3 → hasta **4** requests) |
| `UPLOAD_RETRY_BASE_DELAY_MS` | 1000 | Base del backoff entre reintentos |

---

## Configuración recomendada para fotografías (producción)

Para inventarios fotográficos típicos, preferir límites más acotados que los defaults históricos:

```env
MAX_FILES_PER_UPLOAD_REQUEST=10
MAX_UPLOAD_FILE_SIZE_MB=50
MAX_UPLOAD_REQUEST_SIZE_MB=250

UPLOAD_BATCH_CONCURRENCY=2
UPLOAD_RETRY_ATTEMPTS=3
UPLOAD_RETRY_BASE_DELAY_MS=1000

# Alias legacy (opcional si ya no usás MAX_UPLOAD_FILE_SIZE_MB):
MAX_UPLOAD_SIZE_MB=50
```

`UPLOAD_RETRY_ATTEMPTS=3` significa **tres reintentos adicionales**, es decir **como máximo cuatro intentos**
totales por lote HTTP.

El frontend lee estos límites en runtime vía `GET /api/v3/config/upload-limits`
(`retry_attempts` = reintentos adicionales).

---

## Nginx sugerido (request máxima 250 MB)

Para `MAX_UPLOAD_REQUEST_SIZE_MB=250`, dejar margen de overhead multipart:

```nginx
client_max_body_size 275M;

proxy_connect_timeout 60s;
proxy_send_timeout 600s;
proxy_read_timeout 600s;
send_timeout 600s;
```

También revisar en el host:

* Capacidad y limpieza de `/tmp` (spool de uploads grandes).
* Espacio en disco del volumen de artefactos.
* Memoria del contenedor API bajo concurrencia (`UPLOAD_BATCH_CONCURRENCY` × workers).
* Requests concurrentes de varios usuarios.
* Timeouts del balanceador / CDN ≥ timeouts del proxy.
* Límites del proveedor de storage (tamaño de objeto, throughput).
