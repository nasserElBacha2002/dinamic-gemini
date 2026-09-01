# Auditoría forense — paridad Mobile ↔ Backend (Supplier CODE_SCAN)

**Modo:** read-only — sin cambios de código  
**Golden reference:** job `f898e6f7-aab1-4eee-bb47-61e71df7cebe`  
**Inventory:** `eb6f750e-ed12-4c71-b9b2-56a1301e08a8`  
**Aisle:** `709fe503-2f5c-43ae-b680-25bbc3bbf51f`  
**Fecha:** 2026-09-01

---

## Veredicto ejecutivo

Mobile **implementa el mismo contrato offline determinístico** que el backend a nivel de arquitectura (sync bundle → resolver → validator → draft). Para el aisle de prueba, el **recognition-config productivo coincide** con el snapshot del job golden (ITEM SUPPLIER v10, POSITION SUPPLIER v3, configs SEGMENTED idénticas).

**No hay evidencia de divergencia funcional en el validador SEGMENTED** para los payloads productivos cuando se inspecciona el código — pero **tampoco hay prueba automatizada Mobile** con los fixtures exactos `LPNA000184|SKU773421|24` y `A04-R-02|04|RIGHT|02`, ni E2E en device con la imagen dual QR+Code128.

**Estado global:** **PARIDAD PARCIAL — READY_FOR_DEVICE_E2E = NO**

---

## Fase 1 — Arquitectura Mobile (call graph real)

```
AislesScreen.syncInventory()
  → OfflineRecognitionSyncService.syncInventory()
      GET /api/v3/inventories/{id}/recognition-config
      → OfflineRecognitionConfigRepository.replaceBundle() [SQLite v28, transactional]
      → LocalLabelProfileResolver.invalidate()

UploadQueue.runLocalCodeScanAfterPrepare()
  → LocalCodeScanStrategy.execute()
      → detectLocalBarcodes() [ML Kit native multipass]
      → runProfileAwareLocalScan()
          → consolidateCodeDetections() [Dinamic D1/legacy]
          → validateSupplierPayloadOffline() [SUPPLIER ITEM/POSITION]
      → LocalDetectionDraftRepository.upsertDraft()
          [recognition_profile_snapshot_json, label_id, quantity, product_results_json]

(Optional confirm path)
  → mapConfirmedToAuthoritativeRequest()
      PUT .../authoritative-code-scan
```

| Pieza | Archivo |
|-------|---------|
| Sync | `mobile/src/features/offlineRecognition/offlineRecognitionSyncService.ts` |
| SQLite repo | `mobile/src/database/repositories/offlineRecognitionConfigRepository.ts` |
| Resolver | `mobile/src/features/offlineRecognition/localLabelProfileResolver.ts` |
| Validator | `mobile/src/core/offlineSupplierLabelValidator.ts` |
| Scan orchestration | `mobile/src/features/localCodeScan/profileAwareLocalScan.ts` |
| Strategy | `mobile/src/features/localCodeScan/localCodeScanStrategy.ts` |
| Scanner | `mobile/src/features/localCodeScan/localCodeDetector.ts` + `LocalBarcodeDetector.kt` |
| Authoritative wire | `mobile/src/features/authoritativeLocalResult/authoritativeLocalResultPayloadMapper.ts` |
| Readiness | `mobile/src/features/offlineRecognition/checkOfflineRecognitionReadiness.ts` |

---

## Fase 2 — Config sync (respuesta real)

Bundle live para inventory `eb6f750e-...` (use case productivo):

| Campo | Valor |
|-------|-------|
| `bundle_revision` | `77757467f6da35393781879425bcd48a55f523780ec7848a022caadb58cb1a7f` |
| Aisle `709fe503-...` supplier | `c314c8c3-b6fd-490c-98dc-7b1ac40dca47` |
| effective_item_source | SUPPLIER |
| effective_position_source | SUPPLIER |
| ITEM profile | `99563751-...` v10 SEGMENTED |
| POSITION profile | `602caad9-...` v3 SEGMENTED |

Coincide con job golden `f898e6f7` (mismos profile ids/versiones).

---

## Fase 3 — Backend snapshot vs Mobile bundle

| Campo | Backend job | Mobile bundle (API) | Igual? |
|-------|-------------|---------------------|--------|
| item.source | SUPPLIER | SUPPLIER | ✅ |
| item.profile_id | 99563751-... | 99563751-... | ✅ |
| item.profile_version | 10 | 10 | ✅ |
| item.payload_structure | SEGMENTED | SEGMENTED | ✅ |
| item.delimiter | `\|` | `\|` | ✅ |
| item.segment_count | 3 | 3 | ✅ |
| item.field_mappings | label_id/0, sku/1, qty/2 | idéntico | ✅ |
| position.source | SUPPLIER | SUPPLIER | ✅ |
| position.profile_id | 602caad9-... | 602caad9-... | ✅ |
| position.profile_version | 3 | 3 | ✅ |
| position.payload_structure | SEGMENTED | SEGMENTED | ✅ |
| position.delimiter | `\|` | `\|` | ✅ |
| position.segment_count | 4 | 4 | ✅ |
| position.field_mappings | position_id/0..level/3 | idéntico | ✅ |

---

## Fase 4 — bundle_revision

**Backend:** `compute_offline_bundle_revision()` — SHA-256 sobre bundle canónico (aisles + profiles + deterministic block). Excluye `generated_at`. Tests confirman cambio ante supplier/override/version/config (`test_inventory_recognition_config_bundle.py`).

**Mobile:** no calcula hash localmente; compara string del servidor y skip replace si igual (`offlineRecognitionSyncService.ts` L33–36).

**Riesgo P1:** si el servidor emitiera revision stale pero idéntica con contenido distinto, Mobile no re-descargaría. Mitigado porque el backend **sí** hashea contenido relevante. Test Mobile documenta explícitamente blind trust (`offlineRecognitionSync.test.ts` L180–186).

---

## Fases 5–6 — SQLite y sync atómico

**Schema v28** confirmado en migraciones y tests.

**Atomic replace:** DELETE profiles + aisle config + INSERT all + upsert meta dentro de `withTransactionAsync`. Failure antes de commit preserva bundle anterior.

**Device SQLite dump:** **UNVERIFIED** — no se capturó DB de dispositivo en esta sesión.

---

## Fases 7–8 — Resolver local para aisle real

Precedencia implementada = backend:

1. Aisle override  
2. effective_*_source del bundle (ClientSupplier wiring)  
3. DINAMIC default  

Para aisle `709fe503-...` con bundle sincronizado → **ITEM SUPPLIER v10, POSITION SUPPLIER v3** (determinístico por código + bundle API).

---

## Fases 9–11 — Scanner y dual-symbol

**Formatos:** QR_CODE + CODE_128 habilitados (ML Kit).

**Backend job golden:** asset ITEM detectó 2 payloads (QR + Code128 mismo contenido) → 1 RESOLVED_INTERNAL.

**Mobile:**
- Native merge deduplica por `rawValue` idéntico antes de validator.
- `profileAwareLocalScan` toma **primer candidato VALID** por kind — no crea segundo producto.
- **No hay** dedupe explícito por `label_id|sku` identity como backend `code_scan_label_classifier` DUPLICATE.
- **No hay test** Mobile con QR+CODE128 mismo payload supplier SEGMENTED.

**Evaluación:** comportamiento esperado probablemente correcto (1 ITEM), pero **sin evidencia automatizada** → P1 test gap.

---

## Fases 12–14 — Payloads productivos y extractor

### ITEM `LPNA000184|SKU773421|24`

| | Backend | Mobile (código) |
|---|---------|-----------------|
| label_id | LPNA000184 | extractFields segment 0 |
| sku | SKU773421 | segment 1 |
| quantity | 24 | segment 2 (int) |
| internal_code | sku (runtime) | sku trim; null si absent |

Backend test: `test_supplier_profile_runtime_wiring.py` ✅  
Mobile test dedicado: **NO** (shared vectors usan ABC001\|SKU123\|20)

### POSITION `A04-R-02|04|RIGHT|02`

| | Backend | Mobile |
|---|---------|-----|
| position_id | A04-R-02 | segment 0 |
| pallet | 04 | segment 1 |
| side | RIGHT | segment 2 |
| level | 02 | segment 3 |
| quantity | null | no field |

Shared vector usa MINIMAL `A04-R-02` SIMPLE — **no** el payload SEGMENTED productivo de 4 segmentos.

---

## Fases 15–21 — Normalización, quantity, internalCode

- **Normalization order:** PARITY (trim → case → spaces → hyphens).
- **exact_length:** aplicado sobre payload normalizado completo pre-segmentación — PARITY.
- **Quantity:** Mobile validator no inventa `quantity=1`; draft usa `null`; confirm rechaza qty≤0 — PARITY.
- **internalCode wire:** authoritative mapper envía `null` para identity-only SUPPLIER — PARITY.
- **P1:** `localCodeScanStrategy.ts` L286 `labelId: labelId || (internalCode ?? '')` — puede poblar `label_id` con SKU si label_id vacío en product result.

---

## Fases 28–40 — Draft, upload, confirmación

**Draft persiste:** `recognition_profile_snapshot_json`, `label_id`, `quantity`, `product_results_json`, `recognition_context`.

**Authoritative upload (ITEM):** incluye `profile_id`, `profile_version`, `client_supplier_id`, `label_id`, `internal_code` (null identity-only).

**P1 gap:** `mapConfirmedToAuthoritativeRequest` hardcodea `label_kind: 'ITEM'` — path POSITION authoritative no mapeado.

**Preliminary sync:** no incluye profile snapshot — backend re-ejecuta CODE_SCAN en job (aceptable si diseño es server-authoritative para fotos).

**Confirmación:** usa draft persistido; no re-parse diferente en upload authoritative.

---

## Fase 43 — Error parity (muestra)

| Backend | Mobile equivalent |
|---------|-------------------|
| LABEL_PREFIX_MISMATCH | LABEL_PREFIX_MISMATCH (NOT_APPLICABLE) |
| LABEL_SEGMENT_COUNT_MISMATCH | LABEL_SEGMENT_COUNT_MISMATCH |
| AMBIGUOUS_LABEL_KIND | AMBIGUOUS_LABEL_KIND |
| SUPPLIER_LABEL_PROFILE_NOT_CONFIGURED | missingSupplierProfile + readiness |
| DUPLICATE (intra-image) | No equivalente explícito supplier |
| GS1_* | GS1_NOT_SUPPORTED_OFFLINE |

---

## Fase 57 — Hallazgos clasificados

### P0 (ninguno demostrado con evidencia runtime Mobile)

No se encontró divergencia **demostrada** que produzca datos incorrectos en device para los payloads golden. Los gaps son de **cobertura de prueba**, no bugs confirmados.

### P1

1. **Fixtures productivos ausentes** en `contracts/offline-recognition/v1/minimal-vectors.json` y tests Mobile.
2. **Dual QR+Code128 supplier** sin test de dedupe semántico.
3. **labelId fallback** a internalCode en strategy L286.
4. **Authoritative mapper** solo ITEM label_kind.
5. **bundle_revision blind trust** (mitigado por backend hash).
6. **Device SQLite / E2E UNVERIFIED**.

### P2

1. Observabilidad `mobile.recognition.*` no implementada.
2. Preliminary upload sin profile metadata (by design si server rescans).

---

## Fase 61 — Tests ejecutados

| Suite | Resultado |
|-------|-----------|
| Mobile unit (216 tests) | PASS |
| Mobile SQLite migrations v28 | PASS |
| Backend shared vectors | PASS |
| Backend supplier wiring (golden payloads) | PASS |
| Backend bundle_revision | PASS |
| Device E2E real images | **NOT RUN** |

---

## Conclusión (18 preguntas)

| # | Pregunta | Respuesta |
|---|----------|-----------|
| 1 | ¿Qué supplier/profile usa Mobile para ese aisle? | `c314c8c3-...`; ITEM SUPPLIER v10, POSITION SUPPLIER v3 (post-sync) |
| 2 | ¿Tiene ITEM v10? | Sí (bundle API + SQLite schema) |
| 3 | ¿Tiene POSITION v3? | Sí |
| 4 | ¿Bundle SQLite coincide con backend? | **Esperado sí**; dump device **UNVERIFIED** |
| 5 | ¿Resolver local coincide? | Sí (misma precedencia) |
| 6 | ¿ITEM segmented coincide? | Código sí; **sin test fixture productivo Mobile** |
| 7 | ¿POSITION segmented coincide? | Código sí; **sin test fixture productivo Mobile** |
| 8 | ¿QR y Code128 soportados? | Sí |
| 9 | ¿Dual-symbol dedupe? | Probable vía native merge; **sin test** |
| 10 | ¿Quantity null conservado? | Sí |
| 11 | ¿Label ID no → internalCode en wire? | Sí authoritative; **P1 en draft product result fallback** |
| 12 | ¿Position sin quantity? | Sí |
| 13 | ¿Profile id/version en draft/upload? | Sí en snapshot + authoritative ITEM |
| 14 | ¿Backend revalida versión histórica? | Sí (label_kind + version) |
| 15 | ¿Casos diferentes Mobile vs backend? | **No demostrados**; gaps de prueba |
| 16 | ¿P0 reales? | **Ninguno demostrado** |
| 17 | ¿Tests faltan? | Golden SEGMENTED fixtures, dual-symbol, device E2E, POSITION authoritative |
| 18 | ¿READY_FOR_DEVICE_E2E? | **NO** |

---

## Recomendaciones (no implementadas — audit only)

1. Agregar vectors productivos al contrato compartido.
2. Test Mobile: QR+CODE128 → 1 ITEM con LPNA000184|SKU773421|24.
3. Test Mobile: POSITION A04-R-02|04|RIGHT|02 SEGMENTED v3.
4. Device E2E con imágenes del job golden.
5. Revisar L286 labelId fallback y authoritative POSITION label_kind mapping.

**NO_MIGRATION_REQUIRED** — audit only.
