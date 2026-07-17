# Dinamic Inventory — App móvil de captura (Android)

Cliente móvil **solo fotografías** para acelerar la carga de imágenes de inventario tomadas
con dron. Usa **exclusivamente el backend existente** (`/auth` + `/api/v3`). No crea backend,
base de datos, worker ni flujo de procesamiento paralelo.

> Estado: **Fase 3 — hardening / observabilidad (parcialmente validada)**.  
> **Lista solo para rollout limitado**: CI mobile, flags, timeouts HTTPS, diagnóstico, FlatList, cleanup, WorkManager wake bridge.  
> **No** producción general: falta matriz física firmada, firma release con secretos CI, crash reporting con DSN, ProGuard validado en release real.

---

## Alcance: solo fotografías

- Consulta únicamente `MediaStore.Images` / `MediaType.photo`.
- Permisos: `READ_MEDIA_IMAGES` (+ parcial Android 14). **No** `READ_MEDIA_VIDEO`.
- Allowlist: `image/jpeg|jpg|png|webp|heic|heif`.
- Un `.mp4` en la galería **no** entra a la query de imágenes → no UI, no métricas, no cursores.
- Defensa adicional en core: si se inyecta un candidato `video/*`, se rechaza y avanza solo el `scanCursor`.

---

## Implementado en core (puro / testeable en CI)

| Pieza | Archivo |
|-------|---------|
| Cursor compuesto `(dateAdded, assetId)` | `src/core/compositeCursor.ts` |
| Detección + avance de `scanCursor` (admite y rechaza) | `src/core/photoDetection.ts` |
| Filtro MIME / video defensivo | `src/core/imageFilter.ts` |
| Estabilidad (reducer) | `src/core/stability.ts` |
| Coordinador de scans serializados | `src/core/scanCoordinator.ts` |
| Deduplicación por `assetId` | `src/core/dedupe.ts` |
| Paginación incremental newest-first | `src/core/incrementalScan.ts` |
| Logging con redacción | `src/core/logging.ts` |

### Cursores separados

- **`scanCursor`**: último registro de MediaStore **inspeccionado** (admitido o rechazado). Evita reprocesar.
- **`lastValidPhotoCursor`**: última fotografía **estable y decodificable**. Solo avanza tras estabilidad OK.

### Identidad de asset

- `assetId: string` = id original de la librería (obligatorio, no vacío).
- `mediaStoreNumericId?: number` solo si el id es un entero decimal válido.
- **Prohibido** usar `0` como fallback silencioso.

### Algoritmo incremental

Expo MediaLibrary con `sortBy: [[creationTime, false]]` → **newest first**.  
Se pagina hasta encontrar una fila `<= scanCursor`; solo esas candidatas nuevas se hidratan (`getAssetInfoAsync` + size).

---

## Integrado en app productiva

| Pieza | Archivo |
|-------|---------|
| Query incremental + listener | `src/native/mediaStore.ts` |
| Prober de estabilidad | `src/native/stabilityProber.ts` |
| Foreground Service (contrato + binding) | `src/native/foregroundService.ts` |
| Servicio Android real | `modules/capture-foreground-service/` |
| Config/env | `src/runtime/config/env.ts` |
| Bootstrap de servicios | `src/runtime/bootstrap/createAppServices.ts` |
| Cliente HTTP + refresh mutex | `src/services/api/apiClient.ts` |
| SecureStore tokens | `src/services/secureStorage/tokenStorage.ts` |
| Auth | `src/features/auth/authService.ts` |
| Inventarios | `src/features/inventories/inventoryService.ts` |
| Pasillos | `src/features/aisles/aisleService.ts` |
| SQLite + migraciones | `src/database/` |
| Captura persistente | `src/features/capture/captureService.ts` |
| UI Fase 1 | `App.tsx` |

### Flujo de sesión

1. **Login** → backend existente `/auth/login`; tokens en SecureStore.
2. **Inventarios** → `/api/v3/inventories/` paginado.
3. **Pasillos** → `/api/v3/inventories/{inventory_id}/aisles` paginado; no selecciona inactivos.
4. **Comenzar captura** → permisos → marcador inicial → sesión SQLite → cursores → FGS start → listener.
5. Eventos / **Escanear** → coordinador serial → detección → persistencia → `waiting_stability` → prober → `stable|unstable|undecodable`.
6. **Pausar/Reanudar** mantiene SQLite y cursores.
7. **Finalizar** → última pasada → FGS stop → estado `review`.
8. **Revisión** → excluir/reincorporar/reintentar/confirmar; no inicia uploads todavía.

### Foreground Service

Módulo local Expo (`capture-foreground-service`):

- `Service` con `foregroundServiceType="dataSync"`.
- Canal de notificación `dinamic_capture_fgs`.
- Métodos: `startService` / `updateNotification` / `stopService`.
- Requiere **Development Build** (`expo prebuild` + `installDebug`). No funciona en Expo Go.

Tras cambiar el módulo nativo:

```bash
cd mobile
npm run android
```

Eso es el flujo normal: **un solo comando** (`expo run:android`) hace prebuild si hace falta,
compila, instala en el dispositivo/emulador conectado y arranca Metro.

Si solo necesitás Metro (app ya instalada):

```bash
cd mobile
npm start
```

### Si aparece `EMFILE: too many open files`

En esta máquina `~/.local/state` suele estar owned por `root`, y Watchman no puede
crear su estado → Metro cae a FSEvents y explota. Los scripts `npm start` / `npm run android`
ya exportan `XDG_STATE_HOME=$HOME/.watchman-state` vía `scripts/with-metro-env.sh`.

Si igual falla fuera de npm:

```bash
export XDG_STATE_HOME="$HOME/.watchman-state"
mkdir -p "$XDG_STATE_HOME"
ulimit -n 65536
cd mobile && npm run android
```


---

## Configuración por entorno

Las variables viven en `mobile/.env` (ver `.env.example`) y se inyectan en **build time**
a través de `app.config.ts` → `extra`, y se leen en **runtime** con `expo-constants`
(`src/runtime/config/env.ts`). En React Native `process.env` NO recibe el `.env`, por eso la
app usa `Constants.expoConfig.extra` como fuente principal.

Reglas prácticas:

- Tras editar `.env`, reiniciar Metro con cache limpia: `npx expo start --dev-client --clear`.
  Si el manifest nativo quedó viejo, volver a instalar el dev build.
- **Emulador Android**: `DINAMIC_API_BASE_URL=http://10.0.2.2:8000`.
- **Dispositivo físico**: usar la IP LAN del host (ej. `http://192.168.1.50:8000`).
  `127.0.0.1`/`localhost` apunta al teléfono, no a tu Mac, y produce
  "Falta configurar DINAMIC_API_BASE_URL" o errores de red.
- **API key móvil**: si `DINAMIC_API_KEY` se empaqueta en la app, no es secreta.
  Puede extraerse del APK y no debe otorgar privilegios críticos ni reemplazar la
  autenticación del usuario. Si el backend depende de una API key global secreta,
  ese diseño no es seguro para clientes móviles.

## Recuperación local

- La sesión SQLite es la fuente de verdad para inventario/pasillo al recuperar.
- Una sesión que estaba `active` al cerrar la app se restaura como `paused` y requiere
  reanudación explícita para reiniciar FGS, listener y scan incremental.
- El dispositivo permite una sola sesión local abierta. Si se detectan múltiples sesiones
  antiguas, se conserva la más recientemente actualizada y las demás pasan a `failed`
  con política de reparación documentada; no se eliminan fotografías.

---

## Documentación Fase 3

| Doc | Contenido |
|-----|-----------|
| `docs/PHASE_3_AUDIT.md` | Auditoría pre-hardening |
| `docs/PHASE_3_IMPLEMENTATION.md` | Qué se entregó / gaps |
| `docs/PHASE_3_RUNBOOK.md` | Soporte operativo |
| `docs/PHASE_3_CHECKLIST.md` | Checklist productivo |
| `docs/PHASE_3_ROLLOUT.md` | Rollout / rollback |
| `docs/DEVICE_MATRIX.md` | Matriz de dispositivos |
| `docs/OEM_BACKGROUND.md` | Doze / OEM |
| `docs/SIGNING.md` | Firma APK/AAB |
| `docs/CRASH_REPORTING.md` | Crash reporting (pendiente DSN) |
| `docs/DEPENDENCY_AUDIT.md` | npm audit |

### Feature flags (build-time)

En `.env` / CI:

- `DINAMIC_FLAG_MOBILE_DATA=0` — no subir por datos móviles
- `DINAMIC_FLAG_HEIC_JPEG=0` — desactivar conversión HEIC
- `DINAMIC_FLAG_WORK_MANAGER=0` — desactivar schedule WorkManager
- `DINAMIC_FLAG_RECONCILE=0` — reconciliación avanzada off
- `DINAMIC_FLAG_BG_POLL=0` — no schedule job-monitor wake
- `DINAMIC_FLAG_AISLE_LOCK=1` — reservado (off por defecto)

### Diagnóstico en app

Menú **Diagnóstico**: health checks + **Exportar diagnóstico** (Share sheet, redactado).

---

## Validado mediante build / CI

```bash
cd mobile
export XDG_STATE_HOME="$HOME/.watchman-xdg-state"   # si Watchman falla por ~/.local/state root-owned
npm ci
npm run verify          # typecheck + lint + test:core + test
npx expo-doctor         # o: npm run doctor (Android-only: ignora check Xcode vs SDK 51)
npx expo prebuild -p android --clean
cd android && ./gradlew assembleDebug
cd android && ./gradlew installDebug
```

---

Resultado local Fase 1:

- `npm ci`: pasa (npm reporta vulnerabilidades transitivas existentes).
- `npm run verify`: pasa (39 tests).
- `npm run doctor` / `npx expo-doctor`: dependencias alineadas (`netinfo@11.3.1`). El check de Xcode local vs SDK 51 **no aplica** a este cliente Android-only; `npm run doctor` lo trata como OK. Un upgrade a SDK 55+ (Xcode 26) sería una migración aparte, no necesaria para builds Android.
- `npx expo prebuild -p android --clean`: pasa.
- `./gradlew assembleDebug`: pasa.
- `./gradlew installDebug`: pasa en `SM-G985F`, Android 13.

---

## Validado en dispositivo (obligatorio para aprobar Fase 1)

Plantilla: `docs/DEVICE_EVIDENCE.md`.

Checklist pendiente:

1. Abrir app · permiso solo fotos.
2. Marcar inicio · notificación FGS visible.
3. 20 fotos · pantalla bloqueada en parte del vuelo.
4. Agregar un `.mp4` · **no aparece** · métricas de fotos sin cambio por el video.
5. Sin duplicados · estables = 20 (si todas estabilizan).
6. Finalizar · notificación desaparece.

Mientras no exista evidencia firmada en `docs/DEVICE_EVIDENCE.md`, la Fase 1 permanece **parcialmente validada**.

---

## Limitaciones reales

- **Doze / OEM**: el SO puede pausar trabajo con batería restringida; FGS mitiga pero no garantiza detección eterna.
- **Uploads**: no incluidos por alcance; las fotos quedan listas localmente para la siguiente fase.
- **Conectividad**: login/listados requieren backend; captura local continúa offline una vez iniciada.
- **Navegación**: implementada por estado para evitar dependencias nuevas; puede migrarse a React Navigation sin tocar servicios.
- **Prueba física completa**: pendiente documentar 20 fotos + video + bloqueo de pantalla.
- **Acceso parcial (Android 14)**: solo el subconjunto concedido es visible.
- **Watchman en macOS**: si `~/.local/state` es root-owned, usar `XDG_STATE_HOME`.

---

## Decisión tecnológica

**Expo Development Build** permanece la recomendación tras cablear un FGS nativo real vía módulo local.  
Migrar a RN CLI solo si el rebuild nativo del módulo falla de forma irrecuperable en los Android objetivo.

---

## Scripts

## Scripts

| Script | Qué hace |
|--------|----------|
| `npm run android` | **Comando diario:** build + install + Metro en el dispositivo |
| `npm start` | Solo Metro (si la app ya está instalada) |
| `npm run typecheck` | tsc app completa |
| `npm run typecheck:core` | tsc sobre lógica pura |
| `npm run lint` | ESLint local |
| `npm run test:core` | Jest puro |
| `npm test` | Jest Fase 1+2 |
| `npm run verify` | typecheck + typecheck:core + lint + test:core + test |
| `npm run prebuild:android` | genera `android/` (solo si hace falta regenerar nativo) |

## Fase 2

Ver `docs/PHASE_2_IMPLEMENTATION.md` y `docs/PHASE_2_BACKEND_CONTRACTS.md`.

Flujo: captura → carga progresiva (cola SQLite) → revisión de uploads → `POST .../process` → polling de job → otro pasillo en paralelo.

No avanzar a hardening productivo general hasta cerrar evidencia E2E de dispositivo/staging.
