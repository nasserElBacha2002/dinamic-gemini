# Mapa de reutilización — móvil ↔ servidor

Clasificación: **directo** | **refactor** | **contrato** | **no reutilizable** | **no recomendable móvil** | **sensible servidor**

| Componente actual | Ubicación | Responsabilidad | Acoplamiento | Reutilización | Refactor requerido | Riesgo |
|-------------------|-----------|-----------------|--------------|---------------|--------------------|--------|
| `parse_inventory_code_payload` | `backend/src/application/services/code_scan_qr_payload.py` | Grammar QR/barcode | Bajo (puro) | **contrato** + port TS | Golden tests compartidos | Bajo |
| `EncodedLabelPayloadParser` | `.../encoded_label_payload_parser.py` | Validación code/qty | Bajo | **contrato** | Port o OpenAPI schema | Bajo |
| `AisleIdentificationMode` / strategies | `domain/aisle_identification/` | Enums de modo | Bajo | **contrato** | Ya parcial en `processingMode.ts` | Bajo |
| `resolve_aisle_identification_mode` | `domain/aisle_identification/resolver.py` | Jerarquía request→…→default | Medio | **contrato** | Spec + tests; no ejecutar resolver completo en móvil | Medio |
| `FallbackEligibilityPolicy` | `fallback_eligibility_policy.py` | Elegibilidad fallback | Bajo-medio | **contrato** | Solo si móvil predice fallback | Medio |
| `UploadRequestLimitPolicy` / constants | `upload_limits.py`, config route | Límites upload | Bajo | **contrato** | Mobile ya consume `/config/upload-limits` | Bajo |
| `buildMicroBatch` / packing | `mobile/src/core/uploadBatching.ts` | Empaque multipart | N/A móvil | **directo** (ya móvil) | Alinear con server caps | Bajo |
| `preparePhotoForUpload` | `mobile/.../photoPrepare.ts` | HEIC/resize | Expo | **directo** (extender) | Aplicar `DEFAULT_MAX_DIMENSION_PX` | Bajo |
| `UploadQueue` + SQLite schema | `uploadQueue.ts`, `captureSchema.ts` | Cola persistente | Expo SQLite | **directo** (extender estados) | Campos result sync | Medio |
| `CaptureService` / MediaStore | `captureService.ts`, `mediaStore.ts` | Detección galería | Android/Expo | **no reutilizable** cross-server | — | — |
| Foreground service módulo | `modules/capture-foreground-service` | FGS captura | Android | **refactor** para upload FGS | Extender tipos de trabajo | Medio |
| WorkManager stub | `backgroundWork.ts` + Kotlin | Background schedule | Android | **refactor** (implementar de verdad) | Worker nativo | Alto OEM |
| `UploadAisleAssetsUseCase` | backend use case | Persist assets | FastAPI/storage | **sensible servidor** | Additive signed upload | Medio |
| Multipart spool SHA-256 | `multipart_aisle_uploads.py` | Digest temporal | I/O | **refactor** | Persistir hash en SourceAsset | Bajo |
| `CodeScanProcessingStrategy` | image_processing | Scan servidor | OpenCV/ZXing/etc. | **no recomendable móvil** | SDK distinto on-device | Alto divergencia |
| `InternalOcrProcessingStrategy` | image_processing | OCR Tesseract | Nativo server | **no recomendable móvil** | — | Alto |
| `GlobalExternalFallbackCoordinator` | GLOBAL_BATCH LLM | Fallback vision | LLM keys | **sensible servidor** | Nunca en móvil | Crítico |
| Hybrid prompts / adapters | `llm/`, prompt composer | Contratos LLM | Providers | **sensible servidor** | — | Crítico |
| `ProcessingResultPersister` | persist posiciones | UoW SQL | SQL Server | **sensible servidor** | Preliminary accept path | Alto |
| `JobAssetProcessingStatus` | domain enum | Estados asset | Bajo | **contrato** | Mapear a LocalImageTask | Bajo |
| Auth JWT admin | `get_current_admin` | Authz | Auth stack | **sensible servidor** | Optional scoped tokens later | Medio |
| ResultsScreen summary | mobile UI | Read-only | HTTP | **directo** | No añadir review | — |
| Web review UI | `frontend/` | Corrección | — | **sensible servidor/web** | Fuera de móvil | — |
| Feature flags mobile | `featureFlags.ts` | Toggles | Env build | **refactor** | Unificar con remote config | Medio |
| `heicConvertToJpeg` flag | flags vs prepare | Config muerta | — | **refactor** | Wire o eliminar | Bajo |

## Resumen

- **Compartir de verdad:** grammar/payload CODE_SCAN, enums, límites, idempotency shapes — vía **contract tests**, no binario compartido.
- **Extender en móvil:** cola SQLite, prepare, FGS/WorkManager.
- **Nunca mover a móvil:** LLM keys, INTERNAL_OCR server engine, hybrid pipeline, review authority.
