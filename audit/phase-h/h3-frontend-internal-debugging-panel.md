# H3 — Frontend internal debugging panel

## 1. Executive summary

**Final status:** `READY_FOR_H4_WITH_GAPS`

The read-only **Auditabilidad** tab is integrated into the existing aisle observability workspace (same route as execution log / prompt inspection). It consumes `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/auditability` via a typed client and TanStack Query, and renders structured Spanish sections (resumen, prompt efectivo, fallback/advertencias, referencias, fuentes, metadata faltante). No backend, pipeline, persistence, or metrics changes.

**Gaps:** no metrics dashboard; no SQL audit columns; no RBAC beyond existing admin/session; no top-level job-only URL; `inventory_visual_references_used` may stay null with explanatory copy.

---

## 2. What was implemented

| Path | Responsibility |
|------|----------------|
| `frontend/src/api/types/responses.ts` | `RunAuditMetadataSources`, `RunAuditReferenceUsage`, `RunAuditabilityView` (snake_case aligned with backend `to_jsonable`) |
| `frontend/src/api/jobsApi.ts` | `getJobAuditability`, `getJobAuditabilityPath` (path helper for tests) |
| `frontend/src/api/client.ts` | Re-export new API functions |
| `frontend/src/api/queryKeys.ts` | `queryKeys.inventories.jobAuditability` |
| `frontend/src/hooks/useAisles.ts` | `useJobAuditability` |
| `frontend/src/hooks/index.ts` | Export `useJobAuditability` |
| `frontend/src/components/JobAuditabilityPanel.tsx` | Read-only panel UI + loading/error; optional `auditability` override for tests |
| `frontend/src/components/AisleObservabilityWorkspace.tsx` | Fifth tab **Auditabilidad**; renders panel when job scope + selected job |
| `frontend/src/i18n/locales/es/translation.json` | `jobs.obs_tab_auditability`, `observability.auditability.*` keys |
| `frontend/tests/jobAuditabilityApi.test.ts` | URL path contract |
| `frontend/tests/JobAuditabilityPanel.test.tsx` | Happy path, partial metadata, null booleans, loading, no `prompt_text` |
| `frontend/tests/useJobAuditability.test.tsx` | Hook calls `getJobAuditability` with ids |
| `frontend/tests/InventoryDetailPage.test.tsx` | Mock `useJobAuditability`; integration: tab visible + panel content |

---

## 3. Frontend integration point

- **Page:** `AisleObservabilityPage` (unchanged) — full-page observability for one aisle.
- **Workspace:** `AisleObservabilityWorkspace` — main content tabs now: Eventos, Prompt utilizado, Adjuntos, Trazabilidad, **Auditabilidad**.
- **Context:** Tab **Auditabilidad** is useful when **log scope = selected job** and a **job is selected** (same as other job-scoped tabs). If the user is on merged log scope or has not chosen a job, the panel shows the existing “elegí una ejecución” hint.

---

## 4. API contract consumed

| Item | Detail |
|------|--------|
| **Method / path** | `GET /api/v3/inventories/{inventoryId}/aisles/{aisleId}/jobs/{jobId}/auditability` |
| **Client** | `getJobAuditability` → `RunAuditabilityView` |
| **Errors** | `ErrorAlert` + `resolveApiErrorMessage(..., 'observability.auditability.loadError')` — no raw stack traces in primary copy |

---

## 5. UI sections

1. **Resumen** — job id, estado, modo legacy, cliente, proveedor del cliente, provider, modelo, timestamps.
2. **Prompt efectivo** — prompt key/version, supplier config id/version, protected contract key/version, hash efectivo, composición disponible (no full prompt body).
3. **Fallback y advertencias** — fallback tri-state (`Sí` / `No` / `No informado`), motivo, lista de advertencias.
4. **Referencias visuales** — fuente, conteo, flags tri-state, bloque `reference_usage` cuando existe, IDs; texto auxiliar si `inventory_visual_references_used` es null.
5. **Fuentes de metadata** — chips por fuente (éxito si disponible).
6. **Metadata faltante** — alerta informativa + lista de claves; mensaje cuando la lista está vacía.

---

## 6. Safety behavior

- No field renders full **protected prompt text**; contract fields are metadata/hashes only.
- Partial responses: **info** alert for missing keys, not a hard error state for the whole panel.
- `null` vs `false` vs `true` distinguished per spec for fallback and inventory visual refs.

---

## 7. i18n

New keys (Spanish runtime bundle):

- `jobs.obs_tab_auditability`
- `observability.auditability.*` (title, section labels, source labels, loading/error, tri-state labels, missing-metadata copy, inventory visual refs hint)

`check:i18n` **passed** after adding keys.

---

## 8. Tests and validation

| Command | Result |
|---------|--------|
| `npm run typecheck` | Pass |
| `npm run lint` | Pass |
| `npm run check:i18n` | Pass |
| `npm run build` | Pass |
| `npm test -- --run jobAuditability JobAuditability useJobAuditability` | Pass |
| `npm test -- --run InventoryDetail` | Pass (includes new tab test) |

---

## 9. Remaining gaps

- No H4 metrics backend or SQL audit persistence.
- No dedicated permissions model beyond existing authenticated observability page.
- No `GET /api/v3/jobs/{job_id}/auditability` shortcut on the frontend (path follows inventory/aisle/job).
- English `translation.json` not updated (runtime is Spanish-only per `i18n/index.ts`).

---

## 10. Final recommendation for next phase

Recommend **H4 — additive audit persistence** (optional SQL columns for rollups) **or** **H4 metrics backend** if product priority is dashboards before more UI polish. Alternatively **Phase H final review** if observability scope is considered sufficient for the current release train.
