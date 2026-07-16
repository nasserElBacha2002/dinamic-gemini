# Dinamic Inventory — App móvil de captura (Android)

Cliente móvil **solo fotografías** para acelerar la carga de imágenes de inventario tomadas
con dron. Usa **exclusivamente el backend existente** (`/auth` + `/api/v3`). No crea backend,
base de datos, worker ni flujo de procesamiento paralelo.

> Estado: **Fase 1 — base funcional y captura local completa**.  
> **Fase 1 = parcialmente validada**: typecheck/lint/tests/prebuild/build/install pasan; queda pendiente la prueba física completa de 20 fotografías + video + pantalla bloqueada documentada en `docs/DEVICE_EVIDENCE.md`.

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
| Config/env | `src/app/config/env.ts` |
| Bootstrap de servicios | `src/app/bootstrap/createAppServices.ts` |
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
npx expo prebuild -p android --clean
cd android && ./gradlew installDebug
```

---

## Configuración por entorno

Las variables viven en `mobile/.env` (ver `.env.example`) y se inyectan en **build time**
a través de `app.config.ts` → `extra`, y se leen en **runtime** con `expo-constants`
(`src/app/config/env.ts`). En React Native `process.env` NO recibe el `.env`, por eso la
app usa `Constants.expoConfig.extra` como fuente principal.

Reglas prácticas:

- Tras editar `.env`, reiniciar Metro con cache limpia: `npx expo start --dev-client --clear`.
  Si el manifest nativo quedó viejo, volver a instalar el dev build.
- **Emulador Android**: `DINAMIC_API_BASE_URL=http://10.0.2.2:8000`.
- **Dispositivo físico**: usar la IP LAN del host (ej. `http://192.168.1.50:8000`).
  `127.0.0.1`/`localhost` apunta al teléfono, no a tu Mac, y produce
  "Falta configurar DINAMIC_API_BASE_URL" o errores de red.

---

## Validado mediante build / CI

```bash
cd mobile
export XDG_STATE_HOME="$HOME/.watchman-xdg-state"   # si Watchman falla por ~/.local/state root-owned
npm ci
npm run verify          # typecheck + lint + test:core + test
npx expo-doctor         # cuando el toolchain Expo esté instalado
npx expo prebuild -p android --clean
cd android && ./gradlew assembleDebug
cd android && ./gradlew installDebug
```

---

Resultado local Fase 1:

- `npm ci`: pasa (npm reporta vulnerabilidades transitivas existentes).
- `npm run verify`: pasa (39 tests).
- `npx expo-doctor`: 16/17; falla solo check de Xcode local incompatible con SDK 51, no bloquea Android.
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

| Script | Qué hace |
|--------|----------|
| `npm run typecheck` | tsc app completa |
| `npm run typecheck:core` | tsc sobre lógica pura |
| `npm run lint` | ESLint local |
| `npm run test:core` | Jest puro |
| `npm test` | Jest Fase 1 |
| `npm run verify` | typecheck + typecheck:core + lint + test:core + test |
| `npm run prebuild:android` | genera `android/` |
| `npm start` | Metro dev client |

No avanzar a uploads/procesamiento hasta cerrar la evidencia de dispositivo de Fase 1.
