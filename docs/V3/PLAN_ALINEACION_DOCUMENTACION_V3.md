# Feature Plan — Alineación y corrección de documentación V3.0

## Summary

Plan de trabajo para **alinear y corregir** el conjunto de documentación de Dinamic Inventory v3.0 antes de iniciar la implementación. No se implementa código; se identifican inconsistencias arquitectónicas, terminología ambigua y desalineaciones frontend/backend, y se define un conjunto de correcciones por documento y un orden de edición recomendado.

---

## Scope & Non-goals

- **In scope:** Los cinco documentos listados; decisiones finales recomendadas para convergencia; matriz de inconsistencias; correcciones por archivo; orden de edición; riesgos de no alinear; preguntas abiertas que requieren confirmación humana.
- **Out of scope:** Reescribir los documentos completos; generar código de producción; cambiar el alcance funcional de la v3.0; definir v3.1/v3.2 en detalle.

---

## Pipeline Placement

Este plan no altera el pipeline técnico (detección → tracking → identificación → consolidación → reporte). Afecta únicamente a la documentación que describe el **contrato** entre pipeline y dominio (mapeo a Position/ProductRecord/Evidence), la API expuesta al frontend y el modelo de dominio (Inventory, Aisle, Position, etc.).

---

## A. Executive summary

La documentación v3.0 tiene **dirección correcta** pero presenta:

1. **Frontend:** Desacuerdo sobre tabla compleja (TanStack Table vs MUI Data Grid); Documento técnico sugiere "biblioteca UI liviana o componentes propios" y TanStack Table, mientras Regla de estilos y FRONTEND_ESTRUCTURA establecen MUI Data Grid como estándar. El Backlog incluye ejemplos con clases Tailwind (`className="grid grid-cols-3"`) y estructura `interfaces/web/src/` que puede interpretarse como frontend bajo backend.
2. **Dominio:** Uso inconsistente de "posición/pallet" y falta de definición explícita única de **Position** (unidad revisable = pallet lógico detectado). No hay una sección única que fije transiciones de estado para Inventory, Aisle y Position.
3. **Contrato pipeline→dominio:** La forma mínima de `positions[]`, productos, evidencias y flags (`needs_review`, `confidence`) no está definida en un solo lugar reutilizable por el equipo de backend y el mapeador.
4. **Métricas:** Fórmula de `success_rate` y población de `auto_accepted` / `total_reviewed` aparecen con redacciones ligeramente distintas; no hay definición canónica de `correction_rate`, `deletion_rate` ni momento de cálculo.
5. **Errores:** No hay modelo explícito de error operativo (`error_code`, `error_message`, `retryable`) ni guía de cómo reflejar fallos a nivel Aisle/Inventory sin exponer jobs.
6. **Queries/tablas:** Paginación, filtros por `status`, `needs_review`, confianza y búsqueda por SKU se mencionan de forma dispersa sin especificación de API (query params, valores permitidos).

**Objetivo del plan:** Dejar un conjunto de documentos coherente en frontend, dominio, estados, contrato pipeline-dominio, métricas, errores y queries, con decisiones finales explícitas y un orden de edición que evite retrabajo.

---

## B. Cross-document inconsistency matrix

| Inconsistency | Affected files | Why it matters | Recommended correction |
|---------------|----------------|----------------|-------------------------|
| **Tabla compleja: TanStack Table vs MUI Data Grid** | Documento técnico 3.0 (§13), V3.0.md (Fase 6), FRONTEND_ESTRUCTURA.md, Regla de estilos | Implementación puede duplicar esfuerzo o elegir opción no estándar. | Unificar: **MUI Data Grid** como solución oficial para tablas complejas. Quitar "TanStack Table" y "grilla similar" como alternativas iguales; dejar TanStack Table solo como mención opcional para tablas muy simples si se desea. |
| **Stack frontend: "UI liviana" vs MUI** | Documento técnico 3.0 (§13) | "biblioteca UI liviana o componentes propios simples" contradice MUI como base. | Sustituir por: React, TypeScript, React Router, TanStack Query, **Material UI**, **MUI Data Grid** para tablas complejas. Eliminar "UI liviana" y "componentes propios simples" como opción principal. |
| **Ubicación del frontend** | Backlog (§ Estructura sugerida): `interfaces/web/src/` bajo backend | Puede interpretarse como frontend dentro de backend. | En todos los docs: frontend en **raíz del repo**, carpeta **`frontend/`**. Backlog: reemplazar `interfaces/web/` por referencia a "ver FRONTEND_ESTRUCTURA.md" y `frontend/`. |
| **Ejemplos de código con Tailwind / classNames no MUI** | Backlog (EvidenceGallery, MetricsCards, PositionsTable, etc.) | Regla de estilos prohíbe Tailwind y clases arbitrarias. | Reemplazar ejemplos con componentes MUI (Grid, Box, Card, Table/DataGrid). Quitar `className="grid grid-cols-3"` y similares; usar `Grid`, `Stack`, `sx`. |
| **Position: "posición" vs "pallet lógico"** | V3.0.md, Documento técnico, Backlog | Ambiguidad: ¿Position = slot físico o detección? | Definir en un solo párrafo canónico: "Position es la **unidad revisable** de v3.0; en esta versión equivale a un **pallet lógico detectado** (una detección por pipeline), no a un slot físico del depósito." Repetir o referenciar en los tres docs de dominio. |
| **Transiciones de estado no documentadas** | Documento técnico, V3.0 | Solo se listan estados; no cuándo pasar de uno a otro. | Añadir subsección "Transiciones" por entidad (Inventory, Aisle, Position) en Documento técnico; resumir en V3.0. Ej.: Inventory: draft→processing (al encolar primer pasillo), processing→in_review (todos pasillos processed), in_review→completed (cierre manual). |
| **Diferencia reviewed / corrected / deleted (Position)** | Varios | No está claro si "reviewed" es solo confirmación y "corrected" implica cambio de datos. | Fijar: `reviewed` = usuario confirmó sin cambios; `corrected` = hubo cambio de cantidad/SKU; `deleted` = eliminación lógica. Transiciones: detected → reviewed | corrected | deleted solo por acciones de revisión. |
| **Métricas: fórmula y población** | Documento técnico (§18), V3.0 (§Fase 8), Backlog (HU-9.1) | "total_reviewed_positions" vs "total" y momento de cálculo. | Definir en Documento técnico (y referenciar en V3.0/Backlog): `total_reviewed_positions = count(positions where status in (reviewed, corrected, deleted))`; `auto_accepted = count(reviewed)`; `success_rate = auto_accepted / total_reviewed * 100` si total_reviewed > 0, si no 0. Incluir `correction_rate`, `deletion_rate` como porcentajes sobre total_reviewed. |
| **Contrato pipeline→dominio sin forma mínima** | Documento técnico (Fase 4), V3.0 (Fase 4) | El mapeador no tiene un contrato único. | Añadir sección "Contrato de salida del pipeline para el mapeador": estructura mínima de `positions[]` (id, confidence, needs_review, primary_evidence_id, products[] con sku, quantity, confidence), evidencias referenciadas por id, campos obligatorios vs opcionales. |
| **Error operativo y reflejo en Aisle/Inventory** | Ningún doc lo define explícito | La UI y el backend no tienen guía para errores. | Añadir en Documento técnico (y resumir en V3.0): modelo de error operativo: `error_code`, `error_message`, `retryable`; que el frontend consuma errores a nivel Aisle (ej. aisle.status=failed, aisle.error_summary); no exponer job_id/error crudo como recurso principal. |
| **Paginación y filtros de GET /aisles/{id}/positions** | V3.0 (Fase 5), Backlog (HU-7.1) | "Soporta paginable" y "filtros" sin especificación. | Documentar en Documento técnico y API: query params `page`, `page_size` (o limit/offset); `status`, `needs_review`, `min_confidence`; `sku` (búsqueda en productos de la posición). Valores permitidos de `status`. |
| **SourceAsset en Documento técnico vs "assets" en texto** | Documento técnico, V3.0 | Término a veces "SourceAsset", a veces "assets". | Mantener entidad `SourceAsset`; en prosa permitir "assets del pasillo" como sinónimo. Aclarar en glosario o nota: "Los archivos subidos se modelan como SourceAsset (photo/video)." |

---

## C. Recommended corrections by file

### C.1 Documento tecnico - 3.0.md

| Action | Detail |
|--------|--------|
| **Correct** | §13 Stack sugerido: quitar "TanStack Table" y "biblioteca UI liviana o componentes propios simples". Dejar: React, TypeScript, React Router, TanStack Query, **Material UI**, **MUI Data Grid** para tablas complejas. |
| **Correct** | §7.1–7.2 (Inventory, Aisle): añadir subsección "Transiciones de estado" con reglas (ej. draft→processing, processing→in_review→completed; Aisle: created→assets_uploaded→queued→processing→processed→in_review→completed). |
| **Correct** | §7.4 Position: añadir párrafo canónico: "Position es la unidad revisable; en v3.0 equivale a un pallet lógico detectado." Añadir transiciones: detected → (reviewed | corrected | deleted) solo vía ReviewAction. |
| **Clarify** | §7.4 Estados: definir explícitamente reviewed = confirmado sin cambios, corrected = con cambio de cantidad/SKU, deleted = eliminación lógica. |
| **Add** | Nueva sección "Contrato de salida del pipeline para el mapeador": estructura mínima de `positions[]`, `products[]`, referencias a evidencias, obligatorios vs opcionales. |
| **Add** | Nueva subsección en §12 o §5: "Modelo de error operativo": error_code, error_message, retryable; reflejo en Aisle (status=failed, error_summary); no exponer job como recurso principal. |
| **Add** | §8 Fase 5 / API: paginación y filtros de `GET /aisles/{aisleId}/positions` (page, page_size, status, needs_review, min_confidence, sku). |
| **Add** | §18 Métricas: definición canónica de total_reviewed_positions, auto_accepted_positions, success_rate, correction_rate, deletion_rate y momento de cálculo. |
| **Unchanged** | Modelo de dominio (entidades), SOLID (§6), contratos (§9), fases y endpoints base. |

### C.2 V3.0.md

| Action | Detail |
|--------|--------|
| **Correct** | Fase 6 Stack: reemplazar "TanStack Table o grilla similar" por "MUI Data Grid para tablas complejas". Mantener React, TypeScript, React Router, TanStack Query. |
| **Clarify** | §4.3 Position: usar el mismo párrafo canónico que en Documento técnico (unidad revisable = pallet lógico detectado). |
| **Clarify** | §5.2 "usar Position como pallet lógico": referenciar la definición canónica del Documento técnico para evitar duplicación. |
| **Add** | Breve referencia a transiciones de estado: "Ver Documento técnico §7 para transiciones de Inventory, Aisle y Position." |
| **Add** | En Fase 5 Consideraciones: referenciar especificación de paginación y filtros del Documento técnico. |
| **Add** | Fórmula de éxito y métricas: referenciar definición canónica del Documento técnico (evitar duplicar fórmula). |
| **Unchanged** | Objetivos, alcance, fases generales, historias de usuario, criterios de éxito. |

### C.3 V3.0 - Backlog.md

| Action | Detail |
|--------|--------|
| **Correct** | Estructura sugerida del proyecto: quitar `interfaces/web/src/` con frontend dentro. Reemplazar por "Frontend: ver FRONTEND_ESTRUCTURA.md; app en `frontend/` en la raíz del repo." |
| **Correct** | Ejemplos React/TS: eliminar uso de Tailwind/className (grid-cols-3, etc.). Usar MUI (Grid, Box, Card, Table o Data Grid) y `sx` donde corresponda. |
| **Correct** | HU-10.2 / tabla de posiciones: indicar que la tabla debe implementarse con MUI Data Grid (referencia a Regla de estilos). |
| **Clarify** | HU-6.1 / ResultMapper: que el formato de entrada del mapper cumpla el "Contrato de salida del pipeline" definido en Documento técnico. |
| **Clarify** | HU-9.1 métricas: que el cálculo siga la definición canónica de métricas del Documento técnico. |
| **Unchanged** | Épicas, HUs, criterios de aceptación, código Python de casos de uso y repositorios, orden de sprints. |

### C.4 FRONTEND_ESTRUCTURA.md

| Action | Detail |
|--------|--------|
| **Correct** | § Stack: quitar "(o TanStack Table)" como alternativa igual. Dejar "MUI Data Grid para tablas complejas" como única opción oficial; opcionalmente una frase: "Para tablas muy simples puede usarse Table de MUI; para listas operativas con filtros y paginación se usa MUI Data Grid." |
| **Clarify** | Que la estructura `frontend/` en la raíz es la **única** ubicación oficial del frontend (ya está bien; reforzar en resumen). |
| **Unchanged** | Estructura de carpetas, api/, features/, pages/, hooks/, theme/, types/, deployment, .gitignore. |

### C.5 V3.0 - FrontEnd - Regla de estilos.md

| Action | Detail |
|--------|--------|
| **Clarify** | §3 Stack: ya dice "MUI Data Grid para tablas complejas"; añadir una línea: "No se debe usar TanStack Table como sustituto de MUI Data Grid en vistas operativas de posiciones, inventarios o pasillos." |
| **Unchanged** | Resto del documento (MUI, sx, theme, componentes, accesibilidad, SOLID en UI). |

---

## D. Proposed final decisions

Todas las referencias en la documentación deben converger a lo siguiente:

| Topic | Final decision |
|-------|----------------|
| **Ubicación del frontend** | Carpeta **`frontend/`** en la **raíz del repositorio**. No bajo `src/` ni `interfaces/web/`. |
| **Librería de UI** | **Material UI (MUI)** como base oficial. Sin Tailwind, CSS Modules globales ni otra librería de estilos paralela sin justificación. |
| **Tablas complejas** | **MUI Data Grid** para tablas operativas (posiciones, inventarios, pasillos, productos, historial de revisión). TanStack Table no es alternativa equivalente para estas vistas. |
| **Significado de Position** | **Position** es la **unidad revisable** de v3.0. En v3.0 equivale a un **pallet lógico detectado** (una detección del pipeline). No es un slot físico del depósito. |
| **Rol de Job** | **Job** es entidad **técnica e interna**. Asociado a Aisle (`target_type=aisle`, `target_id=aisle_id`). El frontend **no** expone jobs como recurso principal; consulta estado del **pasillo**. |
| **Métricas** | **total_reviewed_positions** = posiciones con status reviewed, corrected o deleted. **auto_accepted** = reviewed. **success_rate** = auto_accepted / total_reviewed * 100 (0 si total_reviewed=0). **correction_rate** y **deletion_rate** como % sobre total_reviewed. Cálculo en tiempo de consulta (GET /inventories/{id}/metrics). |
| **Transiciones de estado** | Definidas por documento en Documento técnico §7: Inventory (draft→processing→in_review→completed; failed); Aisle (created→assets_uploaded→queued→processing→processed→in_review→completed; failed); Position (detected→reviewed|corrected|deleted solo por revisión). |
| **Error operativo** | Modelo con **error_code**, **error_message**, **retryable**. Fallos reflejados a nivel **Aisle** (y derivable a Inventory): p. ej. aisle.status=failed, aisle.error_summary. No exponer job_id ni stack interno al frontend como recurso principal. |

---

## E. Suggested editing order

1. **Documento tecnico - 3.0.md**  
   Primero: es la referencia de dominio, contratos, estados y API. Añadir transiciones, definición canónica de Position, contrato pipeline→dominio, modelo de error, métricas canónicas y parámetros de query de positions. Corregir §13 stack frontend.

2. **V3.0.md**  
   Segundo: alinear con el Documento técnico. Cambiar Fase 6 stack a MUI Data Grid; añadir referencias a transiciones, métricas y Position; no duplicar fórmulas.

3. **V3.0 - FrontEnd - Regla de estilos.md**  
   Tercero: refuerzo explícito de MUI Data Grid y prohibición de TanStack Table como sustituto en vistas operativas (cambio mínimo).

4. **FRONTEND_ESTRUCTURA.md**  
   Cuarto: quitar "(o TanStack Table)"; dejar MUI Data Grid como estándar; reforzar que `frontend/` es la única ubicación.

5. **V3.0 - Backlog.md**  
   Quinto: corregir estructura del proyecto (frontend en raíz); reemplazar ejemplos con Tailwind por MUI; referenciar Documento técnico para contrato del mapper y métricas; indicar MUI Data Grid para tabla de posiciones.

Este orden evita tener que reescribir el Backlog antes de que el Documento técnico fije contrato y estados, y mantiene la Regla de estilos y FRONTEND_ESTRUCTURA como fuentes de verdad de UI antes de tocar ejemplos en el Backlog.

---

## F. Risks if documents are not aligned

| Risk | Consequence | Mitigation |
|------|-------------|------------|
| **Dos implementaciones de tabla** | Un equipo usa MUI Data Grid y otro TanStack Table; duplicación o refactor. | Unificar en docs; un solo estándar (MUI Data Grid). |
| **Frontend bajo backend** | Estructura `interfaces/web/` o `src/web/`; mezcla de responsabilidades y deploy. | Fijar `frontend/` en raíz en todos los docs. |
| **Position ambiguo** | Backend modela "slot físico" y frontend espera "detección"; desalineación de API y revisión. | Definición canónica única (pallet lógico detectado). |
| **Transiciones implícitas** | Implementación inventa reglas (ej. cuándo pasa Inventory a in_review); comportamiento inconsistente. | Documentar transiciones en Documento técnico. |
| **Métricas distintas entre pantalla y API** | Fórmulas diferentes en backend y en doc; métricas que no cuadran. | Una definición canónica; referenciarla desde V3.0 y Backlog. |
| **Errores solo a nivel job** | UI muestra job_id o error crudo; mala UX y posible filtración de detalle interno. | Modelo de error operativo y reflejo en Aisle/Inventory. |
| **API de positions sin contrato** | Paginación y filtros inventados por desarrollador; breaking changes después. | Especificar query params y valores en Documento técnico. |

---

## G. Open questions

Solo preguntas que requieren **decisión de producto o arquitecto** (no resolubles solo por redacción):

1. **Inventory.status "processing"**: ¿Se pone en `processing` cuando **al menos un** pasillo está en cola/procesando, o solo cuando **todos** los pasillos están en ese estado? (Recomendación: al menos uno.)
2. **Cierre de inventario**: ¿El paso a `completed` es **automático** cuando todos los pasillos están `completed`, o requiere una acción explícita de "Cerrar inventario" en la UI? (Recomendación: acción explícita para permitir revisión final.)
3. **Paginación por defecto**: Para `GET /aisles/{aisleId}/positions`, ¿valores por defecto acordados de `page` y `page_size`? (Recomendación: page=1, page_size=25 o 50.)
4. **error_code**: ¿Lista cerrada de códigos (ej. ASSET_UPLOAD_FAILED, PIPELINE_FAILED, TIMEOUT) o libre por implementación? (Recomendación: lista cerrada en Documento técnico para consistencia de UI.)

---

## Proposed Design (for documentation work)

- **Single source of truth for domain and API:** Documento técnico 3.0.
- **Single source of truth for frontend structure and stack:** FRONTEND_ESTRUCTURA.md + Regla de estilos (MUI + MUI Data Grid).
- **Backlog:** Referencias a los anteriores; ejemplos de código alineados con MUI y con contrato del Documento técnico; sin frontend bajo `interfaces/web/`.

No se introducen nuevos documentos; se corrigen y completan los cinco existentes según la matriz y las correcciones por archivo.

---

## Config / Flags

N/A (plan de documentación; no hay feature flags).

---

## Files / Modules Impacted

Solo documentación:

- `docs/V3/Documento tecnico - 3.0.md`
- `docs/V3/V3.0.md`
- `docs/V3/V3.0 - Backlog.md`
- `docs/V3/FRONTEND_ESTRUCTURA.md`
- `docs/V3/V3.0 - FrontEnd - Regla de estilos.md`

---

## Task Breakdown (ordered)

1. **Doc-1** — Documento técnico: añadir transiciones de estado (§7.1, 7.2, 7.4) y definición canónica de Position.
2. **Doc-2** — Documento técnico: añadir sección "Contrato de salida del pipeline para el mapeador".
3. **Doc-3** — Documento técnico: añadir modelo de error operativo y reflejo en Aisle/Inventory.
4. **Doc-4** — Documento técnico: especificar paginación y filtros de GET /aisles/{id}/positions; métricas canónicas.
5. **Doc-5** — Documento técnico: corregir §13 stack frontend (MUI, MUI Data Grid; quitar TanStack Table y "UI liviana").
6. **Doc-6** — V3.0.md: alinear Fase 6 stack, Position, transiciones, métricas y filtros con Documento técnico.
7. **Doc-7** — Regla de estilos: añadir línea explícita sobre MUI Data Grid y no usar TanStack Table como sustituto en vistas operativas.
8. **Doc-8** — FRONTEND_ESTRUCTURA: quitar alternativa TanStack Table; reforzar MUI Data Grid y ubicación `frontend/`.
9. **Doc-9** — Backlog: estructura del proyecto (frontend en raíz); ejemplos React con MUI; referencias a contrato y métricas; MUI Data Grid para tabla de posiciones.

---

## Acceptance Criteria

- [ ] Los cinco documentos nombran la misma ubicación del frontend (`frontend/` en la raíz).
- [ ] Los cinco documentos coinciden en stack: React, TypeScript, MUI, React Router, TanStack Query, MUI Data Grid para tablas complejas; sin "TanStack Table" ni "UI liviana" como estándar.
- [ ] Documento técnico contiene definición canónica de Position (unidad revisable = pallet lógico detectado) y transiciones de estado para Inventory, Aisle y Position.
- [ ] Documento técnico contiene contrato de salida del pipeline (forma mínima de positions/products/evidence) y modelo de error operativo.
- [ ] Documento técnico contiene especificación de query params de GET /aisles/{id}/positions y definición canónica de métricas.
- [ ] Backlog no contiene ejemplos con Tailwind/className no MUI; estructura del proyecto no coloca frontend bajo `interfaces/web/`.
- [ ] V3.0 y Backlog referencian al Documento técnico para contrato, métricas y estados en lugar de duplicar definiciones.

---

## Risks & De-risk Plan

| Risk | De-risk |
|------|---------|
| Ediciones contradictorias entre autores | Orden de edición estricto (Documento técnico primero; luego V3.0, Regla, FRONTEND, Backlog). |
| Preguntas abiertas bloquean correcciones | Resolver solo las cuatro listadas en §G; el resto se puede documentar con la recomendación indicada y una nota "Decisión: ver Open Questions". |
| Contrato pipeline demasiado rígido | Definir forma **mínima** y marcar campos opcionales; el pipeline actual puede tener más campos que el mapper ignore. |

---

## Notes / Open Questions

- Las **open questions** de §G deben resolverse con producto/arquitecto antes o en paralelo a la edición; si se dejan abiertas, documentar la recomendación como "recomendado" y la alternativa como "pendiente de confirmación".
- Después de aplicar este plan, un **revisor** debería hacer una pasada de consistencia (búsqueda de "TanStack Table", "pallet", "Position", "success_rate", "frontend", "interfaces/web") para asegurar que no queden restos de redacciones antiguas.

---

## Recommended next step

**These open decisions should be resolved first.**  

Resolver las cuatro preguntas de §G (cuándo Inventory pasa a processing, cierre explícito o automático, paginación por defecto, lista cerrada de error_code) en una sesión corta con producto/arquitecto. Con esas respuestas, incorporarlas en la primera edición del Documento técnico y luego ejecutar el orden de edición (Doc-1 a Doc-9). Si no se pueden cerrar las cuatro de inmediato, se puede documentar las recomendaciones como valor por defecto y marcar "Pendiente confirmación" para las alternativas; en ese caso, **documentation can now be corrected** siguiendo el plan y dejando las open questions como notas explícitas en el Documento técnico.
