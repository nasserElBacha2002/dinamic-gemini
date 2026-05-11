# F5 — Frontend regression closure (Phase F — final)

**Date:** 2026-05-11  
**Final recommendation:** `PHASE_F_CLOSED_READY_FOR_PHASE_G`

---

## 1. Executive summary

Phase F consolidated UX around clients, suppliers, inventories, aisle processing, and full-page observability. Supplier prompt and reference image management was moved to **supplier detail tabs**, removing duplicate actions from the **client detail suppliers table**. The process dialog keeps **supplier-adapted** copy without advanced manual prompt profile selection. Automated validation (**typecheck, lint, build, full vitest, check:i18n**) completed successfully. Manual end-to-end QA in a browser was **not** run in this environment; risk is classified as **non-blocking** given test depth on critical paths.

---

## 2. Final Phase F status

| Area | Status |
|------|--------|
| Navigation (clients → supplier → inventory → aisles → observability) | Closed (code + tests) |
| Client detail (no duplicate supplier actions) | Closed |
| Supplier detail (tabs + inline modules) | Closed |
| Process dialog (no advanced profile UX) | Closed |
| Observability (page, dynamic provider titles) | Closed |
| Spanish-first operator UI | Closed with noted JSON debt |

---

## 3. Files reviewed (representative)

- `frontend/src/pages/ClientsList.tsx`, `ClientDetail.tsx`, `ClientSupplierDetail.tsx`
- `frontend/src/pages/InventoryDetail.tsx`, `InventoryDetailHeader.tsx`
- `frontend/src/features/inventories/components/InventoryAislesSection.tsx`, `AisleProcessingDialog.tsx`
- `frontend/src/pages/AisleObservabilityPage.tsx`, `AisleObservabilityWorkspace.tsx`
- `frontend/src/components/ExecutionLogPanel.tsx`, `frontend/src/utils/executionLogProviderTitle.ts`
- `frontend/src/features/clients/components/SupplierPromptConfigsModule.tsx`, `SupplierReferenceImagesModule.tsx`
- `frontend/src/i18n/locales/es/translation.json`
- Tests: `ClientDetailPage.test.tsx`, `ClientSupplierDetailPage.test.tsx`, `InventoryDetailPage.test.tsx`, `ExecutionLogPanel.test.tsx`, `SupplierPromptConfigsModule.test.tsx`, `SupplierReferenceImagesModule.test.tsx`

---

## 4. Files changed in this F5 closure pass

| File | Change |
|------|--------|
| `frontend/audit/phase-f/f5-final-ux-audit.md` | **Created** — final read-only UX audit |
| `frontend/audit/phase-f/f5-i18n-final-audit.md` | **Created** — final i18n audit |
| `frontend/audit/phase-f/f5-frontend-regression-closure.md` | **Replaced** — this document |
| `frontend/tests/ClientDetailPage.test.tsx` | **Updated** — asserts inventarios del cliente + crear inventario + link a inventario |

*(Cambios funcionales mayores de pestañas/proveedor/cliente ya integrados en commits previos de Phase F.)*

---

## 5. Navigation summary

Listado **Clientes** → detalle **Cliente** (proveedores + inventarios filtrados) → detalle **Proveedor** (`/clientes/:id/proveedores/:supplierId` + `?tab=`) → **Inventario** → **Pasillos** → **Observabilidad** (página dedicada). Breadcrumbs y botones “Volver” cubren retorno.

---

## 6. Client detail final UX

- Información, proveedores, inventarios y acciones de creación presentes.
- Tabla de proveedores: **sin** botones de instrucciones/imágenes; nombre es enlace al detalle del proveedor.

---

## 7. Supplier detail final UX

- Pestañas: **Resumen**, **Prompts**, **Imágenes de referencia**.
- Sin botones primarios “Gestionar prompts / imágenes” que abran drawers; contenido en pestañas vía módulos `inline`.

---

## 8. Inventory / aisle final UX

- Alerta legado sin `client_id`.
- Columna de proveedor del pasillo con enlaces cuando hay cliente + `client_supplier_id`.
- Diálogo de procesamiento alineado con flujo testeado.

---

## 9. Process dialog final UX

- Sin sección de opciones avanzadas ni selector de perfil base en el diálogo actual.
- Texto de prompt automático + proveedor del pasillo (tests en `InventoryDetailPage.test.tsx`).

---

## 10. Observability final UX

- Workspace en página completa; pestañas/secciones (eventos, prompt utilizado, adjuntos, trazabilidad) según implementación actual.
- Títulos de solicitud al proveedor dinámicos (`Solicitud a {{name}}`); test de regresión Claude vs Gemini en `ExecutionLogPanel.test.tsx`.

---

## 11. i18n audit summary

- `npm run check:i18n`: **pass**.
- Advertencias: valores en inglés dentro de algunas claves `es` y claves `en` incompletas respecto a `es` — deuda conocida, no bloqueante para cerrar Phase F.
- Detalle: `f5-i18n-final-audit.md`.

---

## 12. Tests added/updated

| Test file | Coverage |
|-----------|----------|
| `ClientDetailPage.test.tsx` | Sin botones duplicados; link proveedor; **nuevo:** sección inventarios + crear inventario + link inventario |
| `ClientSupplierDetailPage.test.tsx` | Tabs, ausencia de botones drawer, deep link `?tab=` |
| `InventoryDetailPage.test.tsx` | Process dialog sin controles avanzados |
| `ExecutionLogPanel.test.tsx` | Título proveedor (Claude vs Gemini) |

Suite completa: **513** tests passed (2026-05-11 run).

---

## 13. Validation commands and results

Ejecutados desde `frontend/`:

| Command | Result |
|---------|--------|
| `npm run typecheck` | Pass |
| `npm run lint` | Pass |
| `npm run build` | Pass |
| `npm test` | Pass (90 files) |
| `npm run check:i18n` | Pass (warnings documented) |

---

## 14. Manual QA result

**Not executed** in this environment (no authenticated browser session against a live API). Checklist del spec queda como guía para demo/pre-producción. Riesgo residual: **medium / non-blocking** si CI verde y stakeholders aceptan demo manual posterior.

---

## 15. Remaining frontend debt (classification)

| Debt | Severity | Classification | Recommended phase |
|------|----------|----------------|-------------------|
| Algunos valores en inglés dentro de `es/translation.json` (KPI / empty copy) | Low | NON_BLOCKING_DEBT | Phase G o PR i18n |
| Paridad `en` incompleta vs `es` (check:i18n notes) | Low | NON_BLOCKING_DEBT | Phase G |
| Visibilidad de prompt completo depende de backend / logging | Low | ACCEPTED_BEHAVIOR | Ops / docs |
| QA manual no ejecutado aquí | Medium | NON_BLOCKING_DEBT | Antes de demo prod |
| Endurecimiento ownership proveedor / inventarios legacy | Medium | BACKEND_DEBT | Phase G |
| Paneles JSON crudos en observabilidad | Low | NON_BLOCKING_DEBT | Phase G polish |

---

## 16. Final recommendation

```txt
PHASE_F_CLOSED_READY_FOR_PHASE_G
```

**Rationale:** Criterios de aceptación Phase F cubiertos por código + tests automatizados + auditorías documentadas (`f5-final-ux-audit.md`, `f5-i18n-final-audit.md`). Deuda restante no bloquea el cierre formal de Phase F; debe planificarse en Phase G o hardening operativo.

---

## Next phase

**Phase G:** backend hardening, higiene i18n profunda, y QA manual con datos reales sobre el checklist F5.
