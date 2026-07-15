# Infraestructura externa — límites de carga multipart

La app aplica límites por request (`MAX_FILES_PER_UPLOAD_REQUEST`, `MAX_UPLOAD_FILE_SIZE_MB`,
`MAX_UPLOAD_REQUEST_SIZE_MB`). El reverse proxy y el balanceador **deben** alinearse:

| Control | Valor sugerido | Notas |
|---------|----------------|-------|
| `client_max_body_size` (Nginx) | ≥ `MAX_UPLOAD_REQUEST_SIZE_MB` + ~10% overhead multipart | Default app: 1024 MB |
| `proxy_read_timeout` / `proxy_send_timeout` | ≥ 120s (ajustar a redes lentas) | Evitar 504 en lotes |
| `proxy_request_buffering` | `on` (default) o `off` si se hace stream | Documentar elección en el host |
| Memoria contenedor API | Suficiente para N archivos spooled + overhead (p. ej. ≥1–2 GiB) | Ver OOM / exit 137 en OpenCloud |
| Disco temporal | Espacio para `SpooledTemporaryFile` / uploads | `/tmp` del contenedor |
| Timeout ALB / Cloudflare | ≥ timeouts proxy | Fuera del repo |

No establecer valores ilimitados. El frontend divide selecciones grandes; el proxy no debe ser el único cuello de botella ni un “whitelist infinito”.

## Configuración de límites (backend)

- `MAX_UPLOAD_FILE_SIZE_MB` (default **500** si no se define; alias legacy `MAX_UPLOAD_SIZE_MB`).
- `MAX_UPLOAD_REQUEST_SIZE_MB` (default **1024**). Debe ser **≥** `MAX_UPLOAD_FILE_SIZE_MB`; el
  arranque de la app falla con un error de configuración claro si no se cumple, o si cualquiera
  de los dos valores es `<= 0`.
- `MAX_FILES_PER_UPLOAD_REQUEST` (default 10, por request; el frontend auto-divide selecciones mayores).
- Hints informativos (no forzados por el servidor, solo expuestos): `UPLOAD_BATCH_CONCURRENCY`
  (default 2), `UPLOAD_RETRY_ATTEMPTS` (default 3), `UPLOAD_RETRY_BASE_DELAY_MS` (default 1000).

Estos valores se exponen en tiempo de ejecución vía `GET /api/v3/config/upload-limits` para que
el frontend no tenga que hardcodear los límites del servidor.
