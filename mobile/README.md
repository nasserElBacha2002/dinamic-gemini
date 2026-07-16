# Dinamic Inventory — App móvil de captura (Android)

Cliente móvil **solo fotografías** para acelerar la carga de imágenes de inventario tomadas
con dron. Usa **exclusivamente el backend existente** (`/auth` + `/api/v3`). No crea backend,
base de datos, worker ni flujo de procesamiento paralelo.

> Estado actual: **Fase 0 — Spike técnico Android** (viabilidad). Las fases 1–7 aún no están
> implementadas. Ver [Fases](#fases-de-implementación).

---

## 1. Alcance de la Fase 0 (esta entrega)

Objetivo: validar la viabilidad de la parte más riesgosa (galería Android + detección + solo
fotos + segundo plano) **antes** de construir la app completa.

Implementado y verificable en este repo:

| Requisito Fase 0 | Dónde | Verificación |
|------------------|-------|--------------|
| Consulta MediaStore **Images** | `src/native/mediaStore.ts` | `mediaType: [photo]` siempre; nunca `video`/`all` |
| Marcador compuesto `(date_added, _id)` | `src/core/compositeCursor.ts`, `src/domain/entities/captureMarker.ts` | tests unitarios |
| Detección de fotos nuevas | `src/core/photoDetection.ts` | tests unitarios (incl. 20 fotos) |
| Filtro de videos / solo imágenes | `src/core/imageFilter.ts`, `src/shared/constants/imageFormats.ts` | test negativo obligatorio |
| Validación de estabilidad | `src/core/stability.ts`, `src/native/stabilityProber.ts` | tests unitarios |
| Foreground Service (contrato) | `src/native/foregroundService.ts` | ver [Limitaciones](#limitaciones-conocidas) |
| Pantalla de prueba en dispositivo | `App.tsx` | plan de prueba manual |

**No** incluido en Fase 0 (fases posteriores): login/API client, cola de uploads, SQLite,
polling de jobs, UI completa.

---

## 2. Restricción transversal: solo fotografías

La app trabaja **exclusivamente con imágenes estáticas**. No lee, muestra, selecciona, sube ni
procesa video; no consulta `MediaStore.Video`; no pide `READ_MEDIA_VIDEO`; no envía `video/*`.

Allowlist inicial (`src/shared/constants/imageFormats.ts`):

```
image/jpeg  image/jpg  image/png  image/webp  image/heic  image/heif
```

Excluidos: GIF, BMP, TIFF, SVG, `application/octet-stream`, sin MIME, y todo `video/*`.

**Garantía comprobada por test**: si aparece un `.mp4` durante la captura, no se detecta, no se
encola, no se envía, y **no mueve el marcador** de la última foto válida
(`tests/photoDetection.test.ts` → "MANDATORY negative test").

---

## 3. Contratos del backend confirmados (leídos del código)

Verificados en `backend/` para que la implementación de fases 1–6 no invente contratos:

- Upload assets (multipart): `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets`
  - Campos: `files` (repetido), `upload_batch_id` (Form), `client_file_ids` (Form, repetido)
  - Respuesta `201 UploadAisleAssetsResponse`: `assets[]`, `batch_id`, `uploaded[]`
    (`{client_file_id, asset_id, filename, status}`), `errors[]`
    (`{filename, code, detail, file_index, client_file_id}`)
  - Idempotencia: índice único `(aisle_id, upload_batch_id, client_file_id)`
  - Fuente: `backend/src/api/routes/v3/assets.py`, `application/use_cases/aisles/upload_aisle_assets.py`
- Límites: `GET /api/v3/config/upload-limits` →
  `max_files_per_request`, `max_file_size_bytes`, `max_request_size_bytes`,
  `upload_batch_concurrency`, `retry_attempts`, `retry_base_delay_ms`
  (`backend/src/api/schemas/upload_limits_schemas.py`)
- Procesamiento: `POST .../process` (202 `{job_id}`), estado `GET .../status`, `GET .../jobs`
- Auth: `POST /auth/login`, `GET /auth/me`, `POST /auth/refresh`, `POST /auth/logout` (Bearer)

> Hallazgo de auditoría (relevante a "solo fotos"): el endpoint de assets **hoy acepta también
> `video/*`** (lo persiste como `SourceAssetType.VIDEO`). La app móvil impide que un video entre
> a su flujo desde el cliente. Un modo `photos_only` en backend queda como cambio menor opcional
> (no bloquea el MVP).

---

## 4. Arquitectura

```
mobile/
  App.tsx                     # pantalla de spike (prueba en dispositivo)
  app.config.ts               # permisos SOLO imágenes; FGS; plugins
  src/
    core/                     # LÓGICA PURA (sin RN/Expo) — testeable en CI liviano
      compositeCursor.ts
      photoDetection.ts
      imageFilter.ts
      stability.ts
      logging.ts
    domain/                   # tipos/en“ums” de dominio (puros)
      entities/ enums/
    native/                   # adaptadores de dispositivo (Expo/RN)
      mediaStore.ts           # MediaStore.Images (expo-media-library)
      stabilityProber.ts      # muestreo de archivo + decode
      foregroundService.ts    # contrato de FGS
    shared/constants/
      imageFormats.ts         # allowlist de imágenes
  tests/                      # unit tests de core
```

Separación clave: **la corrección** (cursor, detección, filtro, estabilidad) vive en `src/core`
como TypeScript puro sin dependencias nativas, por lo que se puede typecheckear y testear sin el
toolchain de Android. Los adaptadores nativos consumen ese core.

---

## 5. Validación en este entorno

Lógica pura (sin dispositivo ni Android SDK):

```bash
cd mobile
npm install
npm run typecheck:core   # tsc sobre src/core + tests
npm run test:core        # jest sobre tests/ (24 tests)
```

Resultado de esta entrega: **typecheck OK**, **24/24 tests OK** (incluye 20 fotos, empate de
timestamp, filtro MIME, exclusión de video, estabilidad, idempotencia de detección, redacción de
logs).

> El typecheck/lint/build **completo** de React Native (App.tsx, `src/native/*`, `app.config.ts`)
> y la generación de APK/AAB requieren el toolchain de Expo + Android SDK, que **no** están
> disponibles en este entorno de auditoría. Ver instrucciones abajo para ejecutarlo en una
> máquina con Android SDK.

---

## 6. Build de desarrollo (máquina con Android SDK)

Requiere Node 18+, JDK 17, Android SDK, un dispositivo/emulador y `EAS`/Expo instalado.

```bash
cd mobile
cp .env.example .env         # setear DINAMIC_API_BASE_URL
npm install
npx expo prebuild -p android --clean   # genera android/ (Development Build)
npx expo run:android                    # instala el dev client en el dispositivo
# o build de artefactos:
#   eas build -p android --profile development   # APK dev client
#   eas build -p android --profile preview       # APK
#   eas build -p android --profile production     # AAB
```

Se usa **Expo Development Build (prebuild)**, no Expo Go, porque el flujo requiere MediaStore
avanzado, Foreground Service y (fases siguientes) uploads persistentes.

---

## 7. Plan de prueba manual en dispositivo (evidencia Fase 0)

Ejecutar en un Android real (idealmente Android 13 y 14):

1. **Permisos solo fotos**: al abrir, el sistema pide acceso a *fotos* (no debe aparecer video).
2. **Marcador**: tocar "Marcar inicio" → congela la última foto existente.
3. **20 fotos**: tomar/copiar 20 fotos al DCIM del dron; **bloquear la pantalla** entre disparos.
4. **Video**: agregar un `.mp4` a la misma carpeta.
5. **Escanear** (o esperar el listener): deben detectarse **20** fotos; "Ignoradas (no imagen)"
   debe contar el video; el video **no** aparece en la lista.
6. **Marcador intacto**: el marcador/último cursor válido corresponde a la última **foto**, no al
   video.

Registrar: versión de Android, fabricante, tiempo de detección, y si la pantalla bloqueada
afectó la detección (ver Limitaciones).

---

## 8. Decisión tecnológica: Expo Dev Build vs React Native CLI

**Recomendación: Expo Development Build (prebuild).**

| Criterio | Expo Managed | **Expo Dev Build** | RN CLI |
|----------|--------------|--------------------|--------|
| MediaStore.Images (expo-media-library, solo `photo`) | Limitado | **Sí** | Sí |
| Permisos granulares 13/14 (sin video) | Parcial | **Sí (config plugin)** | Sí |
| Foreground Service `dataSync` | No | **Sí (config plugin + Service nativo)** | Sí |
| WorkManager / uploads persistentes (fases 5–7) | No | **Sí (módulo nativo)** | Sí |
| Velocidad de desarrollo / OTA | Alta | **Alta** | Media |
| Mantenimiento | Bajo | **Medio** | Alto |

Expo Dev Build cubre todos los requisitos de Fase 0 con un config plugin para el Foreground
Service. Solo se migraría a **RN CLI** si un requisito nativo (p. ej. un comportamiento de FGS/OEM
específico) resultara inviable en Dev Build durante las pruebas físicas; la arquitectura funcional
(este `src/`) no cambiaría.

---

## 9. Limitaciones conocidas

- **Foreground Service**: Expo no trae FGS gestionado. Se requiere un config plugin + un `Service`
  Android mínimo (tipo `dataSync`) en el Development Build. `foregroundService.ts` define el
  contrato; el binding nativo se agrega en la Fase 4/7. Sin él, `isAvailable=false` y la detección
  en segundo plano no está garantizada (la app lo informa explícitamente, no lo simula).
- **Segundo plano / Doze / OEM**: Android puede pausar trabajo con pantalla bloqueada o batería
  restringida; no se promete detección permanente. Se valida en pruebas físicas (Fase 7).
- **Android 14 acceso parcial**: si el usuario concede solo un subconjunto de fotos, la detección
  se limita a ese subconjunto; la UI debe explicarlo (Fase 3/4).
- **MIME desde MediaStore**: algunos OEM no rellenan `MIME_TYPE`; se infiere por extensión y se
  confirma con decode en el prober de estabilidad.
- **Build/APK**: no verificable en el entorno de auditoría (sin Android SDK).

---

## 10. Fases de implementación

- **Fase 0 — Spike (esta entrega):** MediaStore Images, marcador, detección, filtro video,
  estabilidad, contrato FGS, tests, decisión Dev Build.
- Fase 1 — Base: navegación, cliente HTTP, SQLite, SecureStore, logging.
- Fase 2 — Auth: login/me/refresh/logout, manejo de 401.
- Fase 3 — Inventarios y pasillos.
- Fase 4 — Sesión de captura + FGS nativo.
- Fase 5 — Cola de uploads (idempotencia, micro-lotes, offline, respuestas parciales).
- Fase 6 — Procesamiento (process + polling + actividad + segundo pasillo).
- Fase 7 — Hardening (Android 13/14, Doze, OEM, kill, reinicio, observabilidad, E2E).

No avanzar a fases siguientes hasta validar la prueba física de Fase 0 (§7) en dispositivo real.
