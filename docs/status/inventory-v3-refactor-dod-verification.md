# Inventory V3 Refactor — DoD Verification

**Fecha:** 2026-03-31  
**Fuentes contrastadas:** plan por sprints, ADR canónico, auditorías, documentos de progreso/cierre, código backend/frontend, exports y tests relacionados.

---

## 1. Executive summary

- El refactor tiene una base técnica real y consistente en el repo: `PositionCanonicalView`, ensamblado único en `position_to_summary`, bloques públicos enriquecidos, `technical_snapshot` en detail, export operativo canónico y export técnico separado.
- **Sprint 1** y **Sprint 2** pueden considerarse cerrados, pero con deuda aceptada explícita.
- **Sprint 3** quedó implementado en lo esencial y también puede considerarse cerrado con deuda aceptada, aunque la evidencia documental es más de “progress” que de closeout formal.
- **Sprint 4** quedó corregido en sus blockers principales: review queue backend/frontend y cobertura SQL analytics Sprint 4. Puede considerarse cerrable con deuda aceptada, aunque no representa aún el cleanup final absoluto del refactor.

**Resumen de estado**

- Sprints realmente cerrados: 0 sin deuda
- Sprints cerrados con deuda aceptada: 4
- Sprints con gaps que impiden cierre: 0

---

## 2. Sprint-by-sprint status

### Sprint 1

#### Expected DoD

- ADR de campos canónicos creado y alineado al plan.
- Auditoría real del frontend legacy.
- Capa canónica intermedia reusable (`PositionCanonicalView` o equivalente).
- `position_to_summary` delegando a esa capa en lugar de ensamblar inline.
- Tests de coherencia/paridad base para identidad, cantidad y fallback.
- Sin romper contrato público.

#### Evidence found in code/docs/tests

- El ADR existe y define campos canónicos, derivados y técnicos en `docs/adr/inventory-v3-canonical-fields.md`.
- La auditoría frontend existe en `docs/audits/frontend-legacy-position-fields-usage.md`.
- La capa canónica está implementada en `backend/src/application/mappers/position_canonical_view.py`.
- `position_to_summary` delega al builder canónico y a un único punto de serialización en `backend/src/api/routes/v3/shared.py`.
- Los tests base existen en:
  - `backend/tests/application/mappers/test_position_canonical_view.py`
  - `backend/tests/api/test_position_summary_mapping.py`
- El contrato público se mantiene sin breaking change, consistente con `docs/status/inventory-v3-sprint-1-closeout.md`.

#### Gaps

- La deuda de filas aggregated ya existe desde Sprint 1 y queda aceptada/documentada: la semántica visible puede no coincidir plenamente con `ProductRecord`.
- La gobernanza del snapshot técnico en Sprint 1 es principalmente una decisión codificada en el mapper, no una restricción sistémica general.

#### Closure decision

**Closed with accepted debt**

#### Test assessment

**Suficiente**

---

### Sprint 2

#### Expected DoD

- Bloques `product`, `quantity` y `traceability` presentes en list/detail.
- Contrato enriquecido montado desde la vista canónica.
- Aliases legacy todavía presentes.
- Deprecaciones marcadas.
- Frontend capaz de preferir los bloques nuevos.
- Tests de compatibilidad y semántica de quantity/product/traceability.

#### Evidence found in code/docs/tests

- El schema backend expone `product`, `quantity` y `traceability` en `backend/src/api/schemas/position_schemas.py`.
- El ensamblado desde la vista canónica está en `backend/src/api/routes/v3/shared.py`.
- La vista canónica fue extendida con campos de display/barcode/final quantity en `backend/src/application/mappers/position_canonical_view.py`.
- Los aliases siguen presentes y marcados `deprecated=True` en OpenAPI/Pydantic.
- El frontend tipa los bloques nuevos en `frontend/src/api/types/responses.ts` y los prefiere en `frontend/src/features/results/mappers/positionToResult.ts`.
- Tests relevantes:
  - `backend/tests/api/test_position_summary_sprint2_contract.py`
  - `backend/tests/application/mappers/test_position_canonical_view.py`
  - `backend/tests/api/test_position_summary_mapping.py`
  - `frontend/tests/resultMappers.test.ts`

#### Gaps

- El punto de plan sobre `detected_summary_json` en list no se resolvió en Sprint 2, pero quedó explícitamente diferido a Sprint 3 en `docs/status/inventory-v3-sprint-2-closeout.md`.
- La deprecación es metadata/documentación, no existe enforcement runtime.

#### Closure decision

**Closed with accepted debt**

#### Test assessment

**Suficiente**

---

### Sprint 3

#### Expected DoD

- List deja de depender normalmente de `detected_summary_json`.
- Detail incorpora `technical_snapshot`.
- `detected_summary_json` queda relegado a legacy/deprecated.
- CSV estándar alineado al contrato canónico.
- CSV técnico separado.
- Tests de paridad razonable entre API/detail/CSV.

#### Evidence found in code/docs/tests

- List positions usa `include_technical=false` por defecto en `backend/src/api/routes/v3/positions.py`.
- Detail expone `technical_snapshot` y ya no puebla el blob legacy para el frontend activo.
- `PositionDetailResponse` incluye `technical_snapshot` en `backend/src/api/schemas/position_schemas.py`.
- El export operativo usa la vista canónica en `backend/src/application/mappers/inventory_export_rows.py`.
- El export técnico existe en:
  - `backend/src/application/services/csv_inventory_exporter.py`
  - `backend/src/application/use_cases/export_inventory_results.py`
  - `backend/src/api/routes/v3/inventories.py`
- Tests relevantes:
  - `backend/tests/application/use_cases/test_export_inventory_results.py`
  - `backend/tests/api/test_inventory_export_api.py`
  - `backend/tests/api/test_position_summary_mapping.py`
  - `frontend/tests/resultMappers.test.ts`

#### Gaps

- No existe closeout formal específico de Sprint 3; la evidencia principal está en `docs/status/inventory-v3-sprint-3-progress.md`.
- La paridad API/CSV está verificada de forma focalizada, no como suite exhaustiva end-to-end.
- `PositionSummaryResponse` sigue compartido entre list/detail, y esa separación quedó diferida.

#### Closure decision

**Closed with accepted debt**

#### Test assessment

**Parcial**

---

### Sprint 4

#### Expected DoD

- Política final explícita de `detected_summary_json`.
- Readers nuevos prefiriendo canónico cuando hay reemplazo claro.
- `corrected_summary_json` auditado/documentado.
- Política/documentación explícita para aggregated rows.
- Readiness clara para cleanup final de legacy.
- Analytics/readers revisados razonablemente.

#### Evidence found in code/docs/tests

- La política del snapshot técnico quedó mejor documentada en:
  - `docs/adr/inventory-v3-canonical-fields.md`
  - `docs/status/inventory-v3-sprint-4-progress.md`
- `MemoryAnalyticsRepository` ahora reutiliza `primary_by_position` y aplica lógica canónica en analytics memory:
  - `backend/src/infrastructure/repositories/memory_analytics_repository.py`
  - `backend/src/application/services/analytics_aggregation_core.py`
- SQL analytics tiene una migración real pero acotada para `quantity_zero`:
  - `backend/src/infrastructure/repositories/sql_analytics_repository.py`
- `corrected_summary_json` quedó inventariado/documentado como deuda persistida.
- La política de aggregated rows quedó documentada como proyección técnica/virtual, sin inventar una nueva persistencia de negocio.
- Test principal agregado/ajustado:
  - `backend/tests/application/test_analytics_phase51.py`

#### Gaps

- La gobernanza del snapshot técnico sigue siendo principalmente una regla documental/técnica, no una enforcement rule automática.
- `PositionSummaryResponse` sigue compartido entre list/detail.
- Las filas aggregated continúan como excepción documentada basada en snapshot.
- `corrected_summary_json` sigue persistido hasta validación externa de remoción.

#### Closure decision

**Closed with accepted debt**

#### Test assessment

**Parcial a suficiente**

---

## 3. Cross-sprint observations

- La línea arquitectónica principal sí quedó implementada: el backend de posiciones ya pivotea sobre una capa canónica y el export operativo también.
- La mayor deuda transversal es la excepción de filas aggregated/consolidated: persiste desde Sprint 1 y sigue condicionando Sprints 3 y 4.
- Hay una diferencia entre “policy documented” y “policy enforced”: esto se nota más en Sprint 4 con el snapshot técnico.
- El review queue ya quedó alineado en sus derivaciones principales a la capa canónica, pero sigue dependiendo del contrato compartido `PositionSummaryResponse`.
- Sprint 3 está más fuerte en implementación que en formalización documental: hay progreso muy concreto, pero no un closeout equivalente al de Sprint 1/2.

---

## 4. Readiness for final legacy cleanup

### Estado real

- El sistema está bastante preparado para dejar de depender de `detected_summary_json` en frontend.
- No está listo todavía para remover aliases legacy top-level de forma segura.
- El cleanup final requiere cerrar primero la migración de consumers activos fuera de:
  - `sku`
  - `qty`
  - `qtySource`
  - `detected_quantity`
  - campos de traceability flat

### Blockers concretos

- consumo frontend directo o indirecto residual de aliases top-level fuera del review queue principal
- `PositionSummaryResponse` aún compartido entre list/detail
- review queue backend todavía summary-centric
- cobertura insuficiente de analytics SQL Sprint 4
- falta de confirmación externa para remover físicamente `corrected_summary_json`

---

## 5. Recommended next action

- **Sí conviene considerar cerrados con deuda aceptada** los Sprints 1, 2, 3 y 4.
- No hace falta abrir una fase ambigua grande; si se desea seguir, conviene una fase final muy chica y explícita enfocada en:
  1. decidir formalmente si list/detail se separan o si esa deuda queda aceptada
  2. definir el momento de remoción final de aliases legacy
  3. verificar consumidores externos antes de cleanup físico de blobs persistidos

**Recomendación operativa:** el refactor puede considerarse funcionalmente cerrado con deuda aceptada. Si el equipo quiere un cierre absoluto, el paso siguiente debería ser un **Sprint 5 / cleanup final** muy acotado, no una nueva fase amplia de rediseño.
