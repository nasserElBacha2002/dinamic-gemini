# 04 — Functional inventory

Estados: IMPLEMENTED | PARTIALLY_IMPLEMENTED | LEGACY | DEAD_CODE | UNKNOWN  
Evidencia de código (VERIFIED salvo nota).

## Inventarios — PARTIALLY_IMPLEMENTED

| Capacidad | Estado | Evidencia |
|-----------|--------|-----------|
| Create/list/get/patch | IMPLEMENTED | `api/routes/v3/inventories.py` |
| Soft-delete bulk | IMPLEMENTED | `soft_delete_inventories` + route |
| Status derivado de pasillos | IMPLEMENTED | `derive_status_from_aisles`, reconciler |
| Close/reopen explícito | **NO PRESENTE** | Sin rutas `/close`/`/reopen` |
| Undelete | NO PRESENTE | Solo soft-delete |

## Pasillos — PARTIALLY_IMPLEMENTED

| Capacidad | Estado | Evidencia |
|-----------|--------|-----------|
| Create online + supplier | IMPLEMENTED | `aisles.py` POST |
| Soft-deactivate | IMPLEMENTED | bloqueo si job activo |
| Create offline LOCAL_ONLY | IMPLEMENTED | `mobile/.../aisleService.ts` |
| Sync aisle como operación API | PARTIAL | Sin `CREATE_AISLE` offline op; sync vía ZIP package |

## Imágenes / uploads — IMPLEMENTED

Límites (`config/upload-limits`), HEIC→JPEG (`frames/normalize.py`, assets), storage local/S3/GCS (`storage_builders.py`), capture session spool, supplier reference images.

## Jobs — IMPLEMENTED

Start/cancel/retry/recover (`start_aisle_processing`, jobs routes), snapshots, SQL claim/leases, embedded vs on-demand vs dedicated worker.

## Reconocimiento — PARTIALLY_IMPLEMENTED

| Modo | Estado |
|------|--------|
| CODE_SCAN | IMPLEMENTED (default productivo) |
| Vision / EXTERNAL_PROVIDER fallback | IMPLEMENTED |
| GLOBAL_BATCH | IMPLEMENTED |
| AISLE_BATCH | LEGACY (aún usado como scope) |
| LEGACY_LLM / INTERNAL_OCR | LEGACY — bloqueados en starts nuevos (`legacy_processing_guard.py`) |

## Etiquetas / posiciones — IMPLEMENTED

ITEM/POSITION + fuentes DINAMIC/SUPPLIER; D1 checksum Mod-36; HMAC posiciones (`positioning_label_signing.py`); perfiles extracción supplier versionados.

## TXT / CSV / ZIP — IMPLEMENTED

`dinamic_scanner_txt_imports`, `local_csv_imports`, `local_inventory_packages`. Filename TXT rechaza `..` `/` `\` (`aisle_code_from_txt_filename`).

## Mobile offline — IMPLEMENTED (flag-gated)

SQLite (`dinamic_mobile.db`), colas offline ops, export ZIP, sync autoritativo, SecureStore tokens. Limitación: sync basado en timers mientras app abierta (comentario en código).

## Frontend — PARTIALLY_IMPLEMENTED

Inventarios, pasillos, posiciones/review en aisle, clients/suppliers, analytics, AI admin. Rutas legacy redirect: review-queue, metrics, observability, ingestion sessions, aisle locations (DEAD_CODE de ruta / páginas huérfanas).

## Auth — IMPLEMENTED

Login/refresh/logout JWT HS256; admin env + opcional Jairo; roles `platform_admin` / `company_admin`. Sin modelo multi-usuario DB.

## Analytics / exports — IMPLEMENTED

Analytics API, inventory metrics, CSV/ZIP exports, aisle export/benchmark.

## Inconsistencias clave (VERIFIED)

1. No API close/reopen inventario.
2. Offline aisle ≠ create API; depende de ZIP.
3. Review queue FE removida; APIs backend review viven.
4. Dual queues mobile pueden conflictuar si flags solapan.
