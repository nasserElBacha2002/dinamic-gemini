# Security review — Procesamiento / sync móvil

---

## 1. Trust boundaries

```text
[Untrusted device]
   │ HTTPS + Bearer JWT
   ▼
[API gateway / FastAPI]  ← valida authz, schema, sizes, ownership
   │
   ▼
[Object storage / SQL / workers]  ← trusted compute
   │
   ▼
[Web review operators]  ← authoritative corrections
```

Regla: **todo resultado producido en el dispositivo es input no confiable** hasta validación servidor.

---

## 2. Superficies de ataque

| Superficie | Estado actual | Riesgo futuro (local process) |
|------------|---------------|-------------------------------|
| Multipart upload | Auth JWT; size limits | Malicious images (decompression bombs) — ya mitigado en parte por caps |
| Process start | Idempotency key | Abuse de process spam — rate limits? (open question) |
| Token storage | SecureStore | Root/backup extract |
| Signed GET display | TTL | Si se añade signed PUT: scope abuse |
| Preliminary results API | N/A hoy | **Injection de códigos/qty falsos** |
| Logs móviles | Revisar PII | Evitar payloads de etiquetas en cleartext largo |
| Local SQLite | Sin cifrado at-rest documentado | Extracción de fotos/resultados en device perdido |

---

## 3. Datos sensibles

| Dato | Dónde | Controles actuales |
|------|-------|--------------------|
| JWT access/refresh | SecureStore | OK baseline |
| API key opcional | Config build | Evitar en prod si no necesario |
| Fotos de pasillo | Gallery + cache transform | Permisos MediaStore; cleanup transforms |
| Códigos internos / cantidades | Resultados server | Móvil hoy solo summary |
| Secretos LLM/OCR/S3 | Solo server env | **No deben ir al APK** |

---

## 4. Controles requeridos para preliminary results

El servidor debe validar:

- JWT + ownership de `inventory_id` / `aisle_id`
- Schema estricto (code length, charset, qty bounds)
- Idempotency key / `client_result_id` únicos
- Asociación a `client_file_id` / `source_asset_id` existente o pendiente
- `pipeline_version` conocida
- Rechazo si ya hay resultado servidor más nuevo
- Rate limiting por usuario/dispositivo
- Tamaño máximo de `payload_raw`
- No aceptar `RESOLVED` final sin evidencia si política de auditoría lo exige

---

## 5. Amenazas clave

### [CRITICAL] Manipulación de resultados locales

**Impacto:** Inventario falso si el servidor confía ciegamente.  
**Mitigación:** Validación + evidencia obligatoria + review web; marcar `creation_source` / `resolved_by=LOCAL_CODE_SCAN` auditable.

### [HIGH] Credenciales de storage o LLM en el cliente

**Impacto:** Compromiso de infraestructura.  
**Mitigación:** Prohibido; signed URLs de corta vida emitidas por API.

### [HIGH] Replay de preliminary results

**Impacto:** Duplicar o reintroducir datos.  
**Mitigación:** Idempotency + version tokens + reject stale.

### [MEDIUM] SQLite / cache sin wipe en logout

**Impacto:** Datos residuales.  
**Mitigación:** Wipe al logout; retención limitada; no backup automático de DB sensible si posible.

### [MEDIUM] AbortSignal no usado en uploads

**Evidencia:** API acepta signal; `UploadQueue` no pasa AbortSignal.  
**Impacto:** Cancelación UX incompleta; menos control de sesiones.  
**Mitigación:** Wire cancel → abort in-flight.

### [LOW] Logs con metadata de captura

**Mitigación:** Redactar filenames/GPS; ya se evita ACCESS_MEDIA_LOCATION.

---

## 6. Autenticación / autorización

- Actual: mismo admin JWT que web (`get_current_admin`).
- Futuro opcional: roles “capture-only” sin permisos de review.
- Refresh mutex en `ApiClient` — mantener.
- Upload pause on 401 — mantener.

---

## 7. Almacenamiento local

- Transforms bajo `cacheDirectory/dinamic-upload/` (`photoPrepare` / `storageCleanup`).
- Política: borrar transforms tras upload OK; no retener originales copiados más de N días.
- Evaluar cifrado SQLCipher solo si threat model de device lost lo exige (coste).

---

## 8. Background / OEM

- FGS requiere notificación visible (ya en captura).
- WorkManager sujeto a Doze/Samsung — no asumir ejecución ilimitada.
- No elevar privilegios innecesarios.

---

## 9. Mitigaciones prioritarias (antes de CODE_SCAN local)

1. Instrumentar y endurecer upload (A) sin nuevos trust claims.
2. Diseñar preliminary API con deny-by-default.
3. Contract tests anti-divergencia del parser.
4. Feature flags + kill switch remoto.
5. Auditoría de logs móviles.

---

## 10. Conclusión seguridad

La arquitectura recomendada es viable **solo si** el servidor valida y puede invalidar resultados móviles. El procesamiento local mejora UX; **no** puede ser autoridad de inventario.
