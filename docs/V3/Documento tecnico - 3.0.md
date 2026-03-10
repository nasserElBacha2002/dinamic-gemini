# **Documento Técnico — Dinamic Inventory v3.0**

## **1\. Propósito del documento**

Definir formalmente la **versión 3.0** de Dinamic Inventory como la primera versión operativa del sistema orientada a inventarios reales, con:

* backend basado en entidades de negocio,  
* frontend web en React,  
* procesamiento por pasillo,  
* persistencia de resultados,  
* revisión manual,  
* métricas básicas,  
* y una arquitectura alineada con **principios SOLID**.

También se dejan definidos, a menor nivel, los lineamientos de evolución para **v3.1** y **v3.2**.

---

# **2\. Objetivo de la versión 3.0**

La versión 3.0 debe transformar el sistema actual, que hoy está más cerca de un pipeline técnico, en una **plataforma operativa de inventario**.

El usuario debe poder:

* crear un inventario,  
* crear uno o más pasillos dentro de ese inventario,  
* subir múltiples fotos o video por pasillo,  
* disparar procesamiento automáticamente,  
* visualizar resultados estructurados por posición/pallet,  
* revisar evidencia visual,  
* corregir conteos o identificaciones,  
* eliminar detecciones erróneas,  
* consultar métricas básicas de éxito del inventario.

La v3.0 no busca resolver todavía toda la complejidad futura del producto. Su meta es construir una **base operativa robusta, clara y extensible**.

---

# **3\. Objetivos funcionales**

## **3.1 Objetivos de negocio**

* Representar un inventario con entidades reales del dominio.  
* Organizar el procesamiento por pasillo.  
* Permitir revisión manual eficiente por unidad lógica.  
* Medir calidad operativa del inventario.

## **3.2 Objetivos técnicos**

* Desacoplar el dominio de negocio del pipeline técnico.  
* Hacer que la base de datos sea la fuente de verdad del sistema.  
* Mantener trazabilidad entre input, evidencia, resultado detectado y corrección.  
* Exponer una API REST para consumo desde React.  
* Diseñar la arquitectura respetando SOLID.

## **3.3 Objetivos de producto**

* Abandonar la lógica de “subir archivo y recibir output”.  
* Adoptar una lógica de “operar inventarios revisables”.  
* Permitir crecimiento futuro sin rehacer la base.

---

# **4\. Alcance de la versión 3.0**

## **4.1 Incluido en v3.0**

* creación y consulta de inventarios,  
* creación y consulta de pasillos,  
* carga de múltiples fotos,  
* carga de video,  
* assets mixtos por pasillo,  
* procesamiento interno asociado al pasillo,  
* resultados estructurados por posición,  
* productos detectados por posición,  
* evidencias visuales asociadas,  
* revisión manual básica,  
* eliminación lógica,  
* métricas básicas,  
* frontend web React,  
* auditoría mínima de correcciones.

## **4.2 Fuera de alcance en v3.0**

* roles y permisos avanzados,  
* edición colaborativa multiusuario,  
* reprocesamiento selectivo desde la UI,  
* normalización avanzada de etiquetas y posiciones,  
* comparación histórica entre inventarios,  
* integración con WMS externo,  
* merge/split manual de pallets,  
* reglas complejas de layout físico del depósito.

---

# **5\. Principios de arquitectura**

## **5.1 Principio general**

La versión 3.0 debe construirse como una arquitectura orientada a dominio, con separación clara entre:

* **dominio de negocio**,  
* **casos de uso / aplicación**,  
* **infraestructura**,  
* **interfaces externas**.

## **5.2 Reglas estructurales**

* El frontend no debe depender de detalles internos del pipeline.  
* El frontend es una aplicación independiente en **`frontend/`** en la raíz del repositorio (ver FRONTEND_ESTRUCTURA.md).  
* El dominio no debe depender de frameworks.  
* Los jobs son internos del backend; no son la unidad principal expuesta al usuario.  
* Las entidades de negocio deben modelar la operación real.  
* La salida del pipeline debe convertirse en entidades del dominio persistidas en DB.

## **5.3 Fuente de verdad**

* **Base de datos**: estado del negocio, resultados, correcciones, métricas.  
* **Storage**: archivos pesados, imágenes, videos, crops, anotaciones.

---

# **6\. Aplicación de principios SOLID**

Este punto es central para la v3.0.

## **6.1 Single Responsibility Principle**

Cada módulo o clase debe tener una única razón de cambio.

### **Ejemplos**

* `InventoryService`: orquesta casos de uso de inventario, no procesa imágenes.  
* `AisleProcessingService`: dispara procesamiento sobre un pasillo, no sirve endpoints HTTP.  
* `EvidenceRepository`: persiste evidencias, no calcula métricas.  
* `MetricsService`: calcula métricas, no modifica resultados detectados.  
* `PositionReviewService`: aplica correcciones, no ejecuta detección.

## **6.2 Open/Closed Principle**

El sistema debe poder extenderse sin modificar el núcleo.

### **Ejemplos**

* agregar un nuevo tipo de `AnalysisProvider` sin tocar el dominio,  
* incorporar normalización de imágenes en v3.2 como estrategia adicional,  
* sumar exportadores CSV/Excel/JSON sin modificar servicios centrales.

## **6.3 Liskov Substitution Principle**

Las implementaciones concretas deben ser intercambiables sin romper el contrato.

### **Ejemplos**

* `FileSystemArtifactStorage` y `S3ArtifactStorage` deben respetar el mismo contrato,  
* `GeminiAnalysisProvider` y futuros proveedores deben devolver salidas compatibles,  
* `SqlJobRepository` e implementaciones mock deben comportarse igual desde el punto de vista del caso de uso.

## **6.4 Interface Segregation Principle**

Las interfaces deben ser pequeñas y específicas.

### **Ejemplos**

No tener una interfaz gigante tipo:

* `InventorySystemManager`

Sino varias interfaces pequeñas:

* `InventoryRepository`  
* `AisleRepository`  
* `PositionRepository`  
* `ArtifactStorage`  
* `AnalysisProvider`  
* `MetricsCalculator`  
* `ReviewRepository`

## **6.5 Dependency Inversion Principle**

Los casos de uso deben depender de abstracciones, no de implementaciones concretas.

### **Ejemplos**

* `ProcessAisleUseCase` depende de `AnalysisProvider`, `JobRepository`, `PositionRepository`, `ArtifactStorage`.  
* No debe instanciar directamente Gemini, filesystem o SQL local.

---

# **7\. Modelo de dominio**

## **7.1 Inventory**

Entidad raíz del negocio. Representa una sesión de inventario.

### **Responsabilidad**

Agrupar pasillos, representar el estado global y consolidar métricas.

### **Campos sugeridos**

* `id`  
* `warehouse_id` opcional  
* `name`  
* `status`  
* `created_at`  
* `updated_at`  
* `completed_at` opcional

### **Estados**

* `draft`  
* `processing`  
* `in_review`  
* `completed`  
* `failed`

### **Transiciones de estado**

* `draft` → `processing`: cuando al menos un pasillo del inventario pasa a `queued` o `processing`.
* `processing` → `in_review`: cuando todos los pasillos han terminado el procesamiento automático y están listos para revisión (p. ej. todos en `processed` o `in_review`).
* `in_review` → `completed`: por acción explícita de cierre de inventario en la UI (recomendado: no automático).
* Cualquier estado → `failed`: solo si falla una operación crítica a nivel inventario (p. ej. error de sistema).
* Transiciones no permitidas: no se puede volver de `completed` o `failed` a estados previos en v3.0.

---

Unidad operativa principal de la v3.0.

### **Responsabilidad**

Representar el procesamiento y revisión de un pasillo independiente.

### **Campos sugeridos**

* `id`  
* `inventory_id`  
* `code` o `name`  
* `status`  
* `created_at`  
* `updated_at`

### **Estados**

* `created`  
* `assets_uploaded`  
* `queued`  
* `processing`  
* `processed`  
* `in_review`  
* `completed`  
* `failed`

### **Transiciones de estado**

* `created` → `assets_uploaded`: cuando se sube al menos un asset (foto o video) al pasillo.
* `assets_uploaded` → `queued`: cuando se encola el procesamiento del pasillo.
* `queued` → `processing`: cuando un worker toma el job asociado al pasillo.
* `processing` → `processed`: cuando el pipeline termina correctamente y los resultados están listos para persistir/revisión.
* `processed` → `in_review`: estado listo para revisión humana (puede ser implícito al persistir posiciones).
* `in_review` → `completed`: por acción explícita de cierre del pasillo (recomendado).
* Cualquier estado operativo → `failed`: cuando falla la subida de assets, el pipeline o una operación crítica; el pasillo debe exponer un resumen de error (ver modelo de error operativo).
* Transiciones no permitidas: no se puede volver de `completed` o `failed` sin lógica explícita (fuera de v3.0).

---

## **7.3 SourceAsset**

Representa una entrada bruta asociada a un pasillo.

### **Tipos**

* `photo`  
* `video`

### **Campos sugeridos**

* `id`  
* `aisle_id`  
* `type`  
* `original_filename`  
* `storage_path`  
* `mime_type`  
* `metadata_json`  
* `uploaded_at`

---

## **7.4 Position**

**Definición canónica:** `Position` es la **unidad revisable** de la v3.0. En la práctica representa una **unidad de inventario tipo pallet detectada por el pipeline**, no un slot físico del depósito ya mapeado. Cada posición corresponde a una detección lógica (un pallet detectado) sobre la que el usuario puede confirmar, corregir o eliminar.

### **Responsabilidad**

Agrupar evidencia y productos asociados a una posición detectada.

### **Campos sugeridos**

* `id`  
* `aisle_id`  
* `status`  
* `confidence`  
* `needs_review`  
* `primary_evidence_id`  
* `detected_summary_json`  
* `corrected_summary_json` opcional  
* `created_at`  
* `updated_at`

### **Estados**

* `detected`  
* `reviewed`  
* `corrected`  
* `deleted`

### **Significado de cada estado**

* **`reviewed`**: el usuario confirmó la posición **sin cambios** (aceptación explícita).
* **`corrected`**: el usuario modificó cantidad y/o SKU de al menos un producto asociado.
* **`deleted`**: eliminación **lógica**; la posición no se borra físicamente pero deja de contar para el inventario.

### **Transiciones de estado**

* `detected` → `reviewed`: cuando el usuario confirma sin cambios (acción `confirm`).
* `detected` → `corrected`: cuando el usuario modifica cantidad o SKU (acciones `update_quantity`, `update_sku`).
* `detected` → `deleted`: cuando el usuario elimina lógicamente la posición (acción `delete_position`).
* En v3.0, `reviewed`, `corrected` y `deleted` son **terminales**; no se define lógica de reapertura.

---

## **7.5 ProductRecord**

Representa un producto detectado dentro de una posición.

### **Campos sugeridos**

* `id`  
* `position_id`  
* `sku`  
* `description`  
* `detected_quantity`  
* `corrected_quantity` opcional  
* `confidence`  
* `created_at`  
* `updated_at`

---

## **7.6 Evidence**

Representa una evidencia visual asociada a una entidad.

### **Tipos posibles**

* `original_image`  
* `video_frame`  
* `position_crop`  
* `product_crop`  
* `label_crop`  
* `annotated_image`

### **Campos sugeridos**

* `id`  
* `entity_type`  
* `entity_id`  
* `type`  
* `storage_path`  
* `source_asset_id`  
* `frame_index` opcional  
* `timestamp_ms` opcional  
* `bbox_json` opcional  
* `quality_score` opcional  
* `is_primary`

---

## **7.7 ReviewAction**

Representa una acción manual de revisión.

### **Campos sugeridos**

* `id`  
* `position_id`  
* `action_type`  
* `before_json`  
* `after_json`  
* `created_at`  
* `user_id` opcional  
* `comment` opcional

### **Tipos de acción**

* `confirm`  
* `update_quantity`  
* `update_sku`  
* `delete_position`

---

## **7.8 Job**

Entidad técnica interna del backend.

### **Responsabilidad**

Representar el trabajo técnico asociado a un pasillo.

### **Campos sugeridos**

* `id`  
* `target_type`  
* `target_id`  
* `job_type`  
* `status`  
* `payload_json`  
* `result_json` opcional  
* `error_message` opcional  
* `created_at`  
* `updated_at`

### **Asociación recomendada**

* `target_type = aisle`  
* `target_id = aisle_id`

---

# **8\. Arquitectura lógica**

## **8.1 Capas**

### **Capa de dominio**

Contiene:

* entidades,  
* value objects,  
* reglas básicas del negocio,  
* contratos de repositorios.

### **Capa de aplicación**

Contiene:

* casos de uso,  
* orquestación,  
* validaciones de flujo,  
* coordinación entre dominio e infraestructura.

### **Capa de infraestructura**

Contiene:

* repositorios SQL,  
* filesystem o storage,  
* adaptadores del pipeline,  
* colas de jobs,  
* proveedores LLM/vision.

### **Capa de interfaces**

Contiene:

* API REST,  
* frontend React,  
* DTOs,  
* serialización.

---

# **9\. Contratos clave por abstracción**

Para respetar SOLID, estos contratos deberían existir desde el inicio.

## **9.1 Repositorios**

* `InventoryRepository`  
* `AisleRepository`  
* `SourceAssetRepository`  
* `PositionRepository`  
* `ProductRecordRepository`  
* `EvidenceRepository`  
* `ReviewActionRepository`  
* `JobRepository`

## **9.2 Infraestructura**

* `ArtifactStorage`  
* `AnalysisProvider`  
* `JobQueue`  
* `MetricsCalculator`  
* `ResultMapper`

## **9.3 Casos de uso**

* `CreateInventoryUseCase`  
* `CreateAisleUseCase`  
* `UploadAisleAssetsUseCase`  
* `ProcessAisleUseCase`  
* `GetAisleResultsUseCase`  
* `ReviewPositionUseCase`  
* `DeletePositionUseCase`  
* `GetInventoryMetricsUseCase`

## **9.4 Contrato de salida del pipeline para el mapeador**

El backend debe consumir la salida del pipeline de análisis y mapearla a entidades de dominio. Este contrato define la **forma mínima** que debe tener esa salida. El pipeline puede emitir campos adicionales que el mapeador ignore.

### **Estructura mínima esperada**

* **`positions[]`** (array de objetos), uno por posición/pallet detectado.

### **Por cada elemento de `positions[]`**

| Campo | Obligatorio | Descripción |
|-------|-------------|-------------|
| `id` o referencia externa | Sí | Identificador único de la detección (p. ej. para vincular evidencias). |
| `confidence` | Sí | Número en [0, 1]. |
| `needs_review` | Recomendado | Booleano; si falta, el mapeador puede derivarlo (p. ej. confidence &lt; umbral). |
| `primary_evidence_id` | Recomendado | ID de la evidencia principal para la UI. |
| `products[]` | Sí | Array de productos detectados en esta posición (puede ser vacío). |

### **Por cada elemento de `products[]` (dentro de una posición)**

| Campo | Obligatorio | Descripción |
|-------|-------------|-------------|
| `sku` | Sí | Código o identificador del producto (puede ser "unknown" o equivalente). |
| `description` | Opcional | Texto legible. |
| `quantity` | Sí | Cantidad detectada (entero). |
| `confidence` | Opcional | Confianza de la detección del producto. |

### **Evidencias**

* El pipeline debe emitir referencias a evidencias (p. ej. IDs o rutas) que el mapeador persista como entidades `Evidence`, asociadas a la posición por `entity_type`/`entity_id`.
* Al menos una evidencia por posición debe poder marcarse como principal (`is_primary` o equivalente).

### **Incertidumbre / motivos de revisión**

* Opcional: el pipeline puede incluir un campo (p. ej. `review_reason` o `uncertainty`) para indicar por qué se marca `needs_review`; el mapeador puede persistirlo o usarlo solo para lógica interna.

---

## **9.5 Modelo de error operativo**

Los fallos no deben exponerse al frontend como detalles crudos del job. Deben reflejarse en el **dominio operativo** (Aisle, y derivable a Inventory).

### **Campos recomendados en respuestas de error o estado fallido**

* **`error_code`**: código estable para el tipo de fallo (recomendación: lista cerrada). Ejemplos propuestos: `ASSET_UPLOAD_FAILED`, `PIPELINE_FAILED`, `TIMEOUT`, `VALIDATION_ERROR`.
* **`error_message`**: mensaje legible para el usuario o logs.
* **`retryable`**: booleano que indica si tiene sentido reintentar la operación.

### **Reflejo en Aisle**

* Cuando un pasillo falla (upload, pipeline, etc.), el **Aisle** debe actualizarse a `status = failed` y exponer un resumen operativo, por ejemplo:
  * `aisle.error_code`
  * `aisle.error_message`
  * `aisle.retryable` (opcional).
* El frontend consume el estado del **pasillo** (y, si aplica, del inventario); no debe depender de `job_id` ni del mensaje de error técnico del worker como recurso principal.

### **Inventario**

* Si se define un estado `failed` a nivel inventario, debe reservarse para fallos críticos de operación a ese nivel; el estado de los pasillos individuales sigue siendo la fuente de verdad para fallos por pasillo.

---

## **9.6 Métricas canónicas**

Las métricas se calculan sobre posiciones **ya revisadas** (estado terminal), no sobre pendientes. Definición canónica para `GET /inventories/{inventoryId}/metrics` y uso interno:

* **`total_reviewed_positions`** = cantidad de posiciones con `status` en `(reviewed, corrected, deleted)` dentro del inventario (suma sobre todos sus pasillos).
* **`auto_accepted_positions`** = cantidad de posiciones con `status = reviewed` (aceptadas sin cambios).
* **`corrected_positions`** = cantidad de posiciones con `status = corrected`.
* **`deleted_positions`** = cantidad de posiciones con `status = deleted`.

* **`success_rate`** = `auto_accepted_positions / total_reviewed_positions * 100` si `total_reviewed_positions > 0`, si no `0`.
* **`correction_rate`** = `corrected_positions / total_reviewed_positions * 100` (mismo denominador).
* **`deletion_rate`** = `deleted_positions / total_reviewed_positions * 100` (mismo denominador).

Momento de cálculo: en tiempo de consulta al llamar al endpoint de métricas (no necesariamente persistidas como campos; pueden computarse desde los conteos por estado).

---

## **9.7 Paginación y filtros para GET /aisles/{aisleId}/positions**

El endpoint `GET /aisles/{aisleId}/positions` debe soportar:

### **Paginación**

* **`page`**: número de página (recomendado: por defecto `1`).
* **`page_size`**: tamaño de página (recomendado: por defecto `25` o `50`).

### **Filtros**

* **`status`**: filtrar por estado de la posición (`detected`, `reviewed`, `corrected`, `deleted`). Valores permitidos: los mismos que el modelo de dominio.
* **`needs_review`**: booleano; filtrar posiciones que requieren revisión.
* **`min_confidence`**: número en [0, 1]; solo posiciones con `confidence >= min_confidence`.
* **`sku`**: búsqueda por SKU (o texto) en los productos asociados a la posición; devolver posiciones que contengan al menos un producto que coincida.

Si los valores por defecto de paginación no están confirmados por producto, se recomienda `page=1` y `page_size=25` como estándar.

---

# **10\. Flujo operativo de la v3.0**

## **10.1 Crear inventario**

El usuario crea una sesión de inventario.

## **10.2 Crear pasillo**

Dentro del inventario, el usuario crea un pasillo.

## **10.3 Subir assets**

Sube:

* múltiples fotos,  
* un video,  
* o una mezcla.

## **10.4 Disparo de procesamiento**

El backend:

* registra los assets,  
* crea jobs internos,  
* envía a cola o procesamiento,  
* actualiza el estado del pasillo.

## **10.5 Procesamiento técnico**

El pipeline:

* analiza inputs,  
* detecta posiciones,  
* detecta productos,  
* genera evidencias,  
* consolida resultados.

## **10.6 Persistencia del dominio**

El resultado técnico se mapea a:

* `Position`  
* `ProductRecord`  
* `Evidence`

## **10.7 Revisión manual**

Desde la web:

* el usuario confirma,  
* corrige,  
* elimina.

## **10.8 Métricas**

El sistema calcula:

* posiciones aceptadas automáticamente,  
* posiciones corregidas,  
* posiciones eliminadas,  
* success rate.

---

# **11\. Fases de implementación v3.0**

## **Fase 0 — Diseño y contratos**

### **Objetivo**

Cerrar modelo, estados, contratos y límites de la versión.

### **Entregables**

* documento de dominio,  
* contratos de abstracción,  
* endpoints iniciales,  
* mapa de responsabilidades por módulo.

### **Criterio de salida**

Ninguna implementación concreta debería comenzar sin estos contratos definidos.

---

## **Fase 1 — Persistencia del dominio**

### **Objetivo**

Implementar la base persistente del modelo.

### **Alcance**

* tablas SQL,  
* repositorios,  
* entidades,  
* estados del dominio.

### **Entregables**

* schema inicial,  
* repositorios concretos SQL,  
* migraciones,  
* tests básicos de persistencia.

### **Criterio de aceptación**

Se puede crear inventario, pasillo, asset y job, y consultar su estado.

---

## **Fase 2 — Ingesta de assets por pasillo**

### **Objetivo**

Permitir carga de múltiples archivos asociados a un pasillo.

### **Alcance**

* endpoint de creación de pasillo,  
* endpoint de upload,  
* storage físico,  
* metadata,  
* validación de formatos.

### **Criterio de aceptación**

Un pasillo puede quedar asociado a múltiples imágenes y/o un video.

---

## **Fase 3 — Orquestación de procesamiento**

### **Objetivo**

Conectar la carga del pasillo con el pipeline interno.

### **Alcance**

* creación de jobs,  
* cola o ejecución,  
* actualización de estados,  
* manejo de errores.

### **Criterio de aceptación**

El pasillo cambia de estado según el avance del procesamiento.

---

## **Fase 4 — Mapeo del pipeline al dominio**

### **Objetivo**

Transformar la salida técnica en resultados persistidos del dominio.

### **Alcance**

* creación de posiciones,  
* creación de productos,  
* asociación de evidencias,  
* selección de evidencia principal.

### **Criterio de aceptación**

Un pasillo procesado ya puede consultarse como tabla de resultados, sin depender de artifacts técnicos crudos.

---

## **Fase 5 — API REST de lectura**

### **Objetivo**

Exponer recursos del dominio a la web.

### **Endpoints mínimos**

* `POST /inventories`  
* `GET /inventories`  
* `GET /inventories/{id}`  
* `POST /inventories/{inventoryId}/aisles`  
* `GET /inventories/{inventoryId}/aisles`  
* `GET /aisles/{id}`  
* `POST /aisles/{id}/assets`  
* `GET /aisles/{id}/positions`  
* `GET /positions/{id}`  
* `GET /inventories/{id}/metrics`

### **Criterio de aceptación**

React puede consumir el backend sin depender de rutas técnicas internas del pipeline.

---

## **Fase 6 — Frontend React base**

### **Objetivo**

Crear la primera interfaz operativa usable.

### **Pantallas**

* listado de inventarios,  
* detalle de inventario,  
* carga de pasillo,  
* detalle de pasillo,  
* tabla de posiciones,  
* detalle de posición.

### **Criterio de aceptación**

Un usuario puede operar el flujo completo desde la web.

---

## **Fase 7 — Revisión manual básica**

### **Objetivo**

Cerrar el loop humano del inventario.

### **Funcionalidades**

* confirmar posición,  
* corregir SKU,  
* corregir cantidad,  
* eliminar lógicamente.

### **Endpoints**

* `PATCH /positions/{id}`  
* `POST /positions/{id}/reviews`

### **Criterio de aceptación**

Toda corrección queda persistida y auditada.

---

## **Fase 8 — Métricas y cierre**

### **Objetivo**

Medir la calidad del inventario y permitir finalización.

### **Métricas mínimas**

* total_reviewed_positions, corrected_positions, deleted_positions, auto_accepted_positions (ver §9.6)  
* success_rate, correction_rate, deletion_rate  
* unknown products (opcional)

### **Definición canónica**

Ver **§9.6 Métricas canónicas** de este documento.

### **Criterio de aceptación**

Se pueden consultar métricas y cerrar un inventario cuando todos sus pasillos estén finalizados.

---

# **12\. API funcional mínima**

## **Inventarios**

* `POST /inventories`  
* `GET /inventories`  
* `GET /inventories/{inventoryId}`

## **Pasillos**

* `POST /inventories/{inventoryId}/aisles`  
* `GET /inventories/{inventoryId}/aisles`  
* `GET /aisles/{aisleId}`

## **Assets**

* `POST /aisles/{aisleId}/assets`

## **Resultados**

* `GET /aisles/{aisleId}/positions` — soporta paginación (`page`, `page_size`) y filtros (`status`, `needs_review`, `min_confidence`, `sku`). Ver §9.7.
* `GET /positions/{positionId}`

## **Revisión**

* `PATCH /positions/{positionId}`  
* `POST /positions/{positionId}/reviews`

## **Métricas**

* `GET /inventories/{inventoryId}/metrics` — devuelve métricas canónicas definidas en §9.6 (total_reviewed_positions, auto_accepted_positions, success_rate, correction_rate, deletion_rate, etc.).

---

# **13\. Frontend React v3.0**

## **Objetivo**

Brindar una interfaz clara de operación y revisión.

## **Ubicación del frontend**

La aplicación frontend vive en la carpeta **`frontend/`** en la **raíz del repositorio**. No forma parte de `src/` ni de carpetas bajo el backend. Ver **FRONTEND_ESTRUCTURA.md** para la estructura canónica.

## **Stack oficial**

* React  
* TypeScript  
* Material UI (MUI)  
* React Router  
* TanStack Query  
* **MUI Data Grid** para tablas operativas complejas (posiciones, inventarios, pasillos, productos, historial de revisión)

Para tablas muy simples puede usarse el componente `Table` de MUI; para listas operativas con filtros, ordenación y paginación, el estándar es **MUI Data Grid**.

## **Vistas mínimas**

### **InventoriesPage**

* listar inventarios,  
* crear inventario.

### **InventoryDetailPage**

* ver información general,  
* listar pasillos,  
* crear pasillo.

### **AisleUploadPage / AisleDetailPage**

* subir fotos o video,  
* visualizar estado,  
* ver progreso.

### **AisleResultsPage**

* tabla de posiciones con filtros por:  
  * estado,  
  * confianza,  
  * revisión pendiente.

### **PositionDetailPage**

* ver evidencia,  
* ver productos,  
* editar resultados,  
* eliminar posición.

---

# **14\. Historias de usuario prioritarias**

* Como operador, quiero crear un inventario para agrupar el trabajo de una sesión.  
* Como operador, quiero crear un pasillo dentro de un inventario para procesarlo por separado.  
* Como operador, quiero subir múltiples fotos o video para representar correctamente un pasillo.  
* Como operador, quiero ver el estado de procesamiento de un pasillo.  
* Como revisor, quiero ver una tabla con posiciones detectadas y evidencia asociada.  
* Como revisor, quiero abrir una posición y ver su detalle.  
* Como revisor, quiero corregir cantidades o SKU.  
* Como revisor, quiero eliminar una posición mal detectada.  
* Como responsable, quiero ver métricas básicas de éxito del inventario.

---

# **15\. Riesgos técnicos y mitigación**

## **Riesgo 1**

Acoplar el frontend al pipeline actual.

### **Mitigación**

Exponer solo recursos del dominio.

## **Riesgo 2**

Permitir que una sola clase controle demasiada lógica.

### **Mitigación**

Separar casos de uso, repositorios y servicios especializados.

## **Riesgo 3**

No conservar el resultado original detectado.

### **Mitigación**

Guardar detected y corrected por separado, con review actions.

## **Riesgo 4**

No modelar correctamente la evidencia.

### **Mitigación**

Evidence como entidad de primera clase desde v3.0.

## **Riesgo 5**

Diseño cerrado a un único proveedor o storage.

### **Mitigación**

Introducir interfaces desde el inicio.

---

# **16\. Criterios de aceptación globales v3.0**

La v3.0 se considera lograda si:

* existe una entidad `Inventory` operable,  
* cada inventario puede tener múltiples `Aisle`,  
* cada pasillo puede recibir múltiples fotos o video,  
* el procesamiento interno queda asociado al pasillo,  
* la salida del pipeline queda persistida como `Position`, `ProductRecord` y `Evidence`,  
* existe una web React funcional,  
* el usuario puede revisar y corregir,  
* el sistema conserva auditoría básica,  
* se calculan métricas mínimas,  
* la arquitectura permite extenderse sin romper el núcleo.

---

# **17\. Lineamientos resumidos para v3.1**

## **Objetivo**

Mejorar calidad de revisión, trazabilidad y precisión.

## **Alcances posibles**

* consolidación avanzada de evidencias,  
* mejor selección de evidencia principal,  
* score de calidad de evidencia,  
* filtros de revisión avanzados,  
* mejoras del prompt y asociación etiqueta/producto,  
* exportaciones CSV/Excel/JSON,  
* snapshots pre y post revisión,  
* métricas más ricas por error y por pasillo.

## **Principio rector**

Extender la v3.0 sin reescribir sus bases.

---

# **18\. Lineamientos resumidos para v3.2**

## **Objetivo**

Dar madurez operativa y preparación para entornos más reales.

## **Alcances posibles**

* normalización avanzada de imágenes,  
* reprocesamiento selectivo,  
* roles y multiusuario,  
* auditoría ampliada,  
* comparativas históricas,  
* integración con sistemas externos,  
* versionado más fuerte del resultado.

## **Principio rector**

Apoyarse en las abstracciones creadas en v3.0 para agregar nuevas capacidades sin acoplamiento excesivo.

---

# **19\. Recomendación final**

La v3.0 no debe perseguir perfección algorítmica ni complejidad enterprise.  
Debe construir una base correcta, usable y extensible.

La decisión más importante es esta:

**el sistema debe modelar inventarios y pasillos como conceptos de negocio, y dejar los jobs como detalle técnico interno.**

Si eso se respeta, y además se implementa con contratos claros, responsabilidades separadas y dependencias invertidas, la base de la plataforma va a quedar alineada con SOLID y preparada para crecer hacia v3.1 y v3.2 sin necesidad de rediseño estructural.

