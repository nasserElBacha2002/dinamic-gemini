# **Plan de implementación — Rediseño del módulo de estadísticas**

## **1\. Objetivo general**

Rediseñar el panel de estadísticas para que deje de mostrar visualizaciones genéricas o poco confiables y pase a funcionar como un tablero operativo de calidad y eficiencia del conteo.

El nuevo módulo debe priorizar:

* performance por inventario;  
* carga de revisión manual;  
* distribución de tipos de corrección;  
* porcentaje de resultados `unknown`;  
* patrones de calidad relevantes;  
* capacidad real de filtrar por inventario y aisle.

## **2\. Problemas detectados en la versión actual**

### **Problemas de jerarquía**

* `Inventory performance` queda demasiado abajo.  
* `Aisles with review pressure` ocupa demasiado espacio vertical.  
* Los gráficos actuales empujan contenido importante hacia abajo.

### **Problemas de utilidad**

* `Review activity` no aporta valor real.  
* `Processing outcomes` no aporta valor y además no refleja una lectura confiable.  
* `Settling actions / day` no es una métrica prioritaria para este flujo.

### **Problemas de modelo de negocio**

* No existe una métrica visible y prioritaria para `unknown`.  
* No hay una lectura suficientemente clara de qué tipo de intervención manual está ocurriendo.  
* El filtro por inventario no está resolviendo el análisis como debería.

### **Problemas de UX**

* Hay demasiada altura ocupada por tablas secundarias.  
* La tabla de pasillos parece una tabla “de detalle”, no de resumen.  
* Falta una narrativa visual que permita entender rápidamente eficiencia, calidad y puntos de falla.

---

# **3\. Resultado esperado**

El panel debe responder rápidamente estas preguntas:

* ¿Qué tan eficiente está siendo el sistema?  
* ¿Cuánto trabajo manual requiere?  
* ¿Qué porcentaje termina en `unknown`?  
* ¿Qué tipo de corrección manual ocurre más?  
* ¿Qué inventarios rinden mejor o peor?  
* ¿Qué patrones de calidad dominan?  
* ¿Qué pasillos requieren atención?

---

# **4\. Nuevo diseño funcional del dashboard**

## **4.1. Estructura objetivo**

### **Bloque 1 — filtros**

Mantener:

* fecha desde  
* fecha hasta  
* inventario  
* aisle  
* refresh  
* reset filters

### **Bloque 2 — KPIs principales**

Seis cards prioritarias:

* Auto-acceptance rate  
* Manual correction rate  
* Unknown rate  
* Processing success rate  
* Average review time  
* Invalid traceability rate

### **Bloque 3 — visuales operativos**

Reemplazar los gráficos actuales por:

* `Manual intervention breakdown`  
* `Resolution flow` o `Review resolution funnel`

### **Bloque 4 — tabla principal**

* `Inventory performance`

### **Bloque 5 — bloque secundario en dos columnas**

* `Quality patterns`  
* `Aisles requiring attention` o `Aisles with review pressure`

---

# **5\. Alcance funcional detallado**

## **5.1. Remover bloques actuales sin valor**

Eliminar del dashboard:

* `Review activity`  
* `Processing outcomes`  
* `Settling actions / day`

Estos componentes deben salir tanto del layout como del modelo mental principal del módulo.

## **5.2. Agregar nueva métrica central: unknown**

Incorporar una métrica principal para `unknown`:

### **KPI**

* `% unknown rate`

### **Tooltip / descripción**

* porcentaje de posiciones procesadas o revisadas que terminan con estado `unknown`

### **Complemento recomendado**

mostrar también:

* count absoluto  
* denominador del cálculo

Ejemplo:

* `12.4%`  
* `38 of 307 positions`

## **5.3. Reforzar la lectura de revisión manual**

Agregar un bloque visual que muestre distribución de acciones manuales.

### **Categorías mínimas**

* confirmed  
* quantity corrected  
* sku corrected  
* invalid  
* unknown  
* deleted

### **Objetivo**

Entender en qué se va el esfuerzo humano y qué tipo de error domina.

## **5.4. Dar más prioridad a inventory performance**

Mover `Inventory performance` por encima de la tabla de aisles.

## **5.5. Reducir protagonismo de aisles with review pressure**

Mantenerla, pero como bloque secundario:

* paginada;  
* más compacta;  
* con menos altura;  
* sin dominar el layout.

---

# **6\. Fases de implementación**

## **Fase 1 — Definición de métricas y contrato**

Objetivo: alinear exactamente qué mide cada bloque y evitar inconsistencias.

### **Tareas**

* Revisar el contrato actual de analytics.  
* Definir cálculo exacto de `unknown_rate`.  
* Definir cálculo exacto de distribución de acciones manuales.  
* Definir si el denominador de cada rate usa:  
  * posiciones procesadas,  
  * posiciones revisadas,  
  * acciones de review,  
  * o posiciones no eliminadas.

### **Entregables**

* documento corto de definiciones métricas;  
* lista de campos requeridos por frontend;  
* decisión de naming final.

### **Definition of Done**

* cada KPI tiene fórmula explícita;  
* cada tabla tiene columnas definidas;  
* cada visual tiene fuente de datos clara;  
* no queda ninguna métrica ambigua.

---

## **Fase 2 — Refactor de backend analytics**

Objetivo: ajustar endpoints y payloads para el nuevo panel.

### **Cambios backend**

#### **A. Summary**

El summary principal debe incluir:

* auto\_acceptance\_rate  
* manual\_correction\_rate  
* unknown\_rate  
* processing\_success\_rate  
* average\_review\_time\_minutes  
* invalid\_traceability\_rate

Y además counts asociados si aplica:

* unknown\_count  
* processed\_positions\_count  
* reviewed\_positions\_count  
* total\_positions\_in\_scope

#### **B. Manual intervention breakdown**

Agregar un endpoint o ampliar uno existente para devolver:

* confirmed\_count  
* qty\_corrected\_count  
* sku\_corrected\_count  
* invalid\_count  
* unknown\_count  
* deleted\_count

Idealmente también:

* percentage per category

#### **C. Inventory performance**

Asegurar que la tabla por inventario incluya:

* inventory\_id  
* inventory\_name  
* created\_at  
* aisles\_count  
* positions\_count  
* processed\_count  
* auto\_acceptance\_rate  
* manual\_correction\_rate  
* unknown\_rate  
* invalid\_traceability\_rate  
* avg\_confidence  
* processing\_success\_rate  
* average\_review\_time\_minutes

#### **D. Aisles requiring attention**

Reducir a un payload compacto:

* aisle\_id / aisle\_name  
* inventory\_name  
* positions\_count  
* pending\_review\_count  
* unknown\_count  
* invalid\_traceability\_count  
* manual\_corrections\_count

#### **E. Quality patterns**

Agregar bucket explícito para `unknown` si hoy no existe.

### **Definition of Done**

* endpoints responden con los nuevos campos;  
* filtros por fecha / inventory / aisle aplican consistentemente;  
* no se usan series temporales falsas o poco confiables;  
* contratos tipados y documentados.

---

## **Fase 3 — Corrección del filtro por inventario y alcance**

Objetivo: que el dashboard realmente se comporte por scope.

### **Tareas**

* hacer que `inventory` sea filtro real de todos los bloques;  
* hacer que `aisle` dependa del inventario seleccionado;  
* al cambiar inventario, resetear aisle inválido;  
* reflejar claramente el scope actual.

### **Mejora recomendada**

Agregar una línea de contexto debajo de filtros:

* Inventories in scope  
* Aisles in scope  
* Positions in scope

### **Definition of Done**

* todos los widgets responden al filtro;  
* no hay inconsistencias entre cards, tablas y visuales;  
* aisle no muestra opciones fuera del inventory seleccionado.

---

## **Fase 4 — Rediseño del layout frontend**

Objetivo: reordenar jerarquía y limpiar la experiencia.

### **Nuevo orden**

1. Filters bar  
2. KPI grid  
3. Manual intervention breakdown \+ Resolution flow  
4. Inventory performance  
5. Quality patterns \+ Aisles requiring attention

### **Tareas**

* eliminar secciones viejas;  
* reordenar grid;  
* bajar altura de tabla secundaria;  
* priorizar tabla de inventarios;  
* asegurar responsive correcto.

### **Recomendaciones UI**

* cards compactas y homogéneas;  
* tablas con altura controlada;  
* menos scroll vertical innecesario;  
* títulos más operativos;  
* subtítulos claros.

### **Definition of Done**

* inventory performance aparece above the fold o cerca de eso;  
* no hay bloques muertos;  
* el dashboard comunica prioridades reales;  
* la pantalla se siente más corta y más útil.

---

## **Fase 5 — Construcción de visuales operativos**

Objetivo: reemplazar gráficos sin valor por visualizaciones útiles.

### **5.1. Manual intervention breakdown**

#### **Propuesta**

* horizontal bar chart o stacked bar;  
* distribución porcentual \+ count;  
* tooltip con definición.

#### **Datos**

* confirmed  
* qty corrected  
* sku corrected  
* invalid  
* unknown  
* deleted

#### **Lectura esperada**

Permitir detectar rápidamente:

* si predominan correcciones de cantidad;  
* si el problema principal es unknown;  
* si hay demasiadas invalidaciones.

### **5.2. Resolution flow**

#### **Propuesta**

Un bloque tipo funnel simple o step flow:

* total processed  
* needs review  
* manually touched  
* settled  
* unknown

No hace falta complejidad visual excesiva; tiene que ser legible y confiable.

### **Definition of Done**

* ambos visuales usan datos reales;  
* son legibles;  
* no consumen demasiado alto;  
* agregan valor operativo.

---

## **Fase 6 — Rediseño de Inventory performance**

Objetivo: convertirlo en la tabla central del módulo.

### **Cambios**

* moverla arriba;  
* agregar paginación;  
* usar page size chico por default, por ejemplo 5 o 10;  
* sticky header;  
* altura contenida;  
* sorting útil;  
* filas compactas.

### **Columnas recomendadas**

* Inventory  
* Created  
* Aisles  
* Positions  
* Processed  
* Auto-accept rate  
* Manual correction rate  
* Unknown rate  
* Invalid traceability  
* Avg confidence  
* Avg review time  
* Job success rate

### **Posibles acciones**

* click row para ir al inventory detail  
* tooltip de fórmulas

### **Definition of Done**

* la tabla ya no queda enterrada;  
* no rompe el layout;  
* permite comparar performance rápidamente.

---

## **Fase 7 — Rediseño de Aisles with review pressure**

Objetivo: mantener utilidad operativa sin romper el panel.

### **Cambios**

* renombrar opcionalmente a `Aisles requiring attention`;  
* paginación obligatoria;  
* altura fija;  
* menos filas por página;  
* columnas enfocadas.

### **Columnas sugeridas**

* Aisle  
* Inventory  
* Positions  
* Pending review  
* Unknown  
* Invalid traceability  
* Manual corrections

### **Definition of Done**

* la tabla no empuja el resto hacia abajo;  
* sigue siendo accionable;  
* permite detectar quickly qué aisle requiere atención.

---

## **Fase 8 — Quality patterns mejorado**

Objetivo: mantener el bloque, pero alineado a prioridades reales.

### **Ajustes**

* incluir `unknown` como patrón explícito;  
* revisar prioridad de buckets;  
* mejorar labels y descripciones;  
* asegurar consistencia con métricas summary.

### **Orden sugerido**

1. Unknown  
2. Pending review  
3. Invalid traceability  
4. Missing evidence  
5. Zero quantity  
6. Low confidence  
7. OK / no primary issue

### **Definition of Done**

* unknown aparece como patrón visible;  
* las categorías tienen prioridad coherente;  
* el componente aporta lectura de calidad real.

---

# **7\. Cambios de naming recomendados**

## **Reemplazos**

* `Aisles with review pressure` → `Aisles requiring attention`  
* `Review activity` → eliminar  
* `Processing outcomes` → eliminar  
* `Settling actions / day` → eliminar  
* `Review rate` → evaluar reemplazo por `Needs review rate` o `Manual touch rate`

## **Motivo**

Usar nombres más operativos y menos ambiguos.

---

# **8\. Consideraciones de modelo y métricas**

## **8.1. Unknown**

Hay que decidir exactamente qué significa:

* posición sin resolución final;  
* posición marcada manualmente como unknown;  
* posición cuyo estado final es unknown;  
* posición sin SKU / quantity determinable.

La recomendación es usar **estado final unknown** como criterio principal para el KPI y para la tabla por inventario.

## **8.2. Manual correction rate**

Definir si incluye:

* solo qty \+ sku correction;  
* también invalid;  
* también unknown;  
* también delete.

Mi recomendación:

* `manual_correction_rate`: solo qty \+ sku corrections  
* `manual_intervention_breakdown`: incluir confirm / invalid / unknown / delete además de corrections

Así no mezclás “corrección” con “intervención”.

## **8.3. Auto-acceptance**

Mantenerla como proporción de resultados confirmados sin corrección manual, pero revisar denominador para asegurar consistencia con manual correction rate.

## **8.4. Average review time**

Confirmar si mide:

* resultado creado → primera acción de settling  
* o  
* pendiente → resolución final

Si ya existe bien definido, mantenerlo.

---

# **9\. Riesgos**

## **Riesgo 1**

Que `unknown` no esté bien persistido o no tenga trazabilidad consistente.

### **Mitigación**

* auditar el estado final de review actions;  
* revisar cómo queda guardado en posición final / canonical view.

## **Riesgo 2**

Que distintas tablas usen diferentes denominadores para las rates.

### **Mitigación**

* centralizar fórmulas en backend analytics service;  
* evitar cálculos duplicados en frontend.

## **Riesgo 3**

Que el filtro por inventario no se propague correctamente a todos los endpoints.

### **Mitigación**

* estandarizar query params en toda la familia `/analytics`;  
* validar con tests de integración.

## **Riesgo 4**

Que el nuevo dashboard siga siendo demasiado alto.

### **Mitigación**

* controlar altura de tablas;  
* paginación por defecto baja;  
* evitar gráficos grandes.

---

# **10\. Plan técnico sugerido por sprint**

## **Sprint 1 — Métricas y contratos**

* definir fórmulas;  
* agregar unknown rate;  
* ajustar summary;  
* definir payload de manual intervention breakdown.

## **Sprint 2 — Backend analytics**

* implementar endpoints / payloads;  
* corregir filtros inventory/aisle;  
* agregar counts y breakdowns.

## **Sprint 3 — Rediseño base frontend**

* eliminar gráficos viejos;  
* reordenar layout;  
* subir inventory performance;  
* paginar aisles table.

## **Sprint 4 — Nuevos componentes visuales**

* manual intervention breakdown;  
* resolution flow;  
* quality patterns con unknown.

## **Sprint 5 — Pulido y validación**

* copy final;  
* tooltips;  
* empty states;  
* responsive;  
* tests funcionales.

---

# **11\. Criterios de aceptación funcionales**

## **Dashboard**

* no muestra `Review activity`  
* no muestra `Processing outcomes`  
* no muestra `Settling actions / day`

## **KPIs**

* muestra `Unknown rate` como card principal  
* los seis KPIs responden al filtro por fecha / inventory / aisle

## **Inventory performance**

* aparece antes que la tabla de aisles  
* tiene paginación  
* incluye `unknown rate`

## **Aisles requiring attention**

* está paginada  
* tiene altura contenida  
* no domina la pantalla

## **Visuales operativos**

* existe `Manual intervention breakdown`  
* existe `Resolution flow`  
* usan datos reales y consistentes

## **Quality patterns**

* incluye unknown  
* mantiene prioridad útil de issues

---

# **12\. Criterios de aceptación técnicos**

## **Backend**

* contratos tipados  
* fórmulas centralizadas  
* filtros homogéneos  
* tests de integración de analytics actualizados

## **Frontend**

* layout consistente con MUI  
* tabla principal con paginación y altura controlada  
* componentes reutilizables para KPI y visuales  
* loading / empty / error states correctos

---

# **13\. Recomendación de implementación**

Yo lo haría en este orden:

1. definir fórmulas exactas;  
2. resolver `unknown` y manual interventions en backend;  
3. corregir filtros inventory/aisle;  
4. reordenar layout;  
5. agregar nuevos visuales;  
6. compactar tablas;  
7. pulir copy y jerarquía.

Porque si primero hacés solo frontend, corrés riesgo de rearmar la UI sobre contratos que todavía no expresan bien el negocio.

---

# **14\. Resultado final esperado**

Al terminar, el módulo debería sentirse como un panel de control operativo, no como una página genérica de analytics.

La lectura ideal debería ser:

* arriba veo eficiencia general;  
* después entiendo el costo manual;  
* después comparo inventarios;  
* después veo patrones de calidad;  
* por último identifico pasillos problemáticos.

Ese orden responde mucho mejor a tu uso real.

Si querés, en el próximo mensaje te lo convierto directamente en un **prompt para Cursor**, dividido en:

* backend,  
* frontend,  
* contrato de métricas,  
* y definition of done.

