# **Nuevo plan de implementación para Dinamic Inventory v3**

## **Objetivo general**

Implementar una nueva experiencia de producto para Dinamic Inventory v3, alineando primero:

* modelo de datos  
* contratos backend/frontend  
* pantallas objetivo  
* componentes UI reutilizables

y recién después avanzar con la implementación en Material UI.

La meta no es solo rehacer la UI, sino asegurar que:

* las pantallas muestren los datos correctos  
* los contratos estén orientados a frontend  
* los estados sean claros  
* no haya lógica de negocio mal resuelta del lado cliente  
* la nueva interfaz pueda escalar bien

---

# **Fase 0 — Alineación funcional previa**

## **Objetivo**

Validar que la estructura actual de DB y API soporte correctamente la experiencia objetivo del producto.

## **Resultado esperado**

Tener claridad sobre:

* qué datos existen hoy  
* cómo están modelados  
* qué contratos existen hoy  
* qué gaps hay con respecto a la UI objetivo  
* qué cambios hay que hacer antes de tocar fuerte frontend

---

## **Sprint 0.1 — Auditoría de pantallas objetivo**

### **Objetivo**

Cerrar de forma definitiva el mapa de pantallas y sus propósitos.

### **Entregable**

Lista cerrada de pantallas objetivo:

* Login  
* Dashboard  
* Inventories  
* Create Inventory  
* Inventory Detail  
* Create Aisle  
* Aisle Results  
* Review Queue  
* Result Review Detail  
* Quick Review Drawer  
* Metrics / Analytics

### **Para cada pantalla, definir:**

* objetivo de negocio  
* usuario principal  
* acciones principales  
* datos que necesita mostrar  
* datos secundarios  
* métricas necesarias  
* filtros necesarios  
* acciones por fila o por entidad

### **Criterio de cierre**

No se empieza a revisar contratos sin saber exactamente qué necesita cada vista.

---

## **Sprint 0.2 — Auditoría del modelo de datos actual**

### **Objetivo**

Revisar si la base actual representa bien el producto que queremos construir.

### **Entidades a revisar**

* Inventory  
* Aisle  
* Job / Processing  
* Result / Position  
* Evidence  
* ReviewAction / Audit  
* Visual references  
* Resúmenes / métricas derivadas

### **Qué revisar en cada entidad**

* propósito real de la entidad  
* campos actuales  
* naming  
* relaciones  
* timestamps  
* estados  
* flags  
* duplicaciones  
* datos técnicos vs datos útiles para UI

### **Preguntas que tiene que responder esta revisión**

* ¿La entidad representa bien el problema de negocio?  
* ¿Los estados son claros?  
* ¿Hay campos ambiguos o redundantes?  
* ¿El frontend podría construir una buena UI solo con esta estructura?  
* ¿Qué datos faltan para las nuevas vistas?

### **Entregable**

Diagnóstico por entidad con:

* lo que está bien  
* lo que sobra  
* lo que falta  
* lo que conviene renombrar  
* lo que conviene separar

### **Criterio de cierre**

Poder decir con seguridad si el modelo actual soporta o no la UI objetivo.

---

## **Sprint 0.3 — Auditoría de contratos actuales**

### **Objetivo**

Evaluar si las respuestas del backend están orientadas a pantalla o si son demasiado crudas/técnicas.

### **Contratos a revisar**

* login/auth  
* inventories list  
* inventory detail  
* aisles list / aisle detail  
* process/job responses  
* results list  
* result detail  
* evidence  
* review actions  
* metrics / summaries

### **Qué analizar**

* naming de campos  
* consistencia entre endpoints  
* listas vs detalles  
* datos faltantes  
* datos sobrantes  
* agregados faltantes  
* flags derivados útiles para UI  
* soporte para filtros/sort/paginación

### **Preguntas clave**

* ¿El contrato devuelve “entidad interna” o “respuesta útil para pantalla”?  
* ¿Hay contratos que obligan al frontend a hacer demasiada lógica?  
* ¿Los listados ya vienen listos para tabla?  
* ¿Los detalles ya vienen listos para vista de revisión?  
* ¿Existen contratos adecuados para dashboard y review queue?

### **Entregable**

Mapa de contratos actual con:

* endpoint  
* uso actual  
* pantalla destino  
* problemas  
* cambios sugeridos

### **Criterio de cierre**

Saber exactamente qué contratos sirven y cuáles hay que rediseñar.

---

## **Sprint 0.4 — Matriz pantalla → datos → contrato**

### **Objetivo**

Cruzar producto, DB y API en una sola visión.

### **Estructura recomendada**

Para cada pantalla:

* pantalla  
* datos que necesita  
* endpoint actual  
* campos disponibles  
* campos faltantes  
* lógica que hoy cae en frontend  
* cambios requeridos

### **Ejemplo conceptual**

#### **Inventories**

Necesita:

* inventory name  
* status  
* created date  
* aisles count  
* pending review count  
* last activity

Validar:

* si existe `pending_review_count`  
* si existe `last_activity_at`  
* si hay que calcularlo  
* si hoy el endpoint solo devuelve lo básico

#### **Review Queue**

Necesita:

* priority  
* sku  
* quantity  
* confidence  
* traceability  
* review status  
* inventory  
* aisle  
* updated  
* evidence presence

Validar:

* si hoy eso sale de un endpoint real  
* si hay que armar un summary endpoint específico  
* si el backend debería devolver `is_critical`, `has_evidence`, `display_status`

### **Entregable**

Matriz completa de gaps funcionales.

### **Criterio de cierre**

Tener una lista priorizada de ajustes backend antes de frontend.

---

## **Sprint 0.5 — Definición de contratos target**

### **Objetivo**

Diseñar cómo deberían ser los contratos ideales para soportar la nueva UI.

### **Principio**

El frontend no debería reconstruir el dominio desde cero.  
Debe recibir respuestas ya orientadas a pantalla.

### **Tipos de respuestas target a definir**

* list responses  
* detail responses  
* dashboard summaries  
* aisle summaries  
* review queue summaries  
* result review detail responses  
* metrics responses

### **Ejemplos de campos target útiles**

* `pending_review_count`  
* `has_errors`  
* `last_activity_at`  
* `primary_evidence_url`  
* `needs_review`  
* `is_critical`  
* `display_status`  
* `review_summary`  
* `traceability_status`  
* `current_quantity`  
* `system_quantity`  
* `corrected_quantity`

### **Entregable**

Contrato target por pantalla / caso de uso.

### **Criterio de cierre**

Poder empezar backend/UI con una estructura clara y estable.

---

# **Fase 1 — Alineación backend antes de UI**

## **Objetivo**

Ajustar backend y capa de datos para que soporten la nueva experiencia.

---

## **Sprint 1.1 — Normalización de estados y naming**

### **Objetivo**

Corregir inconsistencias estructurales que impactan directo en la UI.

### **Alcance**

* unificar nombres  
* revisar snake\_case vs camelCase según capa  
* formalizar taxonomía de estados  
* clarificar estados por entidad

### **Taxonomías a cerrar**

#### **Inventario**

* draft  
* in\_progress  
* completed  
* archived

#### **Pasillo**

* empty  
* assets\_uploaded  
* processing  
* processed  
* error

#### **Resultado**

* pending\_review  
* confirmed  
* corrected  
* deleted

#### **Calidad**

* valid\_traceability  
* invalid\_traceability  
* low\_confidence

### **Entregable**

Modelo semántico consistente para toda la plataforma.

---

## **Sprint 1.2 — Contratos de summary/listado**

### **Objetivo**

Crear o ajustar endpoints pensados para tablas y listados.

### **Casos prioritarios**

* dashboard summary  
* inventories list  
* inventory summary  
* aisles summary  
* review queue summary  
* aisle results summary

### **Principio**

Los listados tienen que venir listos para mostrarse, no obligar al frontend a inferir demasiado.

### **Entregable**

Endpoints o DTOs pensados para:

* cards  
* tablas  
* filtros  
* badges  
* prioridades

---

## **Sprint 1.3 — Contratos de detalle**

### **Objetivo**

Resolver bien las respuestas para vistas detalladas.

### **Casos prioritarios**

* inventory detail  
* result review detail  
* evidence detail  
* review history detail

### **Principio**

El detalle debe traer:

* resumen principal  
* contenido secundario  
* historial  
* metadata técnica opcional

### **Entregable**

Responses claramente estructuradas para pantalla detallada.

---

## **Sprint 1.4 — Filtros, sort y paginación**

### **Objetivo**

Preparar los endpoints para la nueva UI data-heavy.

### **Aplicar en:**

* inventories  
* aisles  
* aisle results  
* review queue  
* metrics tables

### **Entregable**

Capacidad de:

* búsqueda  
* filtros  
* ordenamiento  
* paginación real

---

## **Sprint 1.5 — Agregados y métricas**

### **Objetivo**

Crear la capa de datos necesaria para dashboard y analytics.

### **Casos a cubrir**

* KPIs globales  
* KPIs por inventario  
* KPIs por pasillo  
* KPIs de review  
* tasas de corrección  
* errores  
* actividad reciente

### **Entregable**

Responses preparadas para cards y analytics.

---

# **Fase 2 — Sistema UI base con Material UI**

## **Objetivo**

Construir primero la base reutilizable del producto.

---

## **Sprint 2.1 — Theme y sistema visual base**

### **Implementar**

* theme MUI  
* paleta neutra \+ semántica  
* tipografía  
* spacing  
* border radius  
* elevations  
* estados de hover/focus  
* botones base

### **Mantener**

* azul como primario de acción  
* verde como positivo  
* naranja como warning  
* rojo como error  
* gris como neutral

### **Entregable**

Base visual consistente para todo el sistema.

---

## **Sprint 2.2 — Layout principal**

### **Implementar**

* AppShell  
* Sidebar  
* Topbar  
* PageHeader  
* Breadcrumbs

### **Entregable**

Arquitectura persistente de navegación.

---

## **Sprint 2.3 — Componentes reutilizables base**

### **Implementar**

* StatusBadge  
* KpiCard  
* SectionCard  
* EmptyState  
* Snackbar/Alert  
* ConfirmDialog  
* FilterToolbar  
* RowActionMenu  
* BaseDialog  
* WizardModal base

### **Entregable**

Catálogo UI base listo para pantallas reales.

---

## **Sprint 2.4 — DataTable base**

### **Implementar**

Tabla reutilizable con:

* sort  
* paginación  
* estados vacíos  
* loading  
* badges  
* row actions  
* densidad consistente

### **Entregable**

Patrón común para todas las tablas del sistema.

---

# **Fase 3 — Pantallas core**

## **Objetivo**

Implementar primero las vistas con mayor impacto operativo.

---

## **Sprint 3.1 — Login \+ Dashboard**

### **Login**

* pantalla simple  
* branding sobrio  
* errores claros

### **Dashboard**

#### **Mostrar**

* Active inventories  
* Pending review  
* Processed aisles  
* Failed jobs  
* Manual corrections  
* Auto-acceptance rate

#### **Secciones**

* requires attention  
* recent activity  
* recent inventories

### **Dependencia**

Necesita contratos de summary ya resueltos.

---

## **Sprint 3.2 — Inventories**

### **Mostrar**

* summary cards  
* search  
* filters  
* table  
* pagination

### **Tabla**

* inventory name  
* status  
* created date  
* aisles count  
* pending review count  
* last activity  
* actions

### **Dependencia**

Necesita inventory list contract bien orientado.

---

## **Sprint 3.3 — Create Inventory**

### **Paso 1**

* inventory name  
* helper text  
* validación

### **Paso 2**

* visual references optional  
* drag and drop  
* preview  
* remove  
* contador

### **Dependencia**

Validar si DB/API soporta correctamente visual references.

---

## **Sprint 3.4 — Inventory Detail**

### **Mostrar**

#### **Header**

* inventory name  
* status  
* created date  
* acciones contextuales

#### **KPIs**

* total aisles  
* processed aisles  
* pending aisles  
* aisles with errors  
* pending review results  
* manual corrections  
* review completion rate

#### **Tabla de pasillos**

* aisle code  
* aisle status  
* uploaded assets  
* processing status  
* results found  
* pending review  
* last updated  
* actions

#### **Secundario**

* recent activity  
* logs resumidos

### **Dependencia**

Necesita contrato de inventory detail \+ aisle summary.

---

## **Sprint 3.5 — Create Aisle**

### **Mostrar**

* aisle code  
* helper text  
* validación  
* CTA clara

### **Dependencia**

Validar reglas de unicidad y naming.

---

# **Fase 4 — Flujo de revisión**

## **Objetivo**

Construir el núcleo de valor operativo del sistema: revisión humana eficiente.

---

## **Sprint 4.1 — Aisle Results**

### **Mostrar**

#### **Header**

* breadcrumb  
* aisle identification  
* inventory context

#### **KPIs**

* total results  
* needs review  
* low confidence  
* invalid traceability  
* qty zero  
* with evidence

#### **Filter bar**

* search by SKU  
* quick filters  
* filtros complementarios

#### **Tabla**

* priority  
* SKU  
* quantity  
* review status  
* traceability  
* confidence  
* evidence  
* updated  
* action

### **Dependencia**

Necesita result summary contract bien diseñado.

---

## **Sprint 4.2 — Review Queue**

### **Mostrar**

#### **KPIs**

* pending review  
* low confidence  
* invalid traceability  
* qty zero  
* missing evidence

#### **Filtros**

* inventory  
* aisle  
* status  
* confidence range  
* traceability  
* evidence  
* qty zero  
* search SKU

#### **Tabla**

* priority  
* SKU  
* quantity  
* confidence  
* traceability  
* review status  
* inventory  
* aisle  
* updated  
* actions

### **Dependencia**

Necesita endpoint específico o summary potente transversal.

---

## **Sprint 4.3 — Result Review Detail**

### **Layout**

Dos columnas obligatorias.

### **Columna izquierda**

* evidence viewer  
* zoom  
* fullscreen  
* thumbnails  
* filename discreto

### **Columna derecha**

#### **Result Summary**

* detected SKU  
* current quantity  
* count source  
* confidence  
* traceability status  
* review status  
* updated timestamp

#### **Review Actions**

* confirm result  
* correct quantity  
* correct SKU  
* mark invalid

#### **Navigation**

* previous / next

### **Secundario**

* review history  
* technical metadata collapsible

### **Dependencia**

Necesita contrato de detalle orientado a revisión, no a debug.

---

## **Sprint 4.4 — Quick Review Drawer**

### **Mostrar**

* evidencia compacta  
* sku  
* quantity  
* confidence  
* traceability  
* review status  
* quick actions  
* open full detail

### **Dependencia**

Necesita summary suficiente por fila.

---

# **Fase 5 — Analytics y robustez**

## **Objetivo**

Separar la capa analítica y cerrar calidad transversal.

---

## **Sprint 5.1 — Metrics / Analytics**

### **Mostrar**

* auto-acceptance rate  
* manual correction rate  
* invalid traceability rate  
* processing success rate  
* average review time  
* reviewed results per day

### **Secciones**

* trends over time  
* inventories with highest correction rate  
* aisles with frequent issues  
* low-confidence patterns  
* performance table

### **Dependencia**

Necesita agregados y métricas ya modelados.

---

## **Sprint 5.2 — Estados transversales y feedback**

### **Implementar**

* loading states  
* empty states  
* success feedback  
* error states  
* confirm dialogs  
* inline validations

### **Aplicar a**

* inventarios  
* pasillos  
* resultados  
* revisión  
* uploads  
* procesamiento

---

## **Sprint 5.3 — Pulido y consistencia final**

### **Revisar**

* copy  
* semántica de estados  
* badges  
* spacing  
* iconografía  
* jerarquía de botones  
* tablas  
* drawers  
* dialogs  
* metadata secundaria  
* breadcrumbs

---

# **Resumen de dependencias clave**

## **Antes de UI fuerte, hay que resolver:**

* taxonomía de estados  
* naming consistente  
* summaries para listas  
* details para pantallas de revisión  
* filtros/sort/paginación  
* métricas agregadas  
* visual references  
* evidencia principal y múltiple  
* historial de revisión usable

---

# **Orden real recomendado**

## **Etapa 1 — Diagnóstico y definición**

1. pantallas objetivo  
2. auditoría DB  
3. auditoría contratos  
4. matriz pantalla-datos-contratos  
5. contratos target

## **Etapa 2 — Backend alignment**

6. normalización de estados  
7. summaries/listados  
8. details  
9. filtros/paginación  
10. métricas

## **Etapa 3 — Base UI**

11. theme  
12. AppShell  
13. componentes reutilizables  
14. DataTable

## **Etapa 4 — Pantallas core**

15. Dashboard  
16. Inventories  
17. Create Inventory  
18. Inventory Detail  
19. Create Aisle

## **Etapa 5 — Review workflow**

20. Aisle Results  
21. Review Queue  
22. Result Review Detail  
23. Quick Review Drawer

## **Etapa 6 — Cierre**

24. Metrics  
25. estados y feedback  
26. pulido final

---

# **Qué cambia respecto del plan anterior**

Antes el plan asumía:

* “ya sabemos la UI, ahora implementemos”

Ahora el plan correcto asume:

* “ya sabemos la UI objetivo, pero primero tenemos que asegurar que DB y contratos soporten bien esa UI”

Ese cambio es muy importante, porque evita:

* rehacer endpoints a mitad de implementación  
* meter lógica de negocio en frontend  
* construir componentes sobre datos inestables  
* diseñar vistas que después no puedan alimentarse bien

---

# **Recomendación práctica final**

Yo arrancaría con esta secuencia inmediata:

## **Próximos 5 pasos concretos**

1. cerrar lista de pantallas objetivo  
2. auditar DB actual por entidad  
3. auditar endpoints actuales por pantalla  
4. construir matriz pantalla → datos → contrato  
5. definir contratos target antes de entrar a Material UI

Recién después pasaría a:

* theme  
* layout  
* tablas  
* pantallas

Porque ahí sí vas a implementar una UI nueva con base firme.l.