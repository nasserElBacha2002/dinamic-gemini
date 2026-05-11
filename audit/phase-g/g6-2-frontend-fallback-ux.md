# G6.2 — Frontend fallback visibility and blocking UX

## 1. Executive summary

**Status: `G6_2_READY_FOR_G6_3`**

Spanish UX now surfaces **missing active supplier prompt** at supplier detail (404 from active prompt query) and aligns **trace tab** fallback reasons with **backend enum strings** (`INVENTORY_WITHOUT_CLIENT`, `AISLE_WITHOUT_CLIENT_SUPPLIER`, `NO_ACTIVE_SUPPLIER_PROMPT_CONFIG`). When execution logs expose **`resolution_status=error`** with **`resolution_error_code`**, the trace tab shows a **Spanish** explanation for **`NO_ACTIVE_SUPPLIER_PROMPT_CONFIG`**.

## 2. UX behavior implemented

| Surface | Change |
| --- | --- |
| **Client → Supplier** | Warning **`Alert`** when active prompt API returns **404** |
| **Aisle observability → trace** | Fallback reason map fixed + error detail line for resolver errors |

## 3. Frontend changes

- **`ClientSupplierDetail.tsx`**: `Alert` + **`role="status"`** for accessibility.
- **`AisleObservabilityWorkspace.tsx`**: **`translateFallbackReason`** keys + **`translateResolutionErrorCode`**; error **`Typography`** when **`resolution_status === error`**.

## 4. i18n changes

- **`frontend/src/i18n/locales/es/translation.json`**: `clients.supplier_page.prompt_required_warning`, `jobs.trace_fb_no_active_supplier_prompt_config`, `jobs.trace_resolution_error_detail`, `jobs.trace_err_no_active_supplier_prompt_config`, `jobs.trace_err_resolution_other`.

## 5. Tests updated

- **`ClientSupplierDetailPage.test.tsx`**: “shows warning when active prompt query returns 404”.

## 6. Validation results

See **`audit/raw/phase-g/g6-3-validation.txt`**.

## 7. Risks / observations

- English locale files are not fully expanded for new keys (app primary language is Spanish).
