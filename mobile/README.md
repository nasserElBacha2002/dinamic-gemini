# Dinamic Inventory — App móvil de captura (Android)

Cliente móvil **solo fotografías** para acelerar la carga de imágenes de inventario tomadas
con dron. Usa **exclusivamente el backend existente** (`/auth` + `/api/v3`). No crea backend,
base de datos, worker ni flujo de procesamiento paralelo.

> Estado: **Fase 0 — Spike técnico Android (corrección post-review)**.  
> **Fase 0 = parcialmente validada** hasta completar la prueba física documentada (§ Dispositivo).

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

## Integrado en app (dispositivo)

| Pieza | Archivo |
|-------|---------|
| Query incremental + listener | `src/native/mediaStore.ts` |
| Prober de estabilidad | `src/native/stabilityProber.ts` |
| Foreground Service (contrato + binding) | `src/native/foregroundService.ts` |
| Servicio Android real | `modules/capture-foreground-service/` |
| UI del spike | `App.tsx` |

### Flujo de sesión

1. **Marcar inicio** → permisos → marcador → reset cursores → FGS start → listener.
2. Eventos / **Escanear** → coordinador serial → detección → `waiting_stability` → prober → `stable|unstable|undecodable`.
3. **Finalizar captura** → abort estabilidad → quita listener → FGS stop → resumen.

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

## Validado mediante build / CI liviano

```bash
cd mobile
export XDG_STATE_HOME="$HOME/.watchman-xdg-state"   # si Watchman falla por ~/.local/state root-owned
npm ci
npm run verify          # typecheck:core + lint + test:core
npx expo-doctor         # cuando el toolchain Expo esté instalado
npx expo prebuild -p android --clean
cd android && ./gradlew assembleDebug
```

---

## Validado en dispositivo (obligatorio para cerrar Fase 0)

Plantilla: `docs/DEVICE_EVIDENCE.md`.

Checklist:

1. Abrir app · permiso solo fotos.
2. Marcar inicio · notificación FGS visible.
3. 20 fotos · pantalla bloqueada en parte del vuelo.
4. Agregar un `.mp4` · **no aparece** · métricas de fotos sin cambio por el video.
5. Sin duplicados · estables = 20 (si todas estabilizan).
6. Finalizar · notificación desaparece.

Mientras no exista evidencia firmada en `docs/DEVICE_EVIDENCE.md`, la Fase 0 permanece **parcialmente validada**.

---

## Limitaciones reales

- **Doze / OEM**: el SO puede pausar trabajo con batería restringida; FGS mitiga pero no garantiza detección eterna.
- **Cierre forzado / reinicio**: el spike no recupera sesión (Fase 1+ con SQLite).
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
| `npm run typecheck:core` | tsc sobre lógica pura |
| `npm run lint` | ESLint local |
| `npm run test:core` | Jest puro |
| `npm run verify` | typecheck:core + lint + test:core |
| `npm run prebuild:android` | genera `android/` |
| `npm start` | Metro dev client |

No avanzar a Fase 1 hasta cerrar la evidencia de dispositivo.
