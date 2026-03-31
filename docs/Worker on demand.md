# **Plan de implementación — Worker on-demand \+ observabilidad \+ control de jobs**

## **Etapa 1 — Rediseño del ciclo de vida del job**

### **Objetivo**

Definir un lifecycle más fino para que el sistema pueda saber exactamente en qué estado real está cada ejecución y no dependa de un `running` demasiado genérico.

### **Alcance**

Agregar o consolidar estados y metadata operativa del job.

### **Cambios**

Estados recomendados:

* `queued`  
* `starting`  
* `running`  
* `cancel_requested`  
* `canceled`  
* `failed`  
* `succeeded`

Campos operativos recomendados:

* `started_at`  
* `finished_at`  
* `last_heartbeat_at`  
* `cancel_requested_at`  
* `current_stage`  
* `current_substep`  
* `current_step_started_at`  
* `attempt_count`  
* `failure_code`  
* `failure_message`  
* `execution_id` o identificador lógico de la corrida

### **Resultado esperado**

Cada job podrá mostrar:

* si solo fue encolado,  
* si realmente arrancó,  
* en qué etapa está,  
* si está cancelándose,  
* por qué falló,  
* y si quedó colgado.

### **Definition of Done**

* El backend expone los nuevos estados.  
* El modelo de job persiste `current_stage/current_substep`.  
* Ya no se usa `running` como único estado operativo amplio.

---

## **Etapa 2 — Pasar el worker a on-demand**

### **Objetivo**

Eliminar el worker always-on y reemplazarlo por ejecución efímera por job.

### **Alcance**

Cuando el usuario aprieta `process`, el backend crea el job y dispara una corrida puntual del worker.

### **Diseño recomendado**

* Misma imagen para backend y worker.  
* Distinto comando de entrada.  
* Un proceso o contenedor efímero por `job_id`.  
* Sin cola permanente en esta etapa.  
* Concurrencia inicial: **1 job a la vez**.

### **Flujo esperado**

1. Usuario presiona `process`.  
2. Backend valida precondiciones.  
3. Backend crea job en `queued`.  
4. Backend dispara worker on-demand.  
5. Si el spawn funciona, job pasa a `starting`.  
6. Cuando el worker confirma arranque real, pasa a `running`.  
7. Al finalizar, actualiza a `succeeded`, `failed` o `canceled`.

### **Cambios técnicos**

* Remover worker persistente del despliegue base.  
* Crear `WorkerLaunchService` o equivalente.  
* Encapsular el comando de ejecución efímera.  
* Agregar lock simple para evitar múltiples jobs simultáneos.  
* Si falla el spawn, marcar el job como `failed`.

### **Definition of Done**

* El worker ya no corre 24/7.  
* Cada job dispara una ejecución efímera.  
* Si el worker no arranca, el job no queda en `running`.

---

## **Etapa 3 — Logs estructurados y trazabilidad fina**

### **Objetivo**

Tener visibilidad real de qué pasa dentro del worker y poder detectar exactamente dónde se frena.

### **Alcance**

Agregar logging estructurado por job, stage y substep.

### **Diseño recomendado**

Cada evento de log debería incluir:

* `job_id`  
* `inventory_id`  
* `aisle_id`  
* `attempt`  
* `stage`  
* `substep`  
* `event`  
* `ts`  
* `duration_ms`  
* `details`

### **Tipos de evento**

* `job.started`  
* `job.spawn_requested`  
* `job.spawn_succeeded`  
* `job.spawn_failed`  
* `stage.started`  
* `substep.started`  
* `substep.completed`  
* `stage.completed`  
* `stage.failed`  
* `job.heartbeat`  
* `job.cancel_requested_detected`  
* `job.canceled`  
* `job.failed`  
* `job.succeeded`

### **Salida recomendada**

* Log resumido operacional.  
* Event log estructurado por job, idealmente en JSONL.

### **Definition of Done**

* Existe un log estructurado por job.  
* Cada stage emite `started/completed/failed`.  
* Cada substep relevante queda registrado con duración.

---

## **Etapa 4 — Instrumentación profunda de `FrameAcquisitionStage`**

### **Objetivo**

Investigar y aislar el punto exacto donde hoy se traba el procesamiento.

### **Contexto**

Por el log actual, el job:

* arranca,  
* completa `InputPreparationStage`,  
* y queda frenado al entrar a `FrameAcquisitionStage`.

Eso indica que el primer foco de investigación debe estar ahí, antes de Gemini.

### **Substeps a instrumentar**

* `manifest_load`  
* `photos_dir_scan`  
* `file_enumeration`  
* `file_validation`  
* `image_open`  
* `image_decode`  
* `image_normalization`  
* `frame_collection_completed`

### **Metadata por evento**

* filename  
* image\_id  
* file index  
* path  
* tamaño del archivo si aplica  
* duración

### **Resultado esperado**

Poder determinar si el bloqueo ocurre:

* al listar archivos,  
* al abrir una imagen,  
* al decodificar,  
* al normalizar,  
* o al consolidar los frames.

### **Definition of Done**

* `FrameAcquisitionStage` tiene logs internos finos.  
* Puede verse exactamente el último substep exitoso.  
* Si falla o se cuelga, queda identificado el archivo/recurso asociado.

---

## **Etapa 5 — Heartbeat y detección de jobs colgados**

### **Objetivo**

Evitar que un job quede indefinidamente en `running`.

### **Alcance**

Agregar heartbeat periódico y un mecanismo de reconciliación de jobs stale.

### **Diseño recomendado**

Mientras el worker está activo:

* actualiza `last_heartbeat_at` cada 10–15 segundos,  
* actualiza `current_stage/current_substep`.

### **Reglas iniciales sugeridas**

* `starting` sin heartbeat por más de 2 minutos → `failed`  
* `running` sin heartbeat por más de 3–5 minutos → `failed` con `STALE_JOB`  
* `cancel_requested` sin resolución por más de 1 minuto → cierre forzado

### **Resultado esperado**

Aunque el proceso se cuelgue o desaparezca, el job deja de quedar eternamente en `running`.

### **Definition of Done**

* Todos los jobs activos tienen heartbeat.  
* Existe reconciliación de stale jobs.  
* Un job colgado se cierra automáticamente con causa explícita.

---

## **Etapa 6 — Cancelación manual y cancelación automática**

### **Objetivo**

Poder interrumpir jobs manualmente y también cerrar automáticamente jobs que no responden.

### **Alcance**

Implementar cancelación cooperativa con fallback forzado.

### **Diseño recomendado**

Flujo de cancelación manual:

1. Usuario solicita cancelación.  
2. Backend marca `cancel_requested`.  
3. Worker chequea cancelación entre substeps.  
4. Si detecta cancelación:  
   * guarda logs,  
   * limpia recursos,  
   * marca `canceled`,  
   * termina.

Fallback:

* Si no responde a cancelación cooperativa, el runner o reconciliador fuerza la terminación.

### **Puntos donde chequear cancelación**

* al empezar cada stage,  
* al empezar cada substep,  
* antes y después de I/O pesado,  
* antes de persistencias largas,  
* dentro de loops largos por imagen/lote.

### **Definition of Done**

* Existe endpoint o acción de cancelación.  
* El worker puede salir limpiamente.  
* Si no responde, el sistema lo cierra y no deja `running` infinito.

---

## **Etapa 7 — Retry manual con trazabilidad**

### **Objetivo**

Permitir reintentar jobs fallidos o cancelados sin perder historial.

### **Alcance**

Implementar retry manual primero; el automático puede esperar.

### **Diseño recomendado**

* No “revivir” silenciosamente el mismo job.  
* Crear un nuevo intento vinculado al anterior.  
* Guardar:  
  * `retry_of_job_id`  
  * `attempt_count`  
  * `retry_reason`  
  * `retryable`

### **Resultado esperado**

El operador puede relanzar un procesamiento fallido, y el sistema conserva el historial completo de intentos.

### **Definition of Done**

* Un job `failed` o `canceled` puede reintentarse.  
* Queda visible la relación entre intento original y nuevo intento.  
* No se pierde el historial previo.

---

## **Etapa 8 — Endpoints y superficie API**

### **Objetivo**

Exponer el nuevo control operativo de jobs al frontend y a debugging interno.

### **Endpoints recomendados**

* `POST /process`  
* `POST /jobs/{job_id}/cancel`  
* `POST /jobs/{job_id}/retry`  
* `GET /jobs/{job_id}`  
* `GET /jobs/{job_id}/execution-log`

### **Campos mínimos en status/detail**

* estado  
* stage actual  
* substep actual  
* heartbeat  
* started\_at  
* finished\_at  
* failure\_code  
* failure\_message  
* cancel\_requested  
* attempt\_count

### **Definition of Done**

* El frontend puede consultar el estado fino del job.  
* Hay acceso a logs por job.  
* Existen acciones de cancelación y retry.

---

## **Etapa 9 — UI operativa mínima**

### **Objetivo**

Dar herramientas básicas para operar y depurar sin entrar al servidor.

### **Funcionalidades mínimas**

* ver estado del job,  
* ver stage/substep actual,  
* ver último heartbeat,  
* botón cancelar,  
* botón retry,  
* acceso al log estructurado.

### **Resultado esperado**

Si un job queda mal, el operador puede:

* ver dónde está,  
* cancelarlo,  
* entender por qué falló,  
* reintentarlo.

### **Definition of Done**

* La UI refleja el lifecycle nuevo.  
* Hay acciones de cancelación y retry.  
* Puede verse la trazabilidad básica del procesamiento.

---

# **Orden de ejecución recomendado**

## **Fase A**

* Etapa 1 — lifecycle del job  
* Etapa 2 — worker on-demand

## **Fase B**

* Etapa 3 — logs estructurados  
* Etapa 4 — instrumentación de `FrameAcquisitionStage`

## **Fase C**

* Etapa 5 — heartbeat y stale recovery  
* Etapa 6 — cancelación manual/automática

## **Fase D**

* Etapa 7 — retry manual  
* Etapa 8 — endpoints  
* Etapa 9 — UI mínima

---

# **Prioridad real sugerida**

Si querés arrancar ya, el mejor primer bloque sería este:

### **Bloque 1**

* lifecycle nuevo  
* worker on-demand  
* logs finos  
* `FrameAcquisitionStage` instrumentado

### **Bloque 2**

* heartbeat  
* stale detection  
* cancelación

### **Bloque 3**

* retry  
* mejoras UI/API

---

