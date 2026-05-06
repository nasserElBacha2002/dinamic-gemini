# F5.1.0 — Inventario de exports de `frontend/src/api/client.ts`

## Alcance
- Auditoria sin cambios de codigo.
- Clasificacion de exports/helpers por dominio para preparar F5.1.1+.
- Verificacion de capture sessions para evitar duplicados.

## Verificacion captureSessions existente
- Existe `frontend/src/features/ingestionSessions/api/captureSessionsApi.ts`.
- `frontend/src/api/client.ts` no contiene funciones de capture/ingestion sessions.
- Recomendacion: **no crear** `frontend/src/api/captureSessionsApi.ts` en F5.1.x salvo necesidad puntual de facade unificada.

## Tabla de clasificacion (exports + helpers internos)
| Export / helper | Tipo | Dominio | Archivo destino sugerido | Riesgo | Notas |
|---|---|---|---|---|---|
| `InventoriesListQuery` | type export | inventories | `frontend/src/api/inventoriesApi.ts` | Bajo | Query DTO local al listado de inventarios. |
| `getInventories` | function export | inventories | `frontend/src/api/inventoriesApi.ts` | Medio | Usado ampliamente por pantallas principales. |
| `getInventory` | function export | inventories | `frontend/src/api/inventoriesApi.ts` | Medio | Base para detalle de inventario. |
| `getInventoryMetrics` | function export | inventories | `frontend/src/api/inventoriesApi.ts` | Medio | Afecta vistas de performance. |
| `exportInventoryResultsCsv` | function export | inventories | `frontend/src/api/inventoriesApi.ts` | Medio | Comparte helper de descarga. |
| `exportAisleResultsCsv` | function export | inventories | `frontend/src/api/inventoriesApi.ts` | Medio | Misma estrategia de descarga. |
| `createInventory` | function export | inventories | `frontend/src/api/inventoriesApi.ts` | Alto | Critico para flujos de alta (CreateInventoryDialog). |
| `uploadInventoryVisualReferences` | function export | assets/images | `frontend/src/api/assetsApi.ts` | Alto | Upload con validaciones dependientes en UI/hooks. |
| `getInventoryVisualReferences` | function export | assets/images | `frontend/src/api/assetsApi.ts` | Medio | Lista de referencias visuales. |
| `deleteInventoryVisualReference` | function export | assets/images | `frontend/src/api/assetsApi.ts` | Medio | Operacion destructiva; mantener firma. |
| `replaceInventoryVisualReference` | function export | assets/images | `frontend/src/api/assetsApi.ts` | Medio | Reemplazo de archivos existentes. |
| `fetchInventoryVisualReferenceFile` | function export | assets/images | `frontend/src/api/assetsApi.ts` | Alto | Usa blob/objectURL; sensible para previews. |
| `AislesListQuery` | type export | aisles | `frontend/src/api/aislesApi.ts` | Bajo | DTO de listado de aisles. |
| `getAisles` | function export | aisles | `frontend/src/api/aislesApi.ts` | Medio | Muy usado por hooks de navegacion. |
| `createAisle` | function export | aisles | `frontend/src/api/aislesApi.ts` | Alto | Critico en CreateAisleDialog. |
| `startAisleProcessing` | function export | aisles | `frontend/src/api/aislesApi.ts` | Alto | Inicia jobs; endpoint sensible. |
| `getAisleStatus` | function export | aisles | `frontend/src/api/aislesApi.ts` | Medio | Polling/estado operacional. |
| `runAisleMerge` | function export | aisles | `frontend/src/api/aislesApi.ts` | Medio | Operacion backend de consolidacion. |
| `getAisleMergeResults` | function export | aisles | `frontend/src/api/aislesApi.ts` | Medio | Lectura de resultados merge. |
| `getExecutionLog` | function export | jobs/executionLogs | `frontend/src/api/jobsApi.ts` | Medio | Consulta log por job. |
| `getAisleExecutionLog` | function export | jobs/executionLogs | `frontend/src/api/jobsApi.ts` | Medio | Consulta log agregado por aisle. |
| `getExecutionLogTxtUrl` | URL builder export | jobs/executionLogs | `frontend/src/api/jobsApi.ts` | Medio | Builder de URL directa; mantener estable. |
| `getAisleExecutionLogTxtUrl` | URL builder export | jobs/executionLogs | `frontend/src/api/jobsApi.ts` | Medio | Similar al anterior. |
| `downloadExecutionLogTxt` | download helper export | jobs/executionLogs | `frontend/src/api/jobsApi.ts` | Alto | Descarga + objectURL + parse error. |
| `downloadAisleExecutionLogTxt` | download helper export | jobs/executionLogs | `frontend/src/api/jobsApi.ts` | Alto | Igual patron de riesgo. |
| `getAisleJobDetail` | function export | jobs/executionLogs | `frontend/src/api/jobsApi.ts` | Medio | Detalle de job usado en observabilidad. |
| `cancelAisleJob` | function export | jobs/executionLogs | `frontend/src/api/jobsApi.ts` | Medio | Mutacion operativa sensible. |
| `retryAisleJob` | function export | jobs/executionLogs | `frontend/src/api/jobsApi.ts` | Medio | Mutacion operativa sensible. |
| `uploadAisleAssets` | function export | assets/images | `frontend/src/api/assetsApi.ts` | Alto | Upload de evidencia fuente. |
| `listAisleAssets` | function export | assets/images | `frontend/src/api/assetsApi.ts` | Medio | Lista de assets por aisle. |
| `deleteAisleSourceAsset` | function export | assets/images | `frontend/src/api/assetsApi.ts` | Medio | Borrado de source asset. |
| `getReferenceImageFileUrl` | URL builder export | assets/images | `frontend/src/api/assetsApi.ts` | Alto | URL base para fetch de imagen/preview. |
| `getReferenceImageDisplayUrl` | URL builder export | assets/images | `frontend/src/api/assetsApi.ts` | Alto | Incluye query semantics (`job_id`). |
| `EvidenceImageLoadSpec` | type export | assets/images | `frontend/src/api/assetsApi.ts` | Bajo | Tipo local de cargador de evidencias. |
| `FetchEvidenceImageResult` | type export | assets/images | `frontend/src/api/assetsApi.ts` | Bajo | Tipo retorno de preview loader. |
| `fetchEvidenceImageDisplay` | function export | assets/images | `frontend/src/api/assetsApi.ts` | Alto | Fallback presigned/auth + objectURL revoke. |
| `AislePositionsListQuery` | type export | jobs/executionLogs | `frontend/src/api/jobsApi.ts` | Bajo | DTO para posiciones por aisle/job. |
| `listAisleJobs` | function export | jobs/executionLogs | `frontend/src/api/jobsApi.ts` | Medio | Listado de jobs por aisle. |
| `getAisleBenchmarkCompare` | function export | analytics | `frontend/src/api/analyticsApi.ts` | Medio | Usado en comparativas analytics. |
| `getAisleBenchmarkCompareMany` | function export | analytics | `frontend/src/api/analyticsApi.ts` | Medio | Compare many runs. |
| `promoteAisleOperationalJob` | function export | jobs/executionLogs | `frontend/src/api/jobsApi.ts` | Medio | Mutacion operativa sobre jobs. |
| `downloadAisleBenchmarkExportCsv` | download helper export | analytics | `frontend/src/api/analyticsApi.ts` | Alto | Descarga csv con parse de errores. |
| `getAislePositions` | function export | jobs/executionLogs | `frontend/src/api/jobsApi.ts` | Medio | Base de Review/positions por aisle. |
| `ReviewQueueListQuery` | type export | misc/pendiente | `frontend/src/api/reviewQueueApi.ts` (futuro) | Bajo | Fuera del alcance de modulos F5.1 propuestos. |
| `getReviewQueuePositions` | function export | misc/pendiente | `frontend/src/api/reviewQueueApi.ts` (futuro) | Medio | Dejar temporalmente en facade/client. |
| `getPositionDetail` | function export | misc/pendiente | `frontend/src/api/reviewQueueApi.ts` (futuro) | Medio | Dejar temporalmente en client hasta subfase dedicada. |
| `submitReviewAction` | function export | misc/pendiente | `frontend/src/api/reviewQueueApi.ts` (futuro) | Alto | Manejo de error especifico; no mover primero. |
| `AnalyticsQueryParams` | type export | analytics | `frontend/src/api/analyticsApi.ts` | Bajo | DTO compartido de analytics. |
| `getAnalyticsSummary` | function export | analytics | `frontend/src/api/analyticsApi.ts` | Medio | Endpoint de dashboard. |
| `getAnalyticsTrends` | function export | analytics | `frontend/src/api/analyticsApi.ts` | Medio | Endpoint de tendencias. |
| `getAnalyticsInventoryPerformance` | function export | analytics | `frontend/src/api/analyticsApi.ts` | Medio | Tabla de performance. |
| `getAnalyticsAisleIssues` | function export | analytics | `frontend/src/api/analyticsApi.ts` | Medio | Lista de issues. |
| `getAnalyticsQualityPatterns` | function export | analytics | `frontend/src/api/analyticsApi.ts` | Medio | Patrones de calidad. |
| `getAnalyticsManualInterventions` | function export | analytics | `frontend/src/api/analyticsApi.ts` | Medio | Breakdown de intervenciones. |
| `API_BASE` | const interno | core/http | `frontend/src/api/core.ts` (opcional) | Alto | Base transversal a todos los dominios. |
| `protectedFetch` | helper interno | core/http | `frontend/src/api/core.ts` | Alto | Critico para auth header. |
| `ValidationDetailItem` | helper interno | core/http | `frontend/src/api/core.ts` | Bajo | Tipo interno util para errores. |
| `messageFromErrorDetail` | helper interno | core/http | `frontend/src/api/core.ts` | Alto | Canoniza mensajes de error API. |
| `throwApiErrorIfNotOk` | helper interno | core/http | `frontend/src/api/core.ts` | Alto | Nucleo de error handling. |
| `handleResponse` | helper interno | core/http | `frontend/src/api/core.ts` | Alto | Parse JSON + throw estandar. |
| `buildInventoriesListQueryString` | helper interno | inventories | `frontend/src/api/inventoriesApi.ts` | Bajo | Helper acotado al dominio. |
| `filenameFromContentDisposition` | helper interno | core/http | `frontend/src/api/core.ts` | Medio | Reutilizado por multiples descargas. |
| `buildAislesListQueryString` | helper interno | aisles | `frontend/src/api/aislesApi.ts` | Bajo | Query helper aislado. |
| `fetchAuthorizedReferenceFileAsBlob` | helper interno | assets/images | `frontend/src/api/assetsApi.ts` | Alto | Flujo auth/presigned para preview. |
| `buildAislePositionsQueryString` | helper interno | jobs/executionLogs | `frontend/src/api/jobsApi.ts` | Bajo | Query helper especifico. |
| `buildReviewQueueQueryString` | helper interno | misc/pendiente | `frontend/src/api/client.ts` (temporal) | Medio | Mover junto con reviewQueueApi futuro. |
| `buildAnalyticsQueryString` | helper interno | analytics | `frontend/src/api/analyticsApi.ts` | Bajo | Query helper de analytics. |
| `getProcessingProviderOptions` | function export | adminAi | `frontend/src/api/adminAiApi.ts` | Medio | Relacionado a configuracion AI. |
| `getAdminAiConfig` | function export | adminAi | `frontend/src/api/adminAiApi.ts` | Medio | Endpoint admin restringido. |
| `getAdminAiComposedPrompt` | function export | adminAi | `frontend/src/api/adminAiApi.ts` | Medio | Preview/composition prompt admin. |

## Recomendacion de orden de movimiento (F5.1.x)
1. **F5.1.1 (estructura + facade):** crear modulos por dominio y mantener `api/client.ts` como punto de entrada por re-export.
2. **F5.1.2:** mover `inventories` + `aisles` + query helpers locales.
3. **F5.1.3:** mover `jobs/executionLogs` + `assets/images`; conservar cuidadosamente builders y downloads.
4. **F5.1.4:** mover `analytics` + `adminAi`.
5. **F5.1.5:** no crear duplicado capture sessions; mantener modulo existente en `features/ingestionSessions/api`.
6. **F5.1.6:** validar compatibilidad completa y reduccion real de `api/client.ts`.

## Helpers que deben quedar en core/http
- `API_BASE`
- `protectedFetch`
- `messageFromErrorDetail`
- `throwApiErrorIfNotOk`
- `handleResponse`
- `filenameFromContentDisposition`
- (opcional) `ValidationDetailItem`

## Exports que NO conviene mover primero
- `submitReviewAction` (manejo de error especifico y sensibilidad funcional).
- `getReviewQueuePositions`
- `getPositionDetail`
- `ReviewQueueListQuery`
- `buildReviewQueueQueryString`

Motivo: forman un subdominio (`reviewQueue`) no incluido en la lista principal de modulos F5.1 y conviene tratarlos en un corte separado para minimizar riesgo.
