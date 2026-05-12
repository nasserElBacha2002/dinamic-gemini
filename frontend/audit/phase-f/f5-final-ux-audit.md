# F5 — Final UX audit (Phase F closure)

**Date:** 2026-05-11  
**Method:** Static review of `frontend/src` routes, pages, dialogs, observability workspace, and automated test coverage. **No manual browser QA** was executed in this environment.

---

## 1.1 Navigation and information architecture

| Flow | Evidence | Status |
|------|------------|--------|
| Clientes (`/clientes`) | `App.tsx` → `ROUTE_PATH.clients` → `ClientsList` | OK |
| Detalle de cliente | `pathToClient(clientId)`, `ClientDetail` | OK |
| Detalle de proveedor | `pathToClientSupplier`, `ClientSupplierDetail` | OK |
| Inventarios del cliente | `ClientDetail` section + `useInventoriesList` filtered by `client_id` | OK |
| Detalle de inventario | `pathToInventory`, `InventoryDetail` | OK |
| Pasillos | `InventoryAislesSection` en `InventoryDetail` | OK |
| Observabilidad (página) | Ruta dedicada + `AisleObservabilityPage` / `AisleObservabilityWorkspace` (no depende solo de modal como flujo principal) | OK |
| Breadcrumbs / volver | `PageHeader` en cliente, proveedor, inventario; enlaces “Volver…” donde aplica | OK |

**Orphans:** Ninguna pantalla revisada queda sin camino de retorno hacia listados o detalle padre razonable.

---

## 1.2 Client detail UX

**Archivo principal:** `frontend/src/pages/ClientDetail.tsx`

| Expectativa | Estado |
|-------------|--------|
| Información del cliente | OK (`SectionCard` + campos) |
| Proveedores asociados | OK (`DataTable` + crear proveedor) |
| Inventarios asociados | OK (tabla filtrada + crear inventario) |
| Sin acciones duplicadas de prompts/imágenes en tabla de proveedores | OK — solo columnas proveedor/estado/fechas + nombre como `RouterLink` |
| Nombre de proveedor clicable | OK → `pathToClientSupplier` |

**Cadenas que no deben aparecer en la tabla:** no hay botones “Configurar instrucciones”, “Gestionar imágenes”, etc. (verificado en código y tests).

---

## 1.3 Supplier detail UX

**Archivo:** `frontend/src/pages/ClientSupplierDetail.tsx`

| Pestaña | Contenido | Estado |
|---------|-----------|--------|
| Resumen | Cliente, estado, fechas, línea de prompt activo / vacío, conteo referencias | OK |
| Prompts | `SupplierPromptConfigsModule` `presentation="inline"` | OK |
| Imágenes de referencia | Texto de ayuda + `SupplierReferenceImagesModule` `presentation="inline"` | OK |

**Botones “Gestionar prompts” / “Gestionar imágenes de referencia”:** no se renderizan en la página de detalle; la gestión es por pestaña.

**Deep link:** `?tab=prompts`, `?tab=imagenes` (Resumen = sin query o valor por defecto).

---

## 1.4 Inventory / aisle UX

| Expectativa | Evidencia | Notas |
|-------------|-----------|--------|
| Inventario sin cliente | `Alert` con `inventory.legacy_no_client_warning` | OK |
| Columna proveedor del pasillo | `InventoryAislesSection` + `inventory.column_aisle_supplier` | OK |
| Fallback sin proveedor / sin cliente para enlace | `inventory.aisle_supplier_assigned_no_nav`, `inventory.aisle_no_supplier` | OK |
| Procesar pasillo | `AisleProcessingDialog` + menú de fila | OK |

**Literal “Cliente asociado”:** el encabezado de inventario muestra breadcrumbs con nombre de cliente cuando hay `client_id`; no hay un chip con ese texto exacto — equivalente funcional vía navegación y contexto.

---

## 1.5 Process dialog UX

**Componente:** `frontend/src/features/inventories/components/AisleProcessingDialog.tsx` (invocado desde `InventoryDetail`).

**Tests:** `InventoryDetailPage.test.tsx` — caso *“process dialog explains automatic prompt and does not show advanced prompt controls”*.

| Debe verse | Estado |
|------------|--------|
| Título tipo “Procesar pasillo …”, proveedor/modelo, “Prompt utilizado”, texto de prompt automático + proveedor | OK en tests |
| No “Opciones avanzadas”, “Perfil base del prompt”, selectores de perfiles A/B | OK en tests |
| Envío con `promptKey: null` en modo test | OK en tests |

Claves i18n legacy (`aisle.process_advanced_options`, etc.) **siguen en JSON** para compatibilidad pero el script `check:i18n` las marca como no referenciadas estáticamente — coherente con UI retirada.

---

## 1.6 Observability page UX

**Componentes:** `AisleObservabilityWorkspace.tsx`, `ExecutionLogPanel.tsx`, util `executionLogProviderTitle.ts`.

| Expectativa | Estado |
|-------------|--------|
| Página completa (no solo modal) | Ruta dedicada + workspace | OK |
| Título dinámico por proveedor (“Solicitud a Claude”, “Solicitud a Gemini”, …) | `provider_request_title_named` + `formatProviderBrandLabel` | OK |
| Claude ≠ Gemini en título | `ExecutionLogPanel.test.tsx` | OK |
| Adjuntos: evidencia principal vs referencias | `execution_log.primary_evidence` + sección de referencias | OK |
| Roles crudos en UI de operador | Comparación por `role` en código; etiquetas vía `t(...)` | OK para bloques revisados |

**JSON crudo / depuración:** paneles técnicos pueden seguir mostrando payloads sin traducir; es deuda aceptada de baja severidad (ver cierre F5).

---

## Resumen

La arquitectura de información Phase F (clientes → proveedor → inventario → pasillos → observabilidad) está **alineada con el código y los tests automatizados**. La QA manual en navegador **no se ejecutó** en este entorno.
