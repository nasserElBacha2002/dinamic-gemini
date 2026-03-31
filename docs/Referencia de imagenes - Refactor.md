# **Documento técnico**

## **Redefinición del detalle de inventario y normalización del flujo de imágenes de referencia**

## **1\. Contexto**

La vista actual de **Inventory Detail** está mezclando tres tipos de información:

1. **Operación del inventario**  
   * tabla de pasillos  
   * acciones de procesamiento  
   * navegación al detalle operativo  
2. **Métricas resumidas**  
   * total aisles  
   * processed aisles  
   * pending aisles  
   * review completion rate  
   * etc.  
3. **Activity / Logs summary**  
   * panel lateral con placeholders de actividad y logs

En la práctica, esta combinación no responde bien al objetivo real de la pantalla.  
El inventario detail debería ser una vista de **gestión operativa del inventario**, no una pantalla híbrida de operación \+ observabilidad \+ analytics.

Además, existe una necesidad funcional prioritaria no bien resuelta en la UI actual: la visualización y actualización de las **reference images** asociadas al inventario, las cuales son clave para el procesamiento.

---

## **2\. Problema**

## **2.1 Problemas de producto / UX**

### **a. Las métricas generan ruido**

Las métricas del inventario ya tienen una sección específica donde se pueden consultar mejor, con más contexto y posibilidades de análisis. En el detalle del inventario:

* ocupan demasiado espacio;  
* desplazan elementos más importantes;  
* duplican información;  
* no ayudan a ejecutar una acción inmediata.

### **b. Activity y logs están mal ubicados**

La actividad mostrada en esta vista no tiene suficiente valor real y conceptualmente no está alineada:

* los logs relevantes son por job o por pasillo;  
* la actividad no está consolidada de manera útil;  
* hoy funciona más como placeholder que como herramienta.

### **c. Falta una pieza clave: reference images**

Las imágenes de referencia son importantes porque:

* forman parte del contexto del inventario;  
* afectan el procesamiento futuro;  
* deberían poder verse y gestionarse desde el detalle del inventario.

Hoy la pantalla no les da un lugar central ni permite verificar con claridad:

* si existen;  
* cuáles son;  
* si están siendo usadas realmente;  
* cómo se actualizan.

---

## **2.2 Problemas técnicos potenciales**

A nivel de backend y flujo de negocio, hay dudas que deben resolverse:

* si las reference images están bien modeladas a nivel inventario;  
* si el inventory detail las devuelve en su contrato;  
* si el procesamiento de un aisle realmente las toma siempre;  
* si el job deja metadata verificable sobre su uso;  
* si actualizar referencias afecta jobs pasados o solo futuros;  
* si la UI actual representa fielmente el comportamiento real del sistema.

---

## **3\. Objetivo del rediseño**

Redefinir la vista de detalle de inventario para que cumpla una función clara:

### **Nuevo objetivo de Inventory Detail**

Ser el lugar donde el operador pueda:

* entender rápidamente el estado del inventario;  
* administrar sus pasillos;  
* visualizar y gestionar reference images;  
* disparar las acciones operativas correctas.

### **Lo que esta vista no debe hacer**

* no debe ser una pantalla de analytics;  
* no debe ser una pantalla de observabilidad/logging;  
* no debe competir con la sección de métricas;  
* no debe mostrar bloques decorativos sin impacto operativo real.

---

## **4\. Propuesta funcional**

## **4.1 Contenido final esperado de la vista**

La vista de detalle de inventario debería quedar compuesta por tres bloques principales:

### **A. Header del inventario**

Debe contener:

* nombre del inventario;  
* estado;  
* fecha de creación;  
* acciones principales.

### **B. Superficie de gestión de Reference Images**

Debe permitir:

* ver las imágenes cargadas;  
* previsualizarlas;  
* conocer metadata básica;  
* subir nuevas imágenes;  
* reemplazar o eliminar existentes;  
* entender si se usarán en futuros procesamientos.

**Decisión final de producto implementada:** la gestión de `Reference images` queda accesible desde el **header** mediante un botón que abre un **right-side drawer**.  
Esta decisión reemplaza la hipótesis inicial de un bloque inline arriba de la tabla y mantiene la pantalla enfocada en operación (`header + aisles`) sin perder acceso directo a referencias.

### **C. Tabla de Aisles**

Debe seguir siendo el bloque operativo principal:

* listado de pasillos;  
* estado;  
* assets;  
* resultados;  
* acciones.

---

## **4.2 Elementos a remover**

### **A remover del inventory detail**

1. **Summary metrics cards**  
2. **Activity panel**  
3. **Logs summary panel**

Estas piezas deben salir completamente de esta pantalla.

---

## **5\. Propuesta de layout**

## **5.1 Estructura recomendada**

### **Header**

* Breadcrumb / ubicación  
* Nombre del inventario  
* Badge de estado  
* Metadata mínima  
* Botones:  
  * Export CSV  
  * Create aisle  
  * Manage reference images o Upload references

### **Bloque 1: Access to Reference Images**

**Decisión final:** el acceso principal a `Reference images` vive en el **header** (`Manage reference images`) y abre un **right-side drawer** de gestión.

Contenido esperado del drawer:

* título;  
* subtítulo explicativo corto;  
* listado administrable con metadata básica;  
* empty state;  
* acciones de gestión.

### **Bloque 2: Aisles**

Tabla con foco operativo.

---

## **5.2 Contenido final de la superficie de Reference Images**

Cada item del drawer debe incluir:

* acceso a preview;  
* nombre o label interno;  
* fecha de carga;  
* tamaño o tipo;  
* acciones:  
  * view  
  * replace  
  * delete

La superficie debe incluir:

* botón de upload;  
* mensaje explicando impacto funcional;  
* estado vacío claro.

### **Empty state sugerido**

**No reference images uploaded yet**  
Upload 1–3 images to help the analysis use expected pallet, label, or packaging references for this inventory.

### **Mensaje funcional sugerido**

**Reference images are used for future processing runs only.**  
Updating them does not modify existing results automatically.

---

## **6\. Reglas de negocio propuestas**

## **6.1 Alcance de reference images**

Las reference images pertenecen al **inventario**, no al aisle ni al job.

## **6.2 Momento de uso**

Las reference images se usan al momento de procesar un aisle dentro de ese inventario.

## **6.3 Impacto de una actualización**

Actualizar reference images:

* **no** debe modificar resultados existentes;  
* **sí** debe impactar en procesamientos futuros.

## **6.4 Trazabilidad**

Cada job debería registrar:

* si usó referencias o no;  
* cuántas usó;  
* cuáles usó, idealmente por asset id;  
* si hubo errores al resolverlas.

## **6.5 Comportamiento ante ausencia de referencias**

Si un inventario no tiene reference images:

* el procesamiento debe seguir funcionando;  
* el sistema debe marcar que corrió sin referencias;  
* la UI no debe inducir a error.

---

## **7\. Estado técnico esperado del sistema**

## **7.1 Backend**

Debe existir un flujo claro para:

* listar reference images por inventario;  
* subir reference images;  
* eliminar reference images;  
* reemplazar reference images;  
* resolver sus URLs de preview/file;  
* inyectarlas en el contexto de análisis del procesamiento.

## **7.2 Frontend**

La pantalla de inventory detail debe:

* obtener las references del inventario;  
* renderizarlas;  
* refrescar el estado tras cambios;  
* mostrar loading, empty y error states;  
* dejar claro su impacto operacional.

## **7.3 Pipeline / procesamiento**

Al ejecutar `process aisle`, el sistema debe:

* resolver las reference images activas del inventario;  
* pasarlas al `AnalysisContext` o equivalente;  
* registrarlas en job metadata;  
* permitir trazabilidad posterior.

---

## **8\. Riesgos identificados**

## **8.1 Riesgos de producto**

* que la UI muestre referencias pero el pipeline no las use realmente;  
* que el usuario piense que actualizar referencias re-procesa resultados viejos;  
* que la falta de visibilidad genere desconfianza operativa.

## **8.2 Riesgos técnicos**

* referencias en storage pero no bien asociadas en DB;  
* contratos API incompletos;  
* metadata insuficiente en jobs;  
* inconsistencias entre proveedores o estrategias de análisis;  
* refresh incompleto en frontend luego de cambios.

---

## **9\. Criterios de aceptación**

## **9.1 Inventory detail**

* no muestra métricas resumen;  
* no muestra activity ni logs summary;  
* muestra reference images;  
* mantiene la tabla de aisles como foco principal.

## **9.2 Reference images**

* se pueden listar;  
* se pueden subir;  
* se pueden eliminar;  
* se pueden reemplazar;  
* muestran preview y metadata básica;  
* la UI comunica correctamente su función.

## **9.3 Procesamiento**

* nuevos jobs usan las referencias activas del inventario;  
* jobs viejos no cambian por actualizar referencias;  
* job metadata registra el uso de referencias;  
* la trazabilidad es visible o al menos auditable.

---

# **Plan de implementación real**

Te propongo hacerlo en **4 fases**, con entregables reales, bajo riesgo y validación progresiva.

---

## **Fase 0 — Discovery técnico y alineación funcional**

### **Objetivo**

Entender exactamente cómo está funcionando hoy el flujo real antes de cambiar UI y contratos.

### **Tareas**

1. Auditar el contrato actual de inventory detail.  
2. Auditar endpoints relacionados con reference images.  
3. Auditar modelo de datos:  
   * dónde se guardan;  
   * cómo se asocian;  
   * qué metadata tienen.  
4. Auditar el flujo de `process aisle`:  
   * cómo resuelve referencias;  
   * si las inyecta o no al análisis.  
5. Auditar job metadata:  
   * si guarda referencias usadas;  
   * cómo se podría exponer.  
6. Verificar comportamiento real desde UI actual y backend.

### **Entregable**

Documento corto de auditoría con:

* flujo actual real;  
* gaps;  
* riesgos;  
* decisiones recomendadas.

### **Duración estimada**

1 a 2 días.

---

## **Fase 1 — Simplificación del Inventory Detail**

### **Objetivo**

Dejar la pantalla enfocada en operación.

### **Cambios**

1. remover summary metrics cards;  
2. remover activity/logs panel;  
3. rebalancear layout;  
4. dejar header \+ tabla de aisles como estructura base.

### **Frontend**

* actualizar layout MUI;  
* remover fetches o componentes que ya no se usen;  
* limpiar estados derivados.

### **Backend**

Sin cambios obligatorios, salvo que algún endpoint esté trayendo data innecesaria que se quiera dejar de consumir.

### **Definition of Done**

* el detalle del inventario queda visualmente limpio;  
* no hay bloques de métricas ni activity;  
* la tabla de aisles sigue funcionando;  
* no se rompe navegación ni acciones.

### **Duración estimada**

1 a 2 días.

---

## **Fase 2 — Incorporación de Reference Images al detalle**

### **Objetivo**

Hacer del inventory detail el punto principal de visualización y gestión de referencias.

### **Cambios funcionales**

1. crear bloque `ReferenceImagesSection`;  
2. listar imágenes actuales;  
3. empty state;  
4. upload flow;  
5. delete flow;  
6. replace flow;  
7. refresh automático tras mutaciones.

### **Frontend**

#### **Componentes sugeridos**

* `ReferenceImagesSection`  
* `ReferenceImageCard`  
* `ReferenceImagesEmptyState`  
* `ReferenceImagesUploadDialog` o uploader inline  
* `ReferenceImagePreviewDialog`

#### **Estados**

* loading  
* empty  
* populated  
* upload in progress  
* mutation error

### **Backend**

Si ya existen endpoints correctos:

* reutilizarlos.

Si no existen o son incompletos:

* definir endpoints mínimos:  
  * `GET /inventories/{inventory_id}/reference-images`  
  * `POST /inventories/{inventory_id}/reference-images`  
  * `DELETE /inventories/{inventory_id}/reference-images/{asset_id}`  
  * opcional: replace vía delete \+ upload o endpoint dedicado

### **Definition of Done**

* desde inventory detail se accede claramente a las reference images;  
* se pueden subir, borrar y actualizar;  
* la UI se refresca correctamente;  
* el usuario entiende que son referencias del inventario.

### **Duración estimada**

2 a 4 días.

---

## **Fase 3 — Corrección y normalización del flujo real de referencias**

### **Objetivo**

Asegurar que lo que se muestra en UI corresponde con el comportamiento real del pipeline.

### **Tareas backend**

1. Confirmar asociación fuerte `inventory -> reference images`.  
2. Normalizar modelo de dominio si hace falta.  
3. Asegurar que `process aisle` resuelva las referencias activas del inventario.  
4. Inyectarlas en `AnalysisContext`.  
5. Registrar en `job.metadata`:  
   * `reference_images_used: true/false`  
   * `reference_image_ids: []`  
   * `reference_images_count`  
   * errores si aplica  
6. Exponer esa metadata si es necesario en endpoints de job o aisle status.

### **Tareas de validación**

* procesar un aisle con referencias;  
* procesar un aisle sin referencias;  
* actualizar referencias y correr un nuevo job;  
* verificar que el job nuevo usa las nuevas y el viejo no cambia.

### **Definition of Done**

* el pipeline usa referencias de forma consistente;  
* existe trazabilidad real;  
* la UI no promete algo que el backend no hace.

### **Duración estimada**

3 a 5 días.

---

## **Fase 4 — Cierre de flujo operativo y UX final**

### **Objetivo**

Terminar de definir el comportamiento de negocio y la experiencia del operador.

### **Tareas**

1. agregar mensajes explicativos en UI;  
2. definir si hay límite de imágenes;  
3. definir validaciones de formato y tamaño;  
4. definir comportamiento de reemplazo;  
5. definir si se muestra metadata de uso en jobs o aisle detail;  
6. revisar nomenclatura final y separación de contratos:  
  * término operatorio/UI: `reference images`  
  * término interno backend/storage: `visual references`  
  * metadata persistida de trazabilidad: `visual_reference_context`  
  * resumen compacto expuesto a frontend: `reference_usage`

### **Mejora opcional**

Mostrar en cada corrida o estado del aisle algo como:

* “Processed with 2 reference images”  
* “Processed without reference images”

### **Definition of Done**

* flujo claro para el operador;  
* reglas de negocio cerradas;  
* nomenclatura consistente;  
* sistema auditable.

### **Decisiones finales de cierre**

* **UI / producto:** el surface final de gestión es `header action + right-side drawer`; no queda un bloque inline obligatorio en `Inventory Detail`.  
* **Término operatorio:** en UI y documentación funcional se usa `Reference images`.  
* **Término técnico interno:** backend, storage y repositorios mantienen `visual references` para evitar churn innecesario en contratos internos y nombres de código.  
* **Metadata persistida canónica:** `visual_reference_context` en `job.result_json`.  
* **Resumen operador/frontend canónico:** `reference_usage` dentro de `latest_job` para aisle list/status.  
* **Modelo summary vs detail:** la tabla muestra resumen compacto; el log modal sigue siendo la capa de deep inspection.

### **Duración estimada**

2 a 3 días.

---

# **Plan de ejecución sugerido por sprint**

## **Sprint corto 1**

### **Alcance**

* Fase 0  
* Fase 1

### **Resultado**

Pantalla limpia y diagnóstico técnico completo.

---

## **Sprint corto 2**

### **Alcance**

* Fase 2

### **Resultado**

Reference images visibles y administrables desde inventory detail.

---

## **Sprint corto 3**

### **Alcance**

* Fase 3  
* parte de Fase 4

### **Resultado**

Flujo real corregido y trazabilidad del uso de referencias.

---

# **Backlog técnico detallado**

## **Epic 1 — Inventory Detail Simplification**

### **Tasks**

* remove summary metrics container  
* remove activity panel  
* remove logs summary panel  
* rebalance page grid/layout  
* validate responsive behavior  
* clean unused hooks/selectors/types

---

## **Epic 2 — Reference Images UI**

### **Tasks**

* define section placement in inventory detail  
* add data fetching hook  
* implement cards/grid rendering  
* implement empty state  
* implement upload action  
* implement delete action  
* implement replace action  
* implement preview dialog  
* add mutation feedback/snackbar  
* invalidate/refetch queries after mutations

---

## **Epic 3 — Reference Images API and Domain Audit**

### **Tasks**

* inspect current DB/storage model  
* inspect inventory detail response  
* inspect asset/reference endpoints  
* confirm storage URL/preview resolution  
* document missing contract pieces

---

## **Epic 4 — Processing Integration**

### **Tasks**

* trace reference resolution during aisle processing  
* pass references into analysis context  
* persist job metadata on references used  
* expose metadata where needed  
* validate with end-to-end tests

---

## **Epic 5 — UX Closure**

### **Tasks**

* define copy and messaging  
* add warnings about future-runs-only impact  
* confirm validation rules  
* decide visibility of reference usage in aisle/job status  
* final polish

---

# **Recomendaciones de implementación**

## **1\. No empezar por la UI sin auditar el flujo**

Porque corrés el riesgo de mostrar una sección linda pero desconectada del comportamiento real.

## **2\. Mantener el cambio del inventory detail pequeño al principio**

Primero:

* sacar ruido,  
* luego agregar referencias.

Eso reduce riesgo y facilita review.

## **3\. No mezclar logs con esta pantalla**

Si más adelante querés observabilidad:

* ubicarla a nivel job,  
* o dentro del detalle del aisle,  
* no a nivel inventory detail con placeholders.

## **4\. Hacer visible la trazabilidad del uso de referencias**

Aunque sea con una metadata mínima.  
Esto va a ser clave para confianza operativa.

---

# **Resultado esperado final**

Al terminar este trabajo, la vista de inventory detail debería convertirse en una pantalla mucho más clara:

* **Header del inventario**  
* **Reference images**  
* **Aisles table**

Y el flujo debería ser:

1. el operador entra al inventario;  
2. verifica o actualiza reference images;  
3. gestiona pasillos;  
4. corre procesamiento;  
5. el sistema usa esas referencias en nuevos jobs;  
6. queda trazabilidad de ese uso.

---

