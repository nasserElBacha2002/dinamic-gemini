
# Multi-Provider Implementation Plan (Final, Strategy + Adapter)

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

Regla:

* la resolución de crops/assets/source images debe respetar el job correcto del contexto seleccionado

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

### Regla principal

Operational analytics por defecto.

Eso significa:

* benchmark jobs excluidos por default
* legacy aisles usan `job_id IS NULL` hasta promoción

### Benchmark analytics

Puede agregarse después, pero fuera del flujo principal.

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

## 11.4 Integration tests

* doble run mismo aisle sin colisión
* cambio de `operational_job_id`
* benchmark no altera legacy ni operativo previo

## 11.5 Frontend tests

* query keys con job
* selector actualiza tabla sin mezcla
* review drawer editable/read-only según contexto

## 11.6 Provider tests

* cada strategy cumple el contrato común
* cada adapter encapsula correctamente errores y request shaping
* mappers normalizan responses a shape interno estable

## 11.7 Legacy compatibility tests

* aisle sin `operational_job_id`
* export legacy
* review history legacy
* analytics operativos sobre `job_id IS NULL`

---

## 12. Riesgos y decisiones abiertas

### Riesgo 1

Resolvers de evidence/assets siguen usando latest job y muestran previews equivocados.

### Riesgo 2

Merge o consolidación mezcla labels de distintos jobs si alguna capa queda aisle-scoped.

### Riesgo 3

Analytics se contamina si algún endpoint sigue leyendo benchmark jobs por defecto.

### Riesgo 4

Provider abstraction incompleta deja lógica compartida atrapada en `GeminiProvider`.

### Decisión abierta 1

Cuándo agregar parent-job para `run all`. No es necesario en MVP.

### Decisión abierta 2

Cuándo agregar compare UX avanzada. No es necesario en MVP.

### Decisión abierta 3

Cuándo agregar transfer semiautomático de correcciones. Fuera de MVP.

---

## 13. Definition of Done de ingeniería

Se considera completado el rollout inicial cuando:

### Persistencia

* todo nuevo `Position`, `RawLabel`, `NormalizedLabel`, `FinalCountRecord` tiene `job_id`
* `product_records`, `evidences`, `review_actions` quedan correctamente job-scoped vía `position_id`
* legacy `job_id IS NULL` sigue legible

### API

* listados y detalles se resuelven por job sin mezclar datasets
* `GET /positions`, export y merge respetan contexto explícito / operativo / legacy
* evidence/assets no dependen de latest job incorrecto

### Frontend

* la pantalla de resultados alterna entre múltiples runs del mismo aisle
* los KPIs reflejan solo el dataset seleccionado
* benchmark jobs son read-only
* operational job es editable

### Provider architecture

* existe contrato común `LLMProvider`
* existe `ProviderRegistry`
* cada provider usa su adapter
* la lógica compartida no vive en una implementación vendor-specific
* el pipeline core no contiene hardcodes Gemini en flows genéricos

### Compatibilidad

* ningún dato legacy se borra o reescribe implícitamente
* aisles legacy siguen funcionando sin promoción obligatoria

### Testing

* pasan tests de aislamiento, fallback legacy, provider contract, export y doble-run
* se prueba explícitamente que dos runs del mismo aisle no colisionan

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