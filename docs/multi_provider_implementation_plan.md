
# Multi-Provider Implementation Plan (Final, Strategy + Adapter)

> **Alineación 2026-04:** reglas ampliadas, DoD y matriz de tests en inglés: [`multi_provider_planning_revision.md`](./multi_provider_planning_revision.md). Este documento conserva el plan operativo en español.

## 1. Objetivo

Evolucionar Dinamic Inventory v3 desde un modelo acoplado implícitamente a:

* un proveedor
* un modelo
* un prompt
* un único resultado efectivo por pasillo

hacia una arquitectura que soporte:

* múltiples proveedores
* múltiples modelos por proveedor
* múltiples prompts o variantes de prompt
* múltiples ejecuciones por pasillo
* navegación de resultados por ejecución
* un único resultado operativo/canónico por pasillo
* benchmarking persistente, trazable y no intrusivo para la operación diaria

El objetivo principal no es solo integrar nuevos proveedores, sino **aislar resultados por ejecución** y **desacoplar la capa de análisis del vendor específico**, para que el sistema pueda crecer sin colisiones de datos ni hardcodes semánticos. 

---

## 2. Arquitectura target

## 2.1 Terminología estándar

### Job

Registro en `inventory_jobs` que representa una ejecución orquestada del pipeline.

### Execution Variant

Configuración concreta del job:

* `provider_name`
* `model_name`
* `prompt_key`
* `engine_params_json`

### Run Result

Conjunto de resultados persistidos producidos por un job exitoso:

* `positions`
* `product_records`
* `evidences`
* `raw_labels`
* `normalized_labels`
* `final_count_records`

Todos deben quedar asociados directa o indirectamente al `job_id`.

### Operational Job

Job promovido como resultado operativo/canónico del aisle. Vive en `aisles.operational_job_id`.

### Benchmark Job

Job exitoso persistido y trazable que no es operativo. Visible para comparación, pero fuera del flujo operativo por defecto.

---

## 2.2 Principios arquitectónicos

### A. Un aisle puede tener múltiples jobs exitosos

Cada ejecución persiste sus resultados sin pisar otros runs del mismo pasillo.

### B. Solo un job operativo por aisle

El aisle tiene un único `operational_job_id` a la vez.

### C. Benchmarking persistente

Los benchmark runs no son transitorios por definición. Se almacenan y pueden compararse luego.

### D. La operación usa el job operativo

Review, export operativo y analytics operativos usan:

* `operational_job_id`
* o fallback legacy `job_id IS NULL`

### E. Compatibilidad legacy explícita

Los datos históricos previos al nuevo modelo siguen siendo legibles como legacy operational data.

### F. El provider-specific code no vive en el core

La lógica compartida del pipeline no debe quedar embebida en implementaciones tipo `GeminiProvider`.

---

## 2.3 Capas arquitectónicas

La arquitectura propuesta no debe describirse solo como “multi-provider”, sino como una composición de capas:

### 1. Use Cases / Orchestration Layer

Responsable de:

* crear jobs
* resolver execution variants
* disparar el pipeline
* persistir resultados
* listar jobs
* promover `operational_job_id`
* ejecutar exports y merge dentro del contexto correcto

Ejemplos:

* `StartAisleProcessingUseCase`
* `PersistAisleResultUseCase`
* `RunAisleMergeUseCase`
* `ExportInventoryResultsUseCase`

### 2. Result Context Resolver

Responsable de resolver qué dataset debe leerse:

* `job_id` explícito
* `operational_job_id`
* fallback legacy `job_id IS NULL`

Esta pieza **no es ni Strategy ni Adapter**. Es una capa de aplicación/dominio clave para evitar bugs de contexto.

Ejemplo conceptual:

* `AisleResultContextResolver`
* o `RunSelectionResolver`

### 3. Provider Strategy Layer

Define cómo se ejecuta el análisis según proveedor/modelo.

Contrato común:

* `LLMProvider`
* o `AnalysisProvider`

Implementaciones:

* `GeminiProvider`
* `OpenAIProvider`
* `DeepSeekProvider`

Esta es la parte **Strategy**.

### 4. Provider Adapter Layer

Responsable de hablar con la API/SDK real del vendor.

Ejemplos:

* `GeminiSdkAdapter`
* `OpenAIResponsesAdapter`
* `DeepSeekApiAdapter`

Esta es la parte **Adapter**.

### 5. Mapper / Translator Layer

Responsable de traducir:

* requests internos → payload externo
* responses externos → resultado interno canónico

Ejemplos:

* `AnalysisRequestMapper`
* `AnalysisResponseMapper`
* `HybridReportToDomainMapper`

### 6. Shared Analysis Services

Responsable de lógica transversal reusable:

* prompt assembly común
* visual reference enrichment
* structured output validation
* metadata común del run
* normalización de campos comunes
* reglas comunes de tracing/logging

Esta lógica no debe quedar dentro de un provider vendor-specific salvo que sea estrictamente necesaria.

### 7. Persistence Layer

Responsable de:

* guardar jobs
* guardar run results job-scoped
* resolver lecturas aisladas por `aisle_id + job_id`
* sostener fallback legacy

---

## 2.4 Cómo aplica Strategy + Adapter

### Strategy

Se usa para seleccionar el comportamiento del análisis según `Execution Variant`.

Ejemplo:

* `ProviderRegistry` recibe `provider_name`
* devuelve una implementación de `LLMProvider`
* el pipeline usa ese contrato común

### Adapter

Se usa para encapsular el SDK/API externa de cada proveedor.

Ejemplo:

* `GeminiProvider` puede delegar en `GeminiSdkAdapter`
* `OpenAIProvider` puede delegar en `OpenAIResponsesAdapter`

### Regla

El pipeline y los use cases no deben conocer:

* shape específico del request del vendor
* shape específico del response del vendor
* nombres de campos internos del SDK
* reglas de retry específicas del SDK

Eso debe quedar encapsulado por Adapter + Mapper.

---

## 2.5 Modelo de metadatos del job

`inventory_jobs` debe almacenar:

### Columnas explícitas indexables

* `provider_name`
* `model_name`
* `prompt_key`

Se usan para:

* filtros
* listados
* selector de runs
* export
* trazabilidad visible
* compare UX futuro

### JSON extendido

* `engine_params_json`

Guarda:

* temperature
* max tokens
* retry policy
* structured output flags
* provider-specific knobs
* capability toggles

Regla:
**la identidad principal del run no puede depender de parsear `engine_params_json`**.

### 2.5.1 Identidad de ejecución vs afinado vs trazabilidad

| Ámbito | Qué incluye | Ejemplos |
|--------|-------------|----------|
| **Identidad de ejecución** | Qué variante corrió (comparable en listados y benchmarks) | `provider_name`, `model_name`, `prompt_key`, (recomendado) `prompt_version`, `job_id` |
| **Afinado (tuning)** | Parámetros que cambian comportamiento pero no deben ser la única base de identidad | `engine_params_json`: temperatura, max tokens, retries, flags |
| **Trazabilidad** | Reproducibilidad y auditoría en el tiempo | timestamps, estado del job, **snapshot del prompt renderizado** (opcional/recomendado), logs estructurados |

**`prompt_key` y evolución de plantillas:** si solo existe `prompt_key` y el contenido de la plantilla cambia sin cambiar la clave, los runs históricos dejan de ser comparables en sentido estricto. **Decisión explícita requerida antes de implementar benchmarking amplio en producción:** adoptar al menos una de:

* **`prompt_version`** (monotónica o semver) ligada al job, y/o  
* **snapshot del prompt ya renderizado** persistido en el job (o tabla satélite),  
* o **ambas** (máxima defensibilidad).

**Estabilidad:** la identidad lógica del prompt debe permanecer estable ante ediciones posteriores de templates en código; las versiones o el snapshot capturan el texto efectivo ejecutado.

**`engine_params_json`:** no es identidad primaria; **no debe ser la única fuente de verdad** para comparar runs ni para analytics operativos.

---

## 3. Cambios de dominio

## 3.1 inventory_jobs

### Rol target

Dueño de lifecycle + identidad de variante.

### Cambios

Agregar:

* `provider_name`
* `model_name`
* `prompt_key`
* `engine_params_json`
* (recomendado antes de benchmarking amplio en prod) **`prompt_version`** y/o columna/blob de **snapshot del prompt renderizado** — ver §2.5.1

Reglas:

* un `job_id` pertenece a un único `aisle_id`
* solo jobs exitosos pueden ser candidatos a `operational_job_id`

---

## 3.2 aisles

### Rol target

Selector del resultado operativo.

### Cambios

Agregar:

* `operational_job_id` nullable FK a `inventory_jobs`

Reglas:

* puede ser `NULL` en legacy
* cuando no es `NULL`, debe apuntar a un job exitoso del mismo aisle
* no puede apuntar a jobs fallidos ni de otro aisle

---

## 3.3 positions

### Rol target

Resultado principal job-scoped.

### Cambios

Agregar:

* `job_id` nullable FK a `inventory_jobs`

Reglas:

* nuevos resultados siempre con `job_id`
* legacy conserva `job_id = NULL`
* listados aíslan por `aisle_id + job_id`
* `position_id` globalmente único no cambia

### 3.3.1 Aislamiento físico vs identidad lógica (reglas semánticas)

* **`position_id`:** sigue siendo **único globalmente** (p. ej. UUID).
* **`job_id`:** garantiza **aislamiento de filas** entre runs: dos jobs ⇒ dos conjuntos de filas, sin sobrescritura.
* **`position_code` (u otra clave de negocio):** **puede repetirse entre jobs** del mismo pasillo si el detector emite el mismo código en otro run. Eso es **ambigüedad semántica entre runs**, no colisión de almacenamiento.
* El aislamiento por job **no** deduplica automáticamente “el mismo lugar lógico” entre ejecuciones.

**Decisión abierta explícita (no implícita):**

* Valorar índice **`(aisle_id, job_id)`** para consultas de listado/filtrado.
* **Unicidad opcional** en **`(aisle_id, job_id, position_code)`** solo si el pipeline de detección **garantiza** unicidad dentro de un run. Si **no** puede garantizarla, **no** forzar constraint UNIQUE; documentar que pueden existir múltiples filas con el mismo código dentro de un job.

---

## 3.4 product_records

### Rol target

Detalle job-scoped indirectamente vía `position_id`.

### Cambios

No requiere `job_id` directo en MVP.

Regla:

* toda lectura job-scoped debe resolverse a través de `positions`

---

## 3.5 evidences

### Rol target

Evidencia job-scoped indirectamente vía `position_id`.

### Cambios

No requiere `job_id` directo en MVP.

### Regla crítica (no opcional)

Con multi-run activo, **evidencias, crops, previews y endpoints de imagen/source asset** deben **nunca** resolver datos usando heurísticas de **“último job”** o “job más reciente” del pasillo. Aunque `evidences` siga ligada solo a `position_id` en MVP, **todo read path** debe:

1. Resolver primero el **contexto de resultado** ( `job_id` explícito → `operational_job_id` → legacy `job_id IS NULL` ).
2. Operar solo sobre el **conjunto de `position_id`** de ese contexto.

Cualquier helper a nivel pasillo que asuma un único run implícito debe **refactorizarse o prohibirse**. La filtración incorrecta aquí produce **fugas benchmark↔operativo** y previews incorrectos.

---

## 3.6 review_actions

### Rol target

Historial auditable sobre posiciones del job operativo.

### Cambios

No requiere `job_id` directo en MVP.

Reglas:

* benchmark jobs son read-only
* solo el `operational_job_id` es editable
* review history debe filtrarse por el contexto correcto
* no hay transferencia automática de correcciones en MVP

### MVP — por qué no hace falta `job_id` en `review_actions`

Las correcciones siguen atadas a **`position_id`**. El dataset editable queda acotado porque solo las posiciones del **job operativo** admiten escritura; las posiciones benchmark son solo lectura. **No** se requiere ampliar el esquema de `review_actions` con `job_id` para el rollout MVP. La UI/API filtra el historial según el **contexto de resultado** seleccionado para no mezclar vistas entre runs.

**Transferencia / mapeo de correcciones** entre runs: posible **fase futura**, **no** prerequisito del multi-provider MVP.

---

## 3.7 raw_labels

### Rol target

Entrada de merge job-scoped.

### Cambios

Agregar:

* `job_id` nullable FK a `inventory_jobs`

Regla:

* nunca mezclar labels de distintos jobs

---

## 3.8 normalized_labels

### Rol target

Salida intermedia job-scoped.

### Cambios

Agregar:

* `job_id` nullable FK a `inventory_jobs`

---

## 3.9 final_count_records

### Rol target

Consolidado job-scoped.

### Cambios

Agregar:

* `job_id` nullable FK a `inventory_jobs`

---

## 4. Plan de persistencia y compatibilidad legacy

## 4.1 Política general

No asumir que los datos históricos pueden mapearse confiablemente al `latest_job_id`.

Por lo tanto:

* legacy permanece con `job_id = NULL`
* `aisles.operational_job_id` inicializa en `NULL`
* nuevos runs se persisten con `job_id` real
* el sistema sostiene fallback explícito a legacy

---

## 4.2 Legacy rules

### Legacy reads

Cuando:

* `operational_job_id IS NULL`
* y no se especifica `job_id`

la lectura usa:

* `positions.job_id IS NULL`
* `raw_labels.job_id IS NULL`
* `normalized_labels.job_id IS NULL`
* `final_count_records.job_id IS NULL`

### Legacy export

Si el aisle es legacy y no tiene `operational_job_id`, el export usa filas con `job_id IS NULL`.

### Legacy review history

Sigue asociada a posiciones legacy.

### Legacy promotion

Cuando se corre por primera vez el nuevo pipeline en un aisle legacy:

* se crea un nuevo job real
* el resultado aparece como benchmark
* solo al promoverlo, `operational_job_id` deja de ser `NULL`

---

## 4.3 Backfill

### MVP

No hacer backfill agresivo.

### Motivo

No hay garantía de trazabilidad histórica consistente entre:

* positions
* labels
* evidences
* artifacts
* latest job histórico

### Política

* columnas nuevas nullable
* legacy permanece en `NULL`
* solo nuevos runs reciben `job_id`

---

## 4.4 Guardrails estructurales

* `operational_job_id` solo puede referenciar jobs exitosos del mismo aisle
* las lecturas job-scoped aíslan por `aisle_id` y `job_id`
* `position_id` globalmente único no debe romperse
* nuevos índices deben soportar:

  * `aisle_id + job_id`
  * fallback legacy `job_id IS NULL`
* ningún nuevo run debe borrar o reescribir implícitamente filas legacy

---

## 5. Evolución de API

## 5.1 Reglas generales de resolución

### Caso A: `job_id` explícito

La API:

1. valida que exista
2. valida que pertenezca al aisle
3. lo usa como contexto de lectura

### Caso B: `job_id` omitido y hay `operational_job_id`

Se usa el job operativo.

### Caso C: `job_id` omitido y `operational_job_id IS NULL`

Se usa fallback legacy.

### Caso D: `job_id` inválido

Retorna error estable.

### Caso E: `job_id` de otro aisle

Retorna error de pertenencia/contexto inválido.

Estas reglas deben centralizarse en un **Result Context Resolver**, no repetirse artesanalmente en cada endpoint.

---

## 5.2 POST /process

### Target

Acepta `ProcessConfig`:

* `provider_name`
* `model_name`
* `prompt_key`
* `engine_params_json` opcional

### Regla MVP

Un request crea un job.

`run all` queda fuera de MVP como orquestación superior.

### Nota futura: orquestación “run all” / batch benchmarking (no MVP)

Cuando se priorice, un diseño razonable incluye:

* entidad padre tipo **benchmark session** / **benchmark batch** que agrupe **N** jobs creados en una misma acción;
* metadatos compartidos (inventario, subconjunto de pasillos, matriz provider/model/prompt);
* UI con **agrupación** (progreso por job hijo);
* controles de **concurrencia y coste** (límites, cancelación, colas).

Esto es **extensión futura**; el MVP no la implementa.

---

## 5.3 GET /aisles/{id}/status

Debe devolver:

* estado operativo actual
* `operational_job_id`
* `recent_jobs[]`
* metadata mínima:

  * `job_id`
  * `status`
  * `provider_name`
  * `model_name`
  * `prompt_key`
  * timestamps

---

## 5.4 GET /aisles/{id}/jobs

Lista historial relevante del aisle.

Uso:

* selector de variantes
* benchmark browsing
* promotion flow futuro

---

## 5.5 GET /aisles/{id}/positions

Job-aware.

Regla:

* usa `job_id` explícito si viene
* si no, resuelve operativo o legacy

Nunca mezcla múltiples jobs.

---

## 5.6 GET /positions/{position_id}

Debe seguir funcionando por `position_id`, pero incluir:

* `job_id`
* metadata mínima de variante
* contexto suficiente para que frontend no mezcle datasets

---

## 5.7 POST /aisles/{id}/merge

Debe ser job-scoped obligatorio.

Requiere `job_id`.

No debe existir merge ambiguo aisle-wide.

---

## 5.8 GET /aisles/{id}/merge-results

Job-aware, con la misma resolución:

* explícito
* operativo
* legacy

---

## 5.9 GET /inventories/{id}/export

### Export operativo

Default:

* `operational_job_id`
* o legacy `job_id IS NULL`

### Export por job

Acepta `job_id` e incluye:

* `llm_provider`
* `llm_model`
* `prompt_key`
* `run_timestamp`

MVP: no requiere export comparativo pivotado.

---

## 5.10 Evidence / source asset endpoints

Cuando el asset dependa del run correcto:

* deben aceptar contexto suficiente
* no deben asumir latest job global del aisle

Esto es crítico para previews, crops y source image display.

---

## 5.11 Analytics

### Regla principal (precisa)

**Por defecto**, los analytics operativos incluyen **solo**:

1. Para cada pasillo con **`operational_job_id` no nulo**: filas cuyo **`job_id`** coincide con ese **`operational_job_id`**.
2. Para cada pasillo **legacy** (`operational_job_id IS NULL`): filas con **`job_id IS NULL`**.

**Inventarios mixtos:** un inventario puede tener pasillos ya promovidos y pasillos aún legacy. La regla se aplica **por pasillo** (o equivalente en el modelo de agregación), no con un único filtro global que rompa un caso u otro.

**Exclusión de benchmark:** los jobs no operativos deben quedar fuera del **default operativo** idealmente en la **capa de repositorio / composición SQL compartida**, no solo con filtros ad-hoc en un endpoint suelto (para evitar fugas en nuevos endpoints).

### Benchmark analytics

**Fuera del alcance MVP.** No es requisito producto del primer rollout.

---

## 6. Plan frontend

## 6.1 Objetivo MVP

Permitir navegar resultados por job aislado, primero con el proveedor actual.

---

## 6.2 Estado y routing

* incorporar `job_id` en URL cuando aplique
* query keys pasan a incluir job context
* hooks consumen:

  * `job_id` explícito
  * o fallback operativo/legacy resuelto por backend

---

## 6.3 Variant selector

Agregar selector de run en la vista de resultados del aisle.

Debe permitir:

* ver job operativo
* ver benchmark jobs
* ver legacy si no hay operativo

---

## 6.4 KPIs

Los KPIs se recalculan sobre el dataset visualizado.

Nunca sobre mezcla de jobs.

---

## 6.5 Processing UX

### Fase inicial

Puede mantenerse una acción simple con provider actual fijo.

### Fase posterior

Modal “Start Run” con:

* provider
* model
* prompt
* parámetros opcionales

---

## 6.6 Review drawer

Debe respetar:

* editable solo para el job operativo
* read-only para benchmark
* read-only para datasets no promovidos

---

## 7. Modelo de review

## 7.1 MVP

Solo el `operational_job_id` es editable.

## 7.2 Benchmark jobs

* visibles
* comparables
* read-only

## 7.3 Promoción

Promover un benchmark job actualiza:

* `aisles.operational_job_id`

No se transfieren correcciones automáticamente en MVP.

## 7.4 Transferencia futura

Queda fuera de MVP.
Podrá resolverse luego mediante una estrategia explícita y auditable.

---

## 8. Arquitectura de proveedores

## 8.1 Contrato común

Definir un contrato como:

* `LLMProvider`
  o
* `AnalysisProvider`

Debe exponer una operación estable tipo:

* `analyze(request: AnalysisRequest) -> AnalysisResult`

El contrato no debe exponer detalles de SDK vendor-specific.

---

## 8.2 Strategy layer

Implementaciones concretas:

* `GeminiProvider`
* `OpenAIProvider`
* `DeepSeekProvider`

Responsabilidad:

* ejecutar el análisis según el proveedor elegido
* delegar la llamada externa a su adapter
* devolver un resultado interno normalizado

---

## 8.3 Adapter layer

Cada provider debe usar un adapter de vendor:

* `GeminiSdkAdapter`
* `OpenAIResponsesAdapter`
* `DeepSeekApiAdapter`

Responsabilidades:

* armar request externo
* ejecutar llamada externa
* parsear error model del vendor
* encapsular detalles del SDK/API

---

## 8.4 Mapper layer

Separar mappers:

* request mapper interno → externo
* response mapper externo → interno
* mapper de resultado híbrido → dominio persistible

Esto evita meter parsing y normalización dentro del provider strategy.

---

## 8.5 Shared analysis services

Extraer lógica común fuera del provider:

* prompt rendering compartido
* visual references enrichment
* metadata/tracing común
* validación de structured outputs
* logging no vendor-specific

---

## 8.6 Provider registry

Agregar un `ProviderRegistry` que:

* registre strategies disponibles
* resuelva provider por `provider_name`
* falle de forma explícita si el provider no existe

---

## 8.7 Regla de diseño

El core del pipeline no debe depender de:

* `Gemini*`
* `OpenAI*`
* nombres específicos de SDK
* shapes externos del vendor

Debe depender de:

* contrato común
* adapters
* mappers
* services compartidos

### 8.7.1 Anti‑patrón: “interface delgada” sobre Gemini

**No basta** con envolver la implementación actual detrás de `LLMProvider` si la lógica compartida sigue dentro de código vendor-specific. En la fase Strategy + Adapter se debe **extraer explícitamente** a servicios/compartidos:

* ensamblado y **render de prompts**
* **enriquecimiento** de referencias visuales
* **validación** de structured output
* **tracing/logging** compartido (independiente de retries del SDK)
* **normalización canónica** de la respuesta hacia el modelo interno

El núcleo del pipeline debe depender **solo de contratos internos estables**, no de formas de request/response del proveedor.

---

## 9. CSV / Export

## 9.1 MVP

### Operational export

Usa:

* `operational_job_id`
* o legacy `job_id IS NULL`

### Job export

Usa un `job_id` puntual y agrega:

* `llm_provider`
* `llm_model`
* `prompt_key`
* `run_timestamp`

## 9.2 Posterior

Comparative export pivotado queda para otra fase.

---

## 10. Fases de rollout

## Fase 1 — Persistence isolation + legacy compatibility

### Scope

* columnas nullable
* nuevos runs con `job_id`
* fallback legacy
* aislamiento por job en repositorios

### Éxito

Dos runs del proveedor actual en el mismo aisle sin colisión.

---

## Fase 2 — API job-scoped reads + Result Context Resolver

### Scope

* `GET /positions` job-aware
* `GET /status` con recent jobs
* `GET /aisles/{id}/jobs`
* `GET /positions/{id}` con contexto
* merge/export/evidence con contexto correcto
* introducir `AisleResultContextResolver`

### Éxito

Todas las lecturas usan un resolver unificado y no hay mezcla de datasets.

---

## Fase 3 — Frontend browsing con provider actual

### Scope

* selector de run
* query keys job-aware
* KPIs por dataset
* review drawer contextual

### Éxito

El operador alterna entre Run 1 y Run 2 del mismo proveedor.

---

## Fase 4 — Provider abstraction cleanup (Strategy + Adapter)

### Scope

* `LLMProvider`
* `ProviderRegistry`
* adapters vendor-specific
* mappers
* extracción de lógica común fuera de Gemini
* limpieza de hardcodes Gemini

### Éxito

El pipeline deja de depender conceptualmente de Gemini y usa contratos estables.

---

## Fase 5 — Nuevo proveedor + Start Run configurable

### Scope

* integrar OpenAI u otro provider
* `POST /process` configurable
* UI de start run configurable

### Éxito

El usuario puede lanzar jobs con más de un provider/model/prompt.

---

## Fase 6 — Benchmark UX y refinamientos

### Scope

* compare UX más rica
* exports refinados
* benchmark analytics opcionales
* promotion workflows futuros

---

## 11. Estrategia de testing

## 11.1 Repository tests

* aislamiento por `aisle_id + job_id`
* fallback legacy
* no mezcla entre jobs
* **analytics / agregados:** default operativo excluye benchmark; inventario **mixto** legacy + operativo

## 11.2 Migration tests

* columnas nullable
* lecturas legacy no rotas
* constraints sobre `operational_job_id`

## 11.3 API tests

* `POST /process` con config
* `GET /positions` en todos los modos
* `POST /merge` requiere `job_id`
* export operativo y por job
* validación de `job_id` ajeno al aisle
* **evidence / preview / crop / imagen:** correctos **por job seleccionado**; **ningún** endpoint nuevo con “latest job” implícito

## 11.4 Integration tests

* doble run mismo aisle sin colisión
* cambio de `operational_job_id`
* benchmark no altera legacy ni operativo previo
* **export operativo:** sin filas duplicadas tras varios benchmark runs en el mismo pasillo
* **KPIs operativos:** no inflan al añadir jobs benchmark

## 11.5 Frontend tests

* query keys con job
* selector actualiza tabla sin mezcla
* review drawer editable/read-only según contexto

## 11.6 Provider tests

* cada strategy cumple el contrato común
* cada adapter encapsula correctamente errores y request shaping
* mappers normalizan responses a shape interno estable
* **tests de contrato** que el core no importe tipos/SDK del vendor

## 11.7 Legacy compatibility tests

* aisle sin `operational_job_id`
* export legacy
* review history legacy
* analytics operativos sobre `job_id IS NULL`

## 11.8 Regresión “sin latest job implícito”

* revisión estática o pruebas de integración que fallen si un read path de evidencia/posición usa “último job del pasillo” sin pasar por el Result Context Resolver

---

## 12. Riesgos y decisiones abiertas

### Riesgo 1 (crítico)

Resolvers de evidence/assets siguen usando latest job y muestran previews equivocados. **Tratamiento:** regla arquitectónica obligatoria + ítems DoD/tests en `multi_provider_planning_revision.md`.

### Riesgo 2

Merge o consolidación mezcla labels de distintos jobs si alguna capa queda aisle-scoped.

### Riesgo 3

Analytics se contamina si algún endpoint sigue leyendo benchmark jobs por defecto. **Tratamiento:** filtros en repositorio/query compartida, tests de no inflación KPI.

### Riesgo 4

Provider abstraction incompleta deja lógica compartida atrapada en `GeminiProvider`. **Tratamiento:** §8.7.1 y extracción explícita de servicios compartidos.

### Decisión abierta 1

**Unicidad `(aisle_id, job_id, position_code)`:** depende de garantías del detector; puede quedar **sin** UNIQUE. Debe documentarse, no asumirse.

### Decisión abierta 2

**`prompt_version` vs snapshot renderizado vs ambos:** elegir antes de benchmarking amplio en prod (ver §2.5.1).

### Decisión abierta 3

Cuándo agregar parent-job para `run all`. No es necesario en MVP (nota futura en §5.2).

### Decisión abierta 4

Cuándo agregar compare UX avanzada. No es necesario en MVP.

### Decisión abierta 5

Cuándo agregar transfer semiautomático de correcciones. Fuera de MVP.

### Diferido explícitamente (lista maestra)

Ver **`docs/multi_provider_planning_revision.md` §8** (benchmark analytics, transfer de correcciones, `job_id` en `review_actions`, run-all, backfill agresivo, etc.).

---

## 13. Definition of Done de ingeniería

Se considera completado el rollout inicial cuando:

### Persistencia

* todo nuevo `Position`, `RawLabel`, `NormalizedLabel`, `FinalCountRecord` tiene `job_id`
* `product_records`, `evidences`, `review_actions` quedan correctamente job-scoped vía `position_id` **y** los reads resuelven **primero** el contexto de resultado
* legacy `job_id IS NULL` sigue legible
* metadatos de job: columnas indexables `provider_name`, `model_name`, `prompt_key`; **`engine_params_json` no es identidad primaria**; **trazabilidad de prompt** (`prompt_version` y/o snapshot renderizado) implementada **o** riesgo aceptado por escrito (preferible implementar al menos una vía)

### API

* listados y detalles se resuelven por job sin mezclar datasets
* `GET /positions`, export y merge respetan contexto explícito / operativo / legacy
* **evidence/assets/previews:** ningún path depende de “latest job” implícito del pasillo

### Analytics

* default operativo: **solo** job operativo por pasillo + legacy `NULL` donde aplique; **benchmark excluido** en capa de consulta compartida; inventarios mixtos correctos
* **benchmark analytics:** fuera de MVP (no requisito)

### Frontend

* la pantalla de resultados alterna entre múltiples runs del mismo aisle
* los KPIs reflejan solo el dataset seleccionado / reglas operativas por defecto
* benchmark jobs son read-only
* operational job es editable

### Provider architecture

* existe contrato común `LLMProvider`
* existe `ProviderRegistry`
* cada provider usa su adapter
* la lógica compartida **extraída** (prompts, enrichment, validación, logging, normalización) no vive en una implementación vendor-specific
* el pipeline core no contiene hardcodes Gemini en flows genéricos

### Review

* **`review_actions` sin `job_id` en MVP** es diseño aceptado; permisos operativos vía job operativo + read-only benchmark

### Compatibilidad

* ningún dato legacy se borra o reescribe implícitamente
* aisles legacy siguen funcionando sin promoción obligatoria

### Testing

* pasan tests de aislamiento, fallback legacy, provider contract, export y doble-run
* se prueba explícitamente que dos runs del mismo aisle no colisionan
* tests de evidence/preview por job, analytics mixtos, exclusión benchmark en KPIs, export sin duplicados post-benchmark
* lista completa: **`multi_provider_planning_revision.md` §7**

---

## 14. Primer slice recomendado

### “Traceable Multi-Run with Current Provider”

Implementar primero:

1. `job_id` nullable en tablas principales
2. persistencia de nuevos runs con `job_id`
3. resolver de contexto para lecturas job-aware + fallback legacy
4. selector básico de run en frontend
5. doble procesamiento del mismo aisle con el proveedor actual
6. validación end-to-end de no colisión

### Éxito del slice

Se considera exitoso cuando:

* un aisle puede procesarse dos veces con el proveedor actual
* ambos resultados quedan persistidos sin mezcla
* la UI alterna entre ambos
* el dataset legacy previo sigue intacto
* el job operativo o fallback legacy siguen siendo la base de la operación