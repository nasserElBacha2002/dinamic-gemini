# **Plan técnico-funcional de rediseño UI para Dinamic Inventory v3**

## **1\. Objetivo del rediseño**

El objetivo no es solamente “hacerla más linda”.  
El objetivo es transformar la interfaz actual en una plataforma que:

* guíe mejor al usuario  
* reduzca carga mental  
* permita operar inventarios con más velocidad  
* escale mejor cuando haya más pasillos, más resultados y más revisiones  
* haga más clara la lectura de estados  
* separe mejor operación, revisión y análisis  
* transmita un nivel mucho más profesional

La nueva UI tiene que sentirse como una **plataforma interna enterprise de operaciones**, no como una colección de pantallas sueltas.

---

# **2\. Principios de diseño que deben guiar la implementación**

## **2.1. Prioridad operativa**

Cada pantalla tiene que responder rápido:

* qué estoy viendo  
* qué es importante  
* qué tengo que hacer ahora

## **2.2. Jerarquía visual fuerte**

La pantalla debe organizarse siempre en este orden:

1. contexto  
2. métricas o resumen  
3. contenido principal  
4. acciones  
5. detalle secundario / técnico

## **2.3. Menos duplicación**

Cada vista debe tener un propósito claro.  
No repetir en cinco lugares la misma información con distinto formato.

## **2.4. Escalabilidad**

Todas las tablas deben pensarse desde ya para:

* búsqueda  
* filtros  
* sort  
* paginación  
* mayor volumen de datos

## **2.5. Consistencia**

Estados, botones, espaciados, badges, tablas y formularios deben comportarse igual en todo el sistema.

## **2.6. Separación entre operación y análisis**

No mezclar en la misma experiencia:

* acciones operativas  
* revisión humana  
* analytics gerencial

---

# **3\. Arquitectura de pantallas propuesta**

La estructura recomendada del producto debería quedar así:

1. **Login**  
2. **Dashboard**  
3. **Inventories**  
4. **Inventory Detail**  
5. **Aisle Results**  
6. **Review Queue**  
7. **Result Review Detail**  
8. **Metrics / Analytics**  
9. **Pantallas/modales auxiliares**  
   * Create Inventory  
   * Create Aisle  
   * Upload Assets  
   * Quick Review Drawer  
   * Logs / metadata secundarios

---

# **4\. Layout global del sistema**

## **4.1. Estructura general**

Todas las pantallas autenticadas deben compartir un layout común:

* **sidebar izquierda persistente**  
* **topbar superior**  
* **contenedor principal central**  
* **breadcrumbs en pantallas internas**  
* **acciones contextuales en header**

## **4.2. Sidebar**

Debe incluir:

* Dashboard  
* Inventories  
* Review Queue  
* Metrics  
* Settings

“Aisles” no necesariamente debe ser una sección independiente del menú principal al comienzo; puede seguir viviendo dentro de Inventory Detail. Solo tendría sentido separarla si más adelante hay operación transversal entre inventarios.

## **4.3. Topbar**

Debe incluir:

* título contextual de página  
* subtítulo o contexto si hace falta  
* acciones principales de esa pantalla  
* usuario / menú de sesión en esquina superior derecha

El logout no debe estar como botón suelto importante. Debe ir dentro del menú del usuario.

---

# **5\. Sistema visual general**

## **5.1. Qué tono visual debe tener**

La plataforma debe sentirse:

* profesional  
* sobria  
* confiable  
* moderna  
* operativa  
* clara  
* enterprise

No debe sentirse:

* juguetona  
* startup exagerada  
* demasiado colorida  
* demasiado “template genérico”  
* ni como herramienta de debugging

---

# **6\. Colores recomendados**

Todavía no estamos cerrando branding final, pero sí una semántica clara.

## **6.1. Base**

Conviene una base neutra:

* fondo general muy claro  
* superficies blancas o casi blancas  
* bordes suaves  
* texto principal oscuro  
* texto secundario gris medio

## **6.2. Color primario**

Mantener un **azul profesional** como color principal de acción está bien para este producto.  
El azul actual, mejor trabajado, funciona porque transmite:

* tecnología  
* control  
* sistema  
* claridad

Debe usarse para:

* botones primarios  
* links importantes  
* estados informativos  
* foco  
* elementos activos de navegación

## **6.3. Colores semánticos**

Hay que fijar una lógica rígida:

* **Azul**: acción / información / elemento activo  
* **Verde**: válido / confirmado / procesado con éxito  
* **Naranja**: requiere revisión / advertencia / necesita atención  
* **Rojo**: error / inválido / eliminado / acción destructiva  
* **Gris**: draft / neutral / sin dato / estado pasivo

Esta lógica debe repetirse en todo el sistema.

## **6.4. Qué evitar**

* demasiados tonos distintos para lo mismo  
* usar verde y azul indistintamente para “estado positivo”  
* usar colores fuertes en exceso  
* badges con semántica inconsistente

---

# **7\. Tipografía y densidad**

## **7.1. Tipografía**

Conviene usar una tipografía limpia y legible, estándar del ecosistema Material UI.

La jerarquía debería ser:

* título principal  
* subtítulo / contexto  
* labels de secciones  
* labels de campos  
* texto secundario  
* captions / metadata

## **7.2. Densidad**

La interfaz debe ser **desktop-first**, con una densidad media:

* no tan aireada como un producto marketing  
* no tan comprimida como un sistema legacy

Especialmente las tablas deben tener buena densidad para revisión operativa.

---

# **8\. Componentes genéricos que sí o sí hay que construir**

No hace falta ahora pensar en props ni en APIs internas, pero sí definir el set conceptual de componentes base.

## **8.1. AppShell**

Componente que resuelve:

* sidebar  
* topbar  
* content container  
* spacing general

Debe ser la base de toda la app autenticada.

## **8.2. PageHeader**

Encabezado reutilizable de página con:

* título  
* subtítulo opcional  
* breadcrumbs opcionales  
* acciones a la derecha

## **8.3. KPI Card**

Tarjetas para métricas resumidas.

Deben tener:

* label  
* valor principal  
* opcional: variación / descripción / estado  
* opcional: clickeables hacia vista filtrada

## **8.4. Status Badge**

Badge semántico reutilizable para:

* status de inventario  
* status de pasillo  
* status de revisión  
* trazabilidad  
* éxito/error/warning

## **8.5. Filter Toolbar**

Barra genérica para búsqueda y filtros:

* search input  
* selects  
* chips de filtros rápidos  
* botón reset  
* acciones secundarias si aplica

## **8.6. Primary Table**

Tabla estándar del sistema.

Debe soportar:

* encabezado consistente  
* sort  
* paginación  
* empty states  
* row actions  
* badges  
* densidad consistente

## **8.7. Action Menu**

Menú de acciones por fila para no llenar las tablas de botones innecesarios.

## **8.8. Section Card**

Card genérica para agrupar bloques:

* métricas  
* tablas  
* resumen  
* actividad  
* review history  
* metadata secundaria

## **8.9. Empty State**

Componente para estados sin datos:

* mensaje claro  
* explicación breve  
* CTA principal

## **8.10. Wizard Modal**

Para creación guiada, sobre todo inventarios.

## **8.11. Form Dialog**

Para modales simples como crear pasillo.

## **8.12. Evidence Viewer**

Componente clave para revisión:

* imagen principal  
* zoom  
* fullscreen  
* thumbnails si hay varias  
* nombre de archivo discreto

## **8.13. Review Action Panel**

Panel reutilizable para acciones humanas sobre un resultado:

* confirmar  
* corregir cantidad  
* corregir SKU  
* invalidar

## **8.14. Audit Timeline**

Historial visual de acciones de revisión.

## **8.15. Quick Review Drawer**

Drawer lateral para revisión rápida sin ir al detalle completo.

---

# **9\. Pantalla por pantalla: qué mostrar y cómo**

---

## **9.1. Login**

### **Objetivo**

Permitir acceso al sistema de forma clara y profesional.

### **Contenido**

* logo o nombre del producto  
* título: Admin login / Sign in  
* campo usuario  
* campo contraseña  
* botón principal  
* mensajes de error claros  
* opcional: mostrar/ocultar contraseña

### **Disposición**

Pantalla centrada, simple, sin distracciones.

### **Observación**

No necesita mucha complejidad, pero sí mejor presencia visual que la actual.

---

## **9.2. Dashboard**

### **Objetivo**

Dar una vista global del estado operativo del sistema.

### **Qué mostrar**

#### **Header**

* título: Dashboard  
* subtítulo corto  
* acción rápida opcional: Create Inventory

#### **KPIs superiores**

* Active inventories  
* Pending review  
* Processed aisles  
* Failed jobs  
* Manual corrections  
* Auto-acceptance rate

#### **Bloque “Requires Attention”**

Lista breve de:

* inventarios con errores  
* pasillos fallidos  
* resultados críticos

#### **Bloque “Recent Activity”**

* últimos inventarios creados  
* últimos procesamientos  
* últimas revisiones

#### **Bloque “Recent Inventories”**

Tabla resumida:

* inventory name  
* status  
* aisles  
* pending review  
* last activity  
* action

### **Disposición**

1. header  
2. fila de KPIs  
3. dos columnas intermedias:  
   * requires attention  
   * recent activity  
4. tabla inferior de inventarios recientes

### **Qué no mostrar**

No meter acá detalle de cada pasillo ni analytics profundos.

---

## **9.3. Inventories**

### **Objetivo**

Gestionar todos los inventarios desde una vista administrativa.

### **Qué mostrar**

#### **Header**

* título  
* subtítulo  
* botón Create Inventory

#### **Summary cards**

* Total inventories  
* Draft  
* In progress  
* Completed  
* Needs attention

#### **Filter bar**

* búsqueda por nombre  
* filtro por estado  
* filtro por fecha  
* reset filters

#### **Tabla**

Columnas recomendadas:

* Inventory name  
* Status  
* Created date  
* Aisles  
* Pending review  
* Last activity  
* Actions

### **Disposición**

1. header  
2. summary cards  
3. filter bar  
4. tabla  
5. paginación

### **Observación**

Esta tabla debe permitir priorizar rápido.  
La vista actual es demasiado pobre para eso.

---

## **9.4. Create Inventory**

### **Objetivo**

Crear un inventario en un flujo guiado, corto y claro.

### **Paso 1: Inventory details**

Mostrar:

* inventory name  
* helper text de naming  
* validación inline

### **Paso 2: Visual references (optional)**

Mostrar:

* explicación breve de para qué sirven  
* drag & drop  
* botón select images  
* previews  
* contador de archivos  
* opción remover imagen

### **Disposición**

Wizard modal de 2 pasos.

### **Acciones**

* back  
* continue  
* create inventory  
* cancel

### **Qué evitar**

No hacerlo demasiado complejo. Debe ser simple y profesional.

---

## **9.5. Inventory Detail**

### **Objetivo**

Ser la vista operativa principal de un inventario concreto.

### **Qué mostrar**

#### **Header**

* breadcrumb  
* inventory name  
* badge de status  
* fecha de creación  
* acciones contextuales si aplica

#### **KPIs**

* Total aisles  
* Processed aisles  
* Pending aisles  
* Aisles with errors  
* Pending review results  
* Manual corrections  
* Review completion rate

#### **Tabla de pasillos**

Columnas:

* Aisle code  
* Aisle status  
* Assets uploaded  
* Processing status  
* Results found  
* Pending review  
* Last updated  
* Actions

#### **Sección secundaria opcional**

* recent activity  
* logs recientes  
* visual references asociadas al inventario

### **Disposición**

1. header  
2. KPIs  
3. sección principal: tabla de pasillos  
4. sección secundaria abajo o lateral: actividad/logs

### **Qué evitar**

No mezclar métricas con demasiada metadata.  
La tabla de pasillos debe ser claramente el foco.

---

## **9.6. Create Aisle**

### **Objetivo**

Dar de alta un pasillo rápida y claramente.

### **Qué mostrar**

* aisle code  
* helper text  
* validación inline  
* opcional a futuro: descripción corta

### **Disposición**

Modal simple.

### **Acción post creación**

Idealmente permitir:

* crear otro  
* ir a upload de assets  
* cerrar

---

## **9.7. Aisle Results**

### **Objetivo**

Mostrar todos los resultados de un pasillo y permitir priorizar revisión.

### **Qué mostrar**

#### **Header**

* breadcrumb  
* aisle identification  
* inventory name o contexto  
* acción opcional: open in review queue / refresh

#### **KPI cards**

* Total results  
* Needs review  
* Low confidence  
* Invalid traceability  
* Qty zero  
* With evidence

#### **Filter bar**

* search by SKU  
* quick filters por chips:  
  * All  
  * Needs review  
  * Low confidence  
  * Qty zero  
  * Invalid traceability  
  * Missing evidence  
* filtros adicionales por rango o estado si hace falta

#### **Tabla de resultados**

Columnas sugeridas:

* Priority  
* SKU  
* Quantity  
* Review status  
* Traceability  
* Confidence  
* Evidence  
* Updated  
* Action

### **Disposición**

1. header  
2. KPI cards  
3. filter bar  
4. tabla  
5. paginación

### **Lógica clave**

Esta vista debe ayudar a decidir **qué revisar primero**, no solo listar todo.

---

## **9.8. Review Queue**

### **Objetivo**

Centralizar todos los resultados pendientes o problemáticos del sistema.

### **Qué mostrar**

#### **Header**

* título  
* subtítulo operativo

#### **KPIs**

* Pending review  
* Low confidence  
* Invalid traceability  
* Qty zero  
* Missing evidence

#### **Filter bar avanzada**

* Inventory  
* Aisle  
* Status  
* Confidence range  
* Traceability  
* Evidence present  
* Qty zero  
* búsqueda por SKU

#### **Tabla principal**

Columnas:

* Priority  
* SKU  
* Quantity  
* Confidence  
* Traceability  
* Review status  
* Inventory  
* Aisle  
* Updated  
* Actions

#### **Acción secundaria importante**

Quick Review desde la fila.

### **Disposición**

1. header  
2. KPIs  
3. filtros  
4. tabla priorizada  
5. paginación

### **Observación**

Esta pantalla tiene que convertirse en una de las más importantes del producto.  
Hoy no existe bien resuelta y es una gran oportunidad.

---

## **9.9. Result Review Detail**

### **Objetivo**

Permitir revisar un resultado individual con foco en la decisión humana.

### **Disposición obligatoria**

**Dos columnas desktop.**

### **Columna izquierda**

#### **Evidence Viewer**

* imagen principal grande  
* zoom  
* fullscreen  
* miniaturas si hay varias imágenes  
* filename discreto  
* no galería vertical gigante  
* no overlays innecesarios

### **Columna derecha**

#### **Result Summary**

Mostrar:

* SKU detectado  
* current quantity  
* count source  
* confidence  
* traceability status  
* review status  
* updated timestamp

#### **Review Actions**

Debe ser el bloque más visible después del resumen.

Acciones:

* Confirm result  
* Correct quantity  
* Correct SKU  
* Mark invalid / delete

Debe estar claramente separado por grupos:

* confirmación rápida  
* corrección  
* acción destructiva

#### **Navigation**

* previous / next result

### **Sección inferior secundaria**

* review history timeline  
* technical metadata colapsable

### **Qué evitar**

* parecer pantalla de debugging  
* muchas imágenes una abajo de otra  
* metadata técnica arriba  
* acciones escondidas

---

## **9.10. Quick Review Drawer**

### **Objetivo**

Permitir revisión rápida desde una tabla sin navegar a la pantalla completa.

### **Qué mostrar**

* evidencia pequeña o mediana  
* SKU  
* cantidad  
* confianza  
* trazabilidad  
* estado  
* acciones rápidas:  
  * confirm  
  * correct quantity  
  * correct SKU  
  * mark invalid  
  * open full detail

### **Uso**

Se abre desde:

* Review Queue  
* Aisle Results

### **Valor**

Esto te puede dar un salto enorme en productividad operativa.

---

## **9.11. Metrics / Analytics**

### **Objetivo**

Separar análisis y performance de la operación diaria.

### **Qué mostrar**

#### **KPIs**

* Auto-acceptance rate  
* Manual correction rate  
* Invalid traceability rate  
* Processing success rate  
* Average review time  
* Reviewed results per day

#### **Gráficos o bloques analíticos**

* trends over time  
* inventories with highest correction rate  
* aisles with frequent issues  
* low confidence patterns

#### **Tabla comparativa**

* inventory performance summary

### **Disposición**

1. header  
2. KPIs  
3. gráficos / análisis  
4. tabla de performance

### **Qué evitar**

No usar esta pantalla como reemplazo del dashboard operativo.

---

# **10\. Reglas para tablas**

Todas las tablas importantes del sistema deben soportar:

* búsqueda  
* filtros  
* sort  
* paginación  
* empty state  
* loading state  
* row hover  
* row actions consistentes  
* badges consistentes  
* buena densidad

Además, cada tabla debe tener una lógica clara de prioridad:

* qué filas son críticas  
* cuáles son warning  
* cuáles están resueltas

---

# **11\. Reglas para estados y badges**

Hay que formalizar una taxonomía.

## **Inventario**

* Draft  
* In progress  
* Completed  
* Archived

## **Pasillo**

* Empty  
* Assets uploaded  
* Processing  
* Processed  
* Error

## **Resultado de revisión**

* Pending review  
* Confirmed  
* Corrected  
* Deleted

## **Calidad**

* Valid traceability  
* Invalid traceability  
* Low confidence

Cada uno debe mapear a badges consistentes con la semántica de color definida antes.

---

# **12\. Acciones principales y secundarias**

La UI actual mezcla demasiado las acciones.  
Hay que normalizar esto.

## **Acciones primarias**

Una por contexto principal.  
Ejemplos:

* Create Inventory  
* Process Aisle  
* Confirm Result  
* Save Correction

## **Acciones secundarias**

* Open  
* View Results  
* Upload  
* Refresh  
* Back

## **Acciones terciarias**

* View log  
* Show technical metadata  
* Export  
* Open full detail

Esto tiene que reflejarse en:

* color  
* tamaño  
* ubicación  
* peso visual

---

# **13\. Qué contenido debe quedar secundario o colapsado**

Hay datos que hoy aparecen demasiado expuestos y deben bajar de prioridad.

## **Deben ser secundarios**

* metadata técnica detallada  
* logs completos  
* datos muy internos del pipeline  
* identificadores técnicos extensos  
* timestamps secundarios repetidos

## **Dónde mostrarlos**

* acordeones  
* pestañas secundarias  
* drawers  
* paneles colapsables  
* modales específicos

La experiencia principal debe estar orientada al trabajo operativo, no a debug técnico.

---

# **14\. Qué patrones de UX hay que introducir sí o sí**

## **14.1. Breadcrumbs**

Para ubicar al usuario en la jerarquía.

## **14.2. Empty states**

Para inventarios, pasillos, resultados, review queue vacía.

## **14.3. Loading states**

Skeletons o placeholders suaves.

## **14.4. Success feedback**

Snackbar o alert tras:

* crear inventario  
* crear pasillo  
* subir imágenes  
* procesar  
* confirmar revisión  
* corregir cantidad o SKU

## **14.5. Confirmaciones**

Para acciones destructivas como delete / mark invalid.

## **14.6. Estados clickeables**

Cuando una métrica tenga sentido, debe llevar a una vista filtrada.

---

# **15\. Qué errores hay que evitar en la implementación**

## **15.1. No caer en una UI demasiado template**

Tiene que sentirse como producto real, no demo SaaS genérica.

## **15.2. No mezclar operación con debugging**

El usuario no debe sentir que está usando una consola técnica.

## **15.3. No saturar de cards**

No todo merece una card.

## **15.4. No duplicar datos**

Cada nivel de vista debe mostrar solo lo necesario.

## **15.5. No sobrecargar con color**

El color debe comunicar, no decorar.

## **15.6. No llenar tablas de botones**

Usar action menus donde haga falta.

## **15.7. No esconder la acción principal**

Siempre debe quedar obvio qué hacer.

---

# **16\. Priorización de implementación recomendada**

Para empezar con Material UI, yo priorizaría así:

## **Fase 1 — base del sistema**

* AppShell  
* Sidebar  
* Topbar  
* PageHeader  
* StatusBadge  
* KPI Card  
* Primary Table  
* Filter Toolbar  
* Empty State

## **Fase 2 — pantallas core**

* Dashboard  
* Inventories  
* Inventory Detail  
* Aisle Results

## **Fase 3 — revisión**

* Review Queue  
* Result Review Detail  
* Quick Review Drawer  
* Review Action Panel  
* Audit Timeline

## **Fase 4 — auxiliares**

* Create Inventory Wizard  
* Create Aisle Modal  
* Upload flows  
* Logs secundarios

## **Fase 5 — analytics**

* Metrics / Analytics

---

# **17\. Visión final del producto**

La dirección correcta para Dinamic Inventory v3 no es una app recargada, sino una plataforma con esta lógica:

* **navegación persistente**  
* **home operativa clara**  
* **inventarios bien administrables**  
* **pasillos bien visibles**  
* **resultados revisables a escala**  
* **detalle de revisión enfocado**  
* **analytics separado**  
* **colores semánticos consistentes**  
* **componentes reutilizables y sobrios**

En resumen:  
el sistema tiene que pasar de ser una herramienta funcional con pantallas aisladas a ser una **plataforma enterprise de revisión operativa y calidad de inventarios**.