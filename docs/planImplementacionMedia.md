# Fase 1 — Dominio y persistencia

## Ticket 1 — Esquema: `capture_sessions`


| Campo                       | Contenido                                                                                                                                                                                                                                                                                                                                                           |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | Migración SQL: tabla `capture_sessions` (inventario + pasillo + estado + auditoría)                                                                                                                                                                                                                                                                                 |
| **Objective**               | Persistir sesiones de captura por pasillo sin tocar `source_assets`, con trazabilidad operativa y estados explícitos.                                                                                                                                                                                                                                               |
| **Technical scope**         | Nueva tabla en `src/database/` (schema + migración aplicable): `inventory_id`, `aisle_id` (FKs), `status`, `created_at` / `updated_at`, `opened_at` / `closed_at` (o equivalentes), columnas de auditoría mínimas (p. ej. `created_by` si existe patrón en el repo), índices por `(inventory_id, aisle_id)`, `(status, updated_at)`. Sin cambios a `source_assets`. |
| **Dependencies**            | Ninguna (salvo convenciones existentes de migraciones y tenancy).                                                                                                                                                                                                                                                                                                   |
| **Acceptance criteria**     | Migración aplica sin romper esquema actual; cada fila asocia inequívocamente `inventory_id` + `aisle_id`; `source_assets` intacto; índices soportan listados por inventario/pasillo/estado.                                                                                                                                                                         |
| **Risks**                   | Estados sin enum en DB → inconsistencia; mitigar con CHECK constraint o tabla de catálogo + convención de aplicación.                                                                                                                                                                                                                                               |
| **Suggested test coverage** | Test de migración (smoke: tablas/columnas/FK), test de repositorio stub si aplica en el harness del proyecto.                                                                                                                                                                                                                                                       |


---

## Ticket 2 — Esquema: `capture_session_items` + idempotencia de confirmación


| Campo                       | Contenido                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | Migración SQL: ítems de staging + vínculo opcional a `SourceAsset` + idempotencia                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| **Objective**               | Representar archivos en staging antes de materializar `SourceAsset`, con reintentos, errores por ítem y confirmación idempotente.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| **Technical scope**         | Tabla `capture_session_items`: `session_id` FK, `staging_storage_key`, `content_hash` (o hash + algoritmo), `effective_capture_time`, `time_source`, `time_confidence` (o enum numérico), `import_status`, `assignment_status`, `linked_source_asset_id` (nullable FK a `source_assets`), metadatos de error (`last_error_code`, `last_error_detail` truncado), `updated_at`. Tabla o restricción única para idempotencia: `**(session_id, idempotency_key)`** en intentos de confirmación **o** única por `**(session_id, content_hash)`** según diseño elegido (documentar en ADR corto en PR). Índices por sesión y por `linked_source_asset_id`. |
| **Dependencies**            | Ticket 1 (sesión padre).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| **Acceptance criteria**     | Ítem puede existir sin `SourceAsset`; confirmado enlaza `linked_source_asset_id`; esquema permite reintentos y registro de fallo por ítem; unicidad evita doble materialización del mismo ítem/hash.                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **Risks**                   | Doble fuente de verdad si se duplica “batch” aparte de sesión → **mitigar unificando con Ticket 1** (ver nota global).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| **Suggested test coverage** | Migración; tests de unicidad (insert duplicado falla o no-op según política); FK cascade/restrict documentado.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |


---

## Ticket 3 — Dominio: entidades y enums


| Campo                       | Contenido                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | Dominio: `CaptureSession`, `CaptureSessionItem` y enums de estado                                                                                                                                                                                                                                                                                                                                                                                                         |
| **Objective**               | Modelar explícitamente estados y orígenes de tiempo para validar transiciones sin acoplar a HTTP.                                                                                                                                                                                                                                                                                                                                                                         |
| **Technical scope**         | Entidades en `src/domain/`: sesión, ítem; enums: estado de sesión (alineado al blueprint: draft, importing, ready_for_review, assignment_proposed, confirming, confirmed, cancelled, failed), importación del ítem, `TimeSource` (exif, file_mtime, fallback_clock), resultado de asignación (p. ej. proposed, conflict, unassigned). Métodos o invariantes mínimos que rechacen transiciones inválidas (o delegación clara al use case con precondiciones documentadas). |
| **Dependencies**            | Tickets 1–2 como contrato de persistencia (nombres alineados).                                                                                                                                                                                                                                                                                                                                                                                                            |
| **Acceptance criteria**     | Estados y transiciones documentados; dominio sin imports de FastAPI/schemas.                                                                                                                                                                                                                                                                                                                                                                                              |
| **Risks**                   | Enum desalineado con DB → tabla de mapeo en infra + tests de round-trip.                                                                                                                                                                                                                                                                                                                                                                                                  |
| **Suggested test coverage** | Tests unitarios de transiciones prohibidas / precondiciones.                                                                                                                                                                                                                                                                                                                                                                                                              |


---

## Ticket 4 — Puertos: repositorios de sesión, ítems e idempotencia


| Campo                       | Contenido                                                                                                                                                                                                                                                                    |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | Puertos: `CaptureSessionRepository`, `CaptureSessionItemRepository`, persistencia idempotente                                                                                                                                                                                |
| **Objective**               | Desacoplar casos de uso de SQL; consultas por inventario, pasillo, estado y sesión.                                                                                                                                                                                          |
| **Technical scope**         | Interfaces en `application/ports` (o convención del repo): save/get/list con filtros, updates optimistas si aplica (`row_version` o `updated_at`), operaciones para registrar **outcome de confirmación idempotente** (guardar clave + resultado serializado o ids creados). |
| **Dependencies**            | Ticket 3 (tipos de dominio).                                                                                                                                                                                                                                                 |
| **Acceptance criteria**     | Ningún use case futuro necesita SQL directo; contratos cubren listado operativo y carga por id con scope inventario/pasillo.                                                                                                                                                 |
| **Risks**                   | Consultas N+1 en listados → proyección DTO en infra o paginación obligatoria.                                                                                                                                                                                                |
| **Suggested test coverage** | Tests de puerto con fake/in-memory según patrón del proyecto; tests de integración SQL opcionales si existen.                                                                                                                                                                |


---

# Fase 2 — Gate de procesamiento y spine único

## Ticket 5 — Preflight: `StartAisleProcessing` sin assets


| Campo                       | Contenido                                                                                                                                                                                  |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Title**                   | `StartAisleProcessingUseCase`: rechazo 4xx si `list_by_aisle` vacío                                                                                                                        |
| **Objective**               | El executor no debe ser la primera línea de defensa para “pasillo sin `SourceAsset`”.                                                                                                      |
| **Technical scope**         | Antes de enqueue/launch: `SourceAssetRepository.list_by_aisle(aisle_id)`; si vacío → error de negocio estable (código estable para cliente) mapeado a **4xx** en capa API; logging mínimo. |
| **Dependencies**            | Ninguna funcional nueva de sesiones (puede entregarse en paralelo al dominio si el puerto ya existe).                                                                                      |
| **Acceptance criteria**     | No se crea/encola job si no hay assets; respuesta consistente v3; regresión cubierta.                                                                                                      |
| **Risks**                   | Race: assets borrados entre preflight y worker → mantener defensa en profundidad en executor sin cambiar contrato UX.                                                                      |
| **Suggested test coverage** | Pytest: mock repo vacío → assert no launch; repo con 1 asset → comportamiento actual preservado.                                                                                           |


---

## Ticket 6 — `AisleSourceAssetMaterializer` (spine único)


| Campo                       | Contenido                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | Servicio de aplicación: materialización única hacia `SourceAsset`                                                                                                                                                                                                                                                                                                                                                                                           |
| **Objective**               | Centralizar storage + construcción de entidad + persistencia + metadata + side effects compartidos.                                                                                                                                                                                                                                                                                                                                                         |
| **Technical scope**         | Nuevo servicio en `application` invocado por flujos autorizados: escritura en destino final (misma semántica que upload actual), construcción `SourceAsset`, `SourceAssetRepository.save`, `metadata_json` opcional, invocación compartida de `**mark_assets_uploaded`** y `**InventoryStatusReconciler.reconcile**` vía helpers ya existentes o extraídos sin duplicar reglas. **Ningún** otro flujo debe llamar storage+save directamente para este caso. |
| **Dependencies**            | Revisión de `UploadAisleAssetsUseCase` y repos existentes (lectura).                                                                                                                                                                                                                                                                                                                                                                                        |
| **Acceptance criteria**     | Un solo lugar autorizado para crear `SourceAsset` desde bytes/metadata de negocio; side effects alineados con upload manual.                                                                                                                                                                                                                                                                                                                                |
| **Risks**                   | No atomicidad histórica → documentar compensación y estados de ítem/sesión; límites de tamaño y timeouts en config.                                                                                                                                                                                                                                                                                                                                         |
| **Suggested test coverage** | Unit: materializer con fakes de storage/repo; assert orden de side effects si es relevante.                                                                                                                                                                                                                                                                                                                                                                 |


---

## Ticket 7 — Refactor: `UploadAisleAssetsUseCase` → materializer


| Campo                       | Contenido                                                                                                                 |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | Refactor: upload manual por pasillo usa el materializer sin cambio de comportamiento                                      |
| **Objective**               | Eliminar duplicación futura; conservar contrato actual.                                                                   |
| **Technical scope**         | Adaptar use case para delegar en materializer; preservar validaciones, MIME, límites, respuestas API; tests de regresión. |
| **Dependencies**            | Ticket 6.                                                                                                                 |
| **Acceptance criteria**     | Comportamiento observable del upload manual equivalente; materialización centralizada.                                    |
| **Risks**                   | Diferencias sutiles en paths/metadata → comparar fixtures antes/después.                                                  |
| **Suggested test coverage** | Pytest existentes del use case actualizados; prueba de integración si hay.                                                |


---

# Fase 3 — Sesiones de captura (API de producto)

## Ticket 8 — Crear sesión de captura


| Campo                       | Contenido                                                                                                                                                                                                                                                                                                                    |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | Use case + endpoint v3: crear `CaptureSession` (scope inventario/pasillo)                                                                                                                                                                                                                                                    |
| **Objective**               | Abrir una sesión trazable con estado inicial consistente y política de concurrencia.                                                                                                                                                                                                                                         |
| **Technical scope**         | Use case: validar que el pasillo pertenece al inventario (mismo patrón que rutas de assets), persistir sesión, timestamps server-side (`Clock`); política configurable: **máx. una sesión activa no terminal por (inventory_id, aisle_id)** o explícitamente permitir múltiples con reglas (definir en config y documentar). |
| **Dependencies**            | Tickets 1, 3, 4; infra repo SQL.                                                                                                                                                                                                                                                                                             |
| **Acceptance criteria**     | Sesión válida creada; imposible asociar pasillo fuera de inventario; respuesta incluye id, estado, timestamps.                                                                                                                                                                                                               |
| **Risks**                   | Sesiones concurrentes sin política → conflictos de confirmación; mitigar con UNIQUE filtrado o lock de aplicación.                                                                                                                                                                                                           |
| **Suggested test coverage** | API + use case: 403/404 scope; doble creación según política.                                                                                                                                                                                                                                                                |


---

## Ticket 9 — Cerrar sesión de captura


| Campo                       | Contenido                                                                                                                                                     |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | Use case + endpoint v3: cerrar sesión (`closed_at`, transición de estado)                                                                                     |
| **Objective**               | Cierre idempotente o error controlado según estado.                                                                                                           |
| **Technical scope**         | Transiciones permitidas (p. ej. no cerrar `confirmed` como “cerrar” si es otro verbo); `closed_at`; errores 409 para estados inválidos; sin borrar auditoría. |
| **Dependencies**            | Ticket 8.                                                                                                                                                     |
| **Acceptance criteria**     | Sesión abierta cierra; re-cierre devuelve error estable; estado final persistido.                                                                             |
| **Risks**                   | Cerrar mientras `confirming` → definir semántica (rechazar o esperar); documentar.                                                                            |
| **Suggested test coverage** | Matriz estado × acción.                                                                                                                                       |


---

## Ticket 10 — Listar / consultar sesiones


| Campo                       | Contenido                                                                                          |
| --------------------------- | -------------------------------------------------------------------------------------------------- |
| **Title**                   | Use case + endpoint v3: listado y detalle de sesiones con filtros                                  |
| **Objective**               | Soporte UI operativa: recientes, por pasillo, por estado, por rango de fechas.                     |
| **Technical scope**         | Queries en puerto/repo; DTO de respuesta estable para UI; paginación; orden por `updated_at` desc. |
| **Dependencies**            | Tickets 4, 8.                                                                                      |
| **Acceptance criteria**     | Filtros funcionan; la UI puede distinguir abierta/cerrada/confirmada/fallida vía `status`.         |
| **Risks**                   | Payloads grandes → proyección ligera en listado, detalle aparte.                                   |
| **Suggested test coverage** | Repo/integration: filtros; API: contrato JSON.                                                     |


---

# Fase 4 — Staging e importación

## Ticket 11 — Crear contenedor de importación (batch)


| Campo                       | Contenido                                                                                                                                                                                                                                                                                                              |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | **Ajuste de alcance:** contenedor de importación = `CaptureSession` (sin segunda tabla)                                                                                                                                                                                                                                |
| **Objective**               | Evitar duplicar “sesión de captura” vs “batch de importación”.                                                                                                                                                                                                                                                         |
| **Technical scope**         | Si ya existe `CaptureSession`, implementar **estado inicial** y transición `**draft` → `importing`** al iniciar importación, o crear sesión vacía lista para ítems (sin segunda entidad). Si el equipo prefiere tabla `import_batches`, debe FK a `capture_sessions` y quedar **1:1**; no recomendado en el blueprint. |
| **Dependencies**            | Ticket 8 (preferido: fusionar criterios de “sesión vacía” en creación).                                                                                                                                                                                                                                                |
| **Acceptance criteria**     | Existe un contenedor persistido antes del primer upload; **no** hay `SourceAsset` aún.                                                                                                                                                                                                                                 |
| **Risks**                   | Doble modelo de sesión → deuda y bugs de estado; **evitar**.                                                                                                                                                                                                                                                           |
| **Suggested test coverage** | Estado inicial + transición al primer upload simulado.                                                                                                                                                                                                                                                                 |


---

## Ticket 12 — Upload a staging + ítems


| Campo                       | Contenido                                                                                                                                                                                                                                                 |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | Use case + endpoint: subir archivo a staging y persistir `CaptureSessionItem`                                                                                                                                                                             |
| **Objective**               | Blob en staging + fila de ítem con hash y estados de importación.                                                                                                                                                                                         |
| **Technical scope**         | Storage de staging (prefijo/config), `staging_storage_key`, cálculo `content_hash`, metadatos básicos, `import_status` imported/failed, errores por ítem; límites configurables (tamaño, nº archivos, concurrencia). **No** usar materializer final aquí. |
| **Dependencies**            | Tickets 2, 4, 11 (o 8 unificado), infra storage.                                                                                                                                                                                                          |
| **Acceptance criteria**     | Archivo en staging; ítem persistido sin `SourceAsset`; fallos registrados por ítem.                                                                                                                                                                       |
| **Risks**                   | Objetos huérfanos si DB falla post-upload → transacción o compensación + Ticket 13/27.                                                                                                                                                                    |
| **Suggested test coverage** | Unit fallos de storage; API multipart; ítem en DB.                                                                                                                                                                                                        |


---

## Ticket 13 — Cancelar / descartar + reglas de cleanup


| Campo                       | Contenido                                                                                                                                                                                                                                                                         |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | Cancelación explícita de sesión y política de borrado de staging                                                                                                                                                                                                                  |
| **Objective**               | Sesión cancelada no continúa; blobs huérfanos eventualmente limpiados sin tocar materializados.                                                                                                                                                                                   |
| **Technical scope**         | Use case cancel: transición a `cancelled`, bloqueo de nuevas importaciones/confirm; borrado staging solo para ítems **sin** `linked_source_asset_id`; preservar filas de auditoría o soft-delete según política; sesiones atascadas → `failed` + mensaje (enlazar con Ticket 27). |
| **Dependencies**            | Tickets 8, 12.                                                                                                                                                                                                                                                                    |
| **Acceptance criteria**     | Cancelación efectiva; no se borran evidencias de assets confirmados; auditoría mínima conservada.                                                                                                                                                                                 |
| **Risks**                   | Borrado agresivo vs soporte → TTL + job de GC separado.                                                                                                                                                                                                                           |
| **Suggested test coverage** | Casos: ítem confirmado vs no confirmado; cancel en cada estado permitido.                                                                                                                                                                                                         |


---

# Fase 5 — Tiempo y preview de asignación

## Ticket 14 — Extracción de tiempo (EXIF + fallbacks)


| Campo                       | Contenido                                                                                                                                                                      |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Title**                   | Servicio: derivar `effective_capture_time`, `time_source`, `time_confidence`                                                                                                   |
| **Objective**               | Todo ítem tiene tiempo efectivo determinista y auditable.                                                                                                                      |
| **Technical scope**         | Job asíncrono o paso post-upload: parse EXIF; fallback `file_mtime`; fallback `Clock.now()`; persistencia en ítem; normalización a UTC; errores de parse → fallback explícito. |
| **Dependencies**            | Ticket 12 (ítem existente).                                                                                                                                                    |
| **Acceptance criteria**     | Siempre hay `effective_capture_time`; UI puede mostrar origen; sin EXIF queda marcado como no-EXIF.                                                                            |
| **Risks**                   | Coste CPU en request → mover a worker/col queue interna.                                                                                                                       |
| **Suggested test coverage** | Fixtures EXIF mínimos; archivo sin EXIF; reloj inyectado.                                                                                                                      |


---

## Ticket 15 — `clock_offset_seconds` a nivel sesión


| Campo                       | Contenido                                                                                                                                                                                                                      |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Title**                   | Persistir y aplicar offset de sesión en preview (y en confirmación)                                                                                                                                                            |
| **Objective**               | Corregir drift de cámara/dron de forma determinista y auditada.                                                                                                                                                                |
| **Technical scope**         | Columna en `capture_sessions`, validación de rango configurable, aplicación: `adjusted_time = effective_capture_time + offset` solo en motor de preview/confirm (documentar); audit log o `updated_by`/`updated_at` en sesión. |
| **Dependencies**            | Tickets 1, 10, 16.                                                                                                                                                                                                             |
| **Acceptance criteria**     | Cambiar offset altera preview de forma reproducible; queda auditado; confirm usa el mismo ajuste.                                                                                                                              |
| **Risks**                   | Offset cambiado tras preview antiguo → exigir re-preview o versionar snapshot de asignación.                                                                                                                                   |
| **Suggested test coverage** | Casos borde de offset extremo (rechazar si fuera de rango).                                                                                                                                                                    |


---

## Ticket 16 — Motor de preview de asignación


| Campo                       | Contenido                                                                                                                                                                                                                                            |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | Use case: preview determinístico sin crear `SourceAsset`                                                                                                                                                                                             |
| **Objective**               | Proponer asignación por timestamp con conflictos y fuera de rango explícitos.                                                                                                                                                                        |
| **Technical scope**         | Lectura de posiciones/slots vigentes del dominio existente (puertos ya definidos); reglas deterministas; persistencia de **resultado de preview** en ítem o tabla derivada (sin FK a assets); estados `assignment_proposed` / conflict / unassigned. |
| **Dependencies**            | Tickets 14–15; puerto de lectura de posiciones/aisle.                                                                                                                                                                                                |
| **Acceptance criteria**     | Match único → proposed; ambiguo → conflict; fuera de ventana → unassigned; **ningún** `SourceAsset` creado.                                                                                                                                          |
| **Risks**                   | Reglas de negocio mal especificadas → ADR + ejemplos en tests.                                                                                                                                                                                       |
| **Suggested test coverage** | Tabla de casos: 0/1/N candidatos; empates; límites de tiempo.                                                                                                                                                                                        |


---

# Fase 6 — Confirmación idempotente y materialización

## Ticket 17 — Contrato de idempotencia de confirmación


| Campo                       | Contenido                                                                                                                                                                             |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | Persistencia y API: `idempotency_key` en `ConfirmCaptureSession`                                                                                                                      |
| **Objective**               | Retries y doble clic no duplican assets.                                                                                                                                              |
| **Technical scope**         | Tabla o registro único `(session_id, idempotency_key)` con **payload de resultado** (ids creados) para respuesta idéntica; política HTTP (p. ej. 200 repetido con mismo body lógico). |
| **Dependencies**            | Ticket 2, 4.                                                                                                                                                                          |
| **Acceptance criteria**     | Misma key → mismo outcome; ítem ya con `linked_source_asset_id` → no-op para ese ítem.                                                                                                |
| **Risks**                   | Confirm parcial + retry → combinar con estado `confirming` y contadores (Ticket 18).                                                                                                  |
| **Suggested test coverage** | Doble POST concurrente; misma key secuencial; keys distintas en mismo estado.                                                                                                         |


---

## Ticket 18 — Confirmar sesión vía materializer


| Campo                       | Contenido                                                                                                                                                                                                                                                                                                                                                       |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | `ConfirmCaptureSessionUseCase`: staging → `SourceAsset` + outcomes por ítem                                                                                                                                                                                                                                                                                     |
| **Objective**               | Materialización final solo por spine compartido; sesión refleja resultado.                                                                                                                                                                                                                                                                                      |
| **Technical scope**         | Selección de ítems confirmables; validación de asignación; lectura staging; llamada a `**AisleSourceAssetMaterializer`** por ítem; `linked_source_asset_id`; errores por ítem sin duplicación silenciosa; transición sesión `confirming` → `confirmed` solo si criterio global cumplido (definir: todos los seleccionados OK o permitir parcial con subestado). |
| **Dependencies**            | Tickets 6, 12, 16, 17.                                                                                                                                                                                                                                                                                                                                          |
| **Acceptance criteria**     | Ítems confirmados existen como `SourceAsset`; errores visibles; sin duplicados; usa materializer.                                                                                                                                                                                                                                                               |
| **Risks**                   | Parcial + reintento → idempotencia por ítem/hash obligatoria.                                                                                                                                                                                                                                                                                                   |
| **Suggested test coverage** | Mix éxito/fallo; retry tras fallo; assert counts en DB.                                                                                                                                                                                                                                                                                                         |


---

## Ticket 19 — Side effects de pasillo e inventario en confirmación


| Campo                       | Contenido                                                                                                                                                                                                                               |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | Alinear side effects post-confirm con upload manual                                                                                                                                                                                     |
| **Objective**               | Misma semántica de `mark_assets_uploaded` y reconciliación que el flujo actual.                                                                                                                                                         |
| **Technical scope**         | Verificar que el materializer ya centraliza esto (Ticket 6); si hace falta, **deduplicar** llamadas (p. ej. reconciliar una vez por operación batch o por política existente); documentar decisión para no doble-reconciliar en bucles. |
| **Dependencies**            | Tickets 6, 18, 7.                                                                                                                                                                                                                       |
| **Acceptance criteria**     | Tras confirm batch, pasillo e inventario coherentes con upload incremental equivalente; sin divergencias documentadas.                                                                                                                  |
| **Risks**                   | Reconciliación N veces en N ítems → performance; mitigar batch hook si el dominio lo permite.                                                                                                                                           |
| **Suggested test coverage** | Integración: estado aisle/inventory tras confirm de N ítems vs N uploads manuales simulados.                                                                                                                                            |


---

# Fase 7 — API v3 (agrupación de rutas)

## Ticket 20 — Endpoints v3: CRUD sesión (crear, cerrar, listar, detalle)


| Campo                       | Contenido                                                                                                                                  |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| **Title**                   | Rutas v3: sesiones de captura con auth y scope                                                                                             |
| **Objective**               | Superficie HTTP consistente con v3 existente.                                                                                              |
| **Technical scope**         | Schemas en `src/api/schemas/`; rutas bajo `/api/v3/`; dependencias de auth; errores 404/409/422 alineados; sin lógica de negocio en rutas. |
| **Dependencies**            | Tickets 8–10.                                                                                                                              |
| **Acceptance criteria**     | Convenciones del sistema respetadas; multi-tenant preservado.                                                                              |
| **Risks**                   | Filtrado insuficiente → pruebas de escalamiento horizontal de IDs.                                                                         |
| **Suggested test coverage** | API tests: auth, scope, OpenAPI si aplica.                                                                                                 |


---

## Ticket 21 — Endpoints v3: import, preview, confirm, cancel, detalle ítems


| Campo                       | Contenido                                                                                                                                                                                         |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | Rutas v3: ciclo completo staging → preview → confirm                                                                                                                                              |
| **Objective**               | Una línea clara de endpoints sin solapamientos ambiguos con upload manual.                                                                                                                        |
| **Technical scope**         | Upload staging (multipart/chunked según estándar del repo), preview, confirm con `Idempotency-Key` header o body (decidir y documentar), cancel, GET detalle con agregados de conteos por estado. |
| **Dependencies**            | Tickets 12–19, 20.                                                                                                                                                                                |
| **Acceptance criteria**     | Ciclo E2E vía API; no rompe endpoints existentes; contratos versionados si hay cambios breaking (evitar).                                                                                         |
| **Risks**                   | Timeouts en uploads grandes → async + polling de sesión si es necesario.                                                                                                                          |
| **Suggested test coverage** | E2E API con almacenamiento fake; límites de tamaño.                                                                                                                                               |


---

# Fase 8 — Frontend MVP

## Ticket 22 — Entry point desde `InventoryDetail`


| Campo                       | Contenido                                                               |
| --------------------------- | ----------------------------------------------------------------------- |
| **Title**                   | UI: acceso a “Captura de campo” desde detalle de inventario             |
| **Objective**               | Descubribilidad sin reemplazar upload manual por pasillo.               |
| **Technical scope**         | Botón/link en página existente; ruta nueva; permisos alineados con API. |
| **Dependencies**            | Ticket 20 mínimo (o mocks hasta API lista).                             |
| **Acceptance criteria**     | Navegación clara; upload manual sigue accesible.                        |
| **Risks**                   | Feature flag si release incremental.                                    |
| **Suggested test coverage** | Vitest de ruta/botón; smoke E2E opcional.                               |


---

## Ticket 23 — UI: lista y ciclo de vida de sesión


| Campo                       | Contenido                                                                     |
| --------------------------- | ----------------------------------------------------------------------------- |
| **Title**                   | UI: abrir/cerrar/cancelar sesión y ver estado global                          |
| **Objective**               | Operador entiende en qué estado está la sesión.                               |
| **Technical scope**         | Tabla o panel; chips de estado alineados al backend; manejo de errores; i18n. |
| **Dependencies**            | Tickets 20–21.                                                                |
| **Acceptance criteria**     | Estados distinguibles; errores visibles.                                      |
| **Risks**                   | Desalineación enum UI/backend → tipos generados o constantes compartidas.     |
| **Suggested test coverage** | Tests de render por estado mock.                                              |


---

## Ticket 24 — UI: wizard importación + revisión + confirmación


| Campo                       | Contenido                                                                                                                                                          |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Title**                   | UI: wizard (upload → tiempos → offset → preview → conflictos → confirmar)                                                                                          |
| **Objective**               | Flujo usable con fallos parciales y reintentos.                                                                                                                    |
| **Technical scope**         | Tabla de ítems, badges `time_source`, badges de asignación, acciones retry/cancel según API; deshabilitar confirm si hay conflictos sin resolver (según política). |
| **Dependencies**            | Ticket 21.                                                                                                                                                         |
| **Acceptance criteria**     | Operador entiende cada archivo; revisión antes de confirmar; idempotency key generada/reutilizada según diseño (p. ej. una por intento de confirm).                |
| **Risks**                   | UX de archivos masivos → progreso/cola.                                                                                                                            |
| **Suggested test coverage** | Vitest de componentes críticos; prueba de integración API mock.                                                                                                    |


---

## Ticket 25 — UI: “Start processing” alineado al gate


| Campo                       | Contenido                                                                                                                                      |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | UI: deshabilitar procesado si no hay `SourceAsset` / sesión no confirmada                                                                      |
| **Objective**               | Paridad con Ticket 5; menos errores tardíos.                                                                                                   |
| **Technical scope**         | Condicionar botón a conteo de assets del pasillo (endpoint existente o nuevo agregado ligero); mensaje claro; tras confirm, refrescar conteos. |
| **Dependencies**            | Tickets 5, 24 (o datos de aisle existentes).                                                                                                   |
| **Acceptance criteria**     | UI no contradice backend; mensaje explica causa.                                                                                               |
| **Risks**                   | Datos obsoletos → invalidación tras mutaciones (React Query keys).                                                                             |
| **Suggested test coverage** | Tests de habilitación del botón según fixtures.                                                                                                |


---

# Fase 9 — Observabilidad, hardening, QA integral

## Ticket 26 — Métricas y logging


| Campo                       | Contenido                                                                                                                                                             |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | Observabilidad: sesiones, ítems, confirmaciones idempotentes, latencias                                                                                               |
| **Objective**               | Soporte y detección de estados atascados.                                                                                                                             |
| **Technical scope**         | Logs estructurados con `session_id`, `inventory_id`, `aisle_id`, `idempotency_key`; métricas (counts por transición, histogramas de fases); sin PII en logs de paths. |
| **Dependencies**            | Flujos 8–21 en staging mínimo.                                                                                                                                        |
| **Acceptance criteria**     | Una sesión problemática es reconstruible desde logs/métricas.                                                                                                         |
| **Risks**                   | Cardinalidad alta en labels → acotar etiquetas.                                                                                                                       |
| **Suggested test coverage** | Tests de que los eventos clave emiten log (spy).                                                                                                                      |


---

## Ticket 27 — GC de staging (TTL + barrido)


| Campo                       | Contenido                                                                                                                                                |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | Job programado: GC de blobs de staging y sesiones atascadas                                                                                              |
| **Objective**               | No acumular huérfanos indefinidamente; transiciones seguras.                                                                                             |
| **Technical scope**         | Config `STAGING_TTL_HOURS`, worker/cron interno, transición a `failed`/`cancelled`, borrado solo si sin `linked_source_asset_id`; límites por ejecución. |
| **Dependencies**            | Tickets 12–13.                                                                                                                                           |
| **Acceptance criteria**     | No borra materializados; reduce huérfanos; configurable.                                                                                                 |
| **Risks**                   | Carrera con confirmación → bloqueo por estado `confirming` o lease.                                                                                      |
| **Suggested test coverage** | Unit del GC con reloj simulado; integración con storage fake.                                                                                            |


---

## Ticket 28 — Testing integral E2E + regresiones


| Campo                       | Contenido                                                                                                                                       |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **Title**                   | QA: E2E captura → confirm → `process_aisle` habilitado + regresión upload manual                                                                |
| **Objective**               | Cierre de epic con pruebas que reflejen invariantes del blueprint.                                                                              |
| **Technical scope**         | Cadena: migración; dominio; use cases; API; idempotencia; gate de assets; regresión Ticket 7; opcional Playwright/Cypress si el repo ya lo usa. |
| **Dependencies**            | Fases 1–8 completas o feature-flag off para merge incremental.                                                                                  |
| **Acceptance criteria**     | No procesar sin assets; doble confirm sin duplicados; sesión/ítems en estados correctos; upload manual intacto.                                 |
| **Risks**                   | Flaky E2E por storage → hermeticidad con fakes.                                                                                                 |
| **Suggested test coverage** | Lista explícita: matriz idempotencia, gate, preview sin assets, GC, concurrencia mínima.                                                        |


---

# Orden de ejecución recomendado (ajustado al blueprint)


| Sprint | Tickets                                                | Nota                                                     |
| ------ | ------------------------------------------------------ | -------------------------------------------------------- |
| **1**  | 1, 2, 3, 4, 5, 6, 7                                    | Fundación persistencia + gate + spine + refactor upload. |
| **2**  | 8, 9, 10, **11 (fusionado con 8 o sub-tarea)**, 12, 13 | Sesión única como contenedor; staging; cancel.           |
| **3**  | 14, 15, 16, 17, 18, 19                                 | Tiempo, preview, confirm idempotente, side effects.      |
| **4**  | 20, 21, 22, 23, 24, 25                                 | API completa + MVP UI + paridad gate.                    |
| **5**  | 26, 27, 28                                             | Observabilidad, GC, E2E.                                 |


