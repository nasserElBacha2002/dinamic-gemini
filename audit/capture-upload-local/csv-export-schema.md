# CSV export schema (mobile) — schema_version=1

Ver `mobile/src/features/localCsv/csvFormat.ts` (`LOCAL_CSV_HEADERS`).

- UTF-8, RFC 4180, fórmulas neutralizadas con prefijo `'`
- Idempotencia: `content_fingerprint` en tabla `local_csv_exports` (migración móvil v22)
- Generación atómica: `.tmp.csv` → rename
- Sin rutas locales sensibles en celdas; checksum SHA-256 (o FNV fallback en tests Node)

Alcance actual: **por sesión**. Pasillo/inventario completo: extensión futura reutilizando el mismo builder.
