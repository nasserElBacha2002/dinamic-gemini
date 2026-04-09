# Plan implementacion — Inventory processing mode (`production` vs `test`)

## 1. Objetivo

Introducir una separación explícita entre dos formas de operar inventarios dentro de Dinamic Inventory:

* **`production`**: flujo operativo real, simple, estable y por defecto
* **`test`**: flujo experimental para benchmark, comparación entre proveedores/modelos/prompts y validación de resultados

La meta es conservar todo el trabajo ya hecho para multiproveedor y comparación, pero encapsularlo únicamente dentro del modo `test`, dejando el modo `production` como experiencia principal del producto.

---

## 2. Alcance

Esta implementación debe cubrir:

* dominio
* persistencia
* contratos API
* casos de uso
* guards de negocio
* frontend
* migración/backfill
* testing
* observabilidad básica

No forma parte obligatoria de esta fase:

* rediseñar por completo la arquitectura de execution profiles
* construir paneles admin avanzados para elegir defaults operacionales
* rehacer analytics separadas por modo en profundidad

Eso puede quedar como evolución posterior.

---

## 3. Problema actual

Hoy el sistema evolucionó hacia una arquitectura donde el usuario puede:

* elegir distintos proveedores
* elegir distintos modelos
* correr múltiples configuraciones
* comparar runs
* exportar benchmark
* iterar entre ejecuciones

Eso sirve para etapa de validación, pero mezcla dos necesidades distintas:

1. **Operación real del producto**
2. **Experimentación / benchmark**

El resultado es que el flujo “normal” queda contaminado con complejidad experimental.

---

## 4. Resultado esperado

Con esta implementación:

* todo inventario nuevo se crea en `production` salvo que el usuario active manualmente `test`
* inventarios `production` usan una única configuración primaria
* inventarios `production` no exponen comparaciones, benchmark ni runs paralelos
* inventarios `test` mantienen el comportamiento multiproveedor actual
* el backend hace cumplir esta separación, no solo el frontend
* inventarios existentes no se rompen

---

## 5. Definición funcional

### 5.1 `production`

Modo operativo real.

Características:

* default al crear inventario
* una sola configuración efectiva
* sin selector multiproveedor
* sin selector multmodelo
* sin selector multiprompt
* sin compare runs
* sin benchmark exports
* sin promote operational job
* ejecución simple: un job principal

### 5.2 `test`

Modo experimental.

Características:

* opt-in
* múltiples proveedores/modelos/prompts
* múltiples jobs/runs por pasillo
* comparación entre resultados
* benchmark
* exportes comparativos
* mantenimiento del flujo actual multiproveedor

---

## 6. Principios de diseño

### 6.1 El modo es parte del dominio

No debe resolverse solo ocultando componentes.
Debe vivir en backend y gobernar reglas reales.

### 6.2 `production` es el flujo principal

Tiene que sentirse como el uso natural del sistema.

### 6.3 `test` encapsula toda la complejidad experimental

Todo lo comparativo debe quedar bajo ese modo.

### 6.4 El modo no debe cambiar libremente

Una vez que un inventario ya tiene procesamiento, cambiar de modo puede romper trazabilidad y semántica.

---

## 7. Diseño de dominio

## 7.1 Nuevo enum

Agregar nuevo enum en dominio:

```python
class InventoryProcessingMode(str, Enum):
    PRODUCTION = "production"
    TEST = "test"
```

## 7.2 Inventory

Agregar a la entidad `Inventory`:

```python
processing_mode: InventoryProcessingMode = InventoryProcessingMode.PRODUCTION
primary_provider_name: Optional[str] = None
primary_model_name: Optional[str] = None
primary_prompt_key: Optional[str] = None
primary_prompt_version: Optional[str] = None
```

## 7.3 Sentido de la configuración primaria

Estos campos representan el snapshot de la configuración operacional efectiva.

Reglas:

* en `production`, deben representar la configuración que usa el inventario para correr
* en `test`, pueden quedar nulos o actuar como referencia, pero no gobiernan compare/multirun

---

## 8. Persistencia

## 8.1 Migración SQL

Agregar columnas a `inventories`:

```sql
processing_mode VARCHAR(20) NOT NULL DEFAULT 'production',
primary_provider_name VARCHAR(100) NULL,
primary_model_name VARCHAR(150) NULL,
primary_prompt_key VARCHAR(150) NULL,
primary_prompt_version VARCHAR(50) NULL
```

## 8.2 Consideraciones

* `processing_mode` debe ser `NOT NULL`
* el default DB debe ser `production`
* los campos primarios pueden ser null inicialmente para soportar transición gradual

---

## 9. Estrategia de backfill

## 9.1 Recomendación

Para no romper inventarios existentes:

* todos los inventarios existentes se backfillean a `test`
* todos los inventarios nuevos nacen en `production`

Esto preserva el comportamiento histórico.

## 9.2 Motivo

Hoy los inventarios existentes fueron creados dentro del paradigma experimental.
Forzarlos a `production` puede romper:

* compare views
* benchmark exports
* runs múltiples
* UX actual de detalle

## 9.3 Evolución futura opcional

Más adelante se puede hacer una auditoría más fina y reclasificar algunos inventarios viejos a `production`, pero no debe bloquear esta fase.

---

## 10. Configuración operacional primaria

## 10.1 Fuente de verdad

Debe existir una configuración operacional default del sistema.

Ejemplo conceptual:

* provider: provider principal aprobado
* model: modelo principal aprobado
* prompt: prompt operacional aprobado

## 10.2 Resolver centralizado

Crear un servicio backend, por ejemplo:

```python
OperationalExecutionConfigResolver
```

Responsabilidad:

* devolver la configuración primaria vigente para inventarios `production`

## 10.3 Snapshot al crear inventario

Cuando se crea un inventario en `production`, el backend debe:

1. resolver la configuración operacional vigente
2. persistirla dentro del inventario

Esto evita que cambios futuros de defaults afecten inventarios ya creados.

---

## 11. Contratos API

## 11.1 CreateInventoryRequest

Agregar:

```python
processing_mode: Optional[Literal["production", "test"]] = "production"
```

Regla:

* si no viene, backend asume `production`

## 11.2 InventoryResponse

Agregar:

```json
{
  "processing_mode": "production",
  "primary_execution_config": {
    "provider_name": "gemini",
    "model_name": "gemini-2.5-pro",
    "prompt_key": "operational_default",
    "prompt_version": "v1"
  }
}
```

El shape exacto puede adaptarse al DTO actual, pero la idea es que el frontend entienda claramente:

* en qué modo está el inventario
* cuál es la configuración primaria efectiva si aplica

## 11.3 UpdateInventoryRequest

Solo si se decide permitir edición de modo en draft.

Si se implementa:

* agregar `processing_mode`
* validar reglas fuertes de mutabilidad

---

## 12. Reglas de mutabilidad

Recomendación de negocio:

solo permitir cambiar `processing_mode` si se cumplen todas:

* inventory está en `draft`
* no existen jobs asociados
* no existen resultados persistidos
* no existen acciones de review asociadas

Si no:

* responder con error de negocio

Esto evita ambigüedades operativas.

---

## 13. Casos de uso backend

## 13.1 CreateInventoryUseCase

Debe:

* aceptar `processing_mode`
* default a `production`
* si `production`:

  * resolver config operacional primaria
  * persistir snapshot en inventory
* si `test`:

  * no exigir snapshot obligatorio

## 13.2 Coordinador de ejecución

Crear un coordinador explícito, por ejemplo:

```python
LaunchInventoryAisleProcessingUseCase
```

Este decide:

```python
if inventory.processing_mode == PRODUCTION:
    launch operational flow
else:
    launch experimental flow
```

## 13.3 Flujo operacional

Crear caso de uso específico, por ejemplo:

```python
LaunchOperationalAisleJobUseCase
```

Responsabilidades:

* tomar la config primaria del inventario
* crear un solo job
* no aceptar selección múltiple
* marcar la intención operativa del job si aplica

## 13.4 Flujo experimental

Mantener o ajustar el flujo existente, por ejemplo:

```python
LaunchExperimentalAisleJobsUseCase
```

Responsabilidades:

* aceptar una o más configuraciones
* crear uno o múltiples jobs
* preservar compare / benchmark

---

## 14. Modelo de jobs

## 14.1 Recomendación

Agregar una noción explícita de intención/tipo del job.

Ejemplo:

```python
job_mode: Literal["operational", "experimental"]
```

## 14.2 Reglas

* inventory `production` => jobs `operational`
* inventory `test` => jobs `experimental` por defecto

Esto mejora:

* trazabilidad
* métricas
* debugging
* lectura de logs
* entendimiento del frontend

No es estrictamente obligatorio para el primer corte, pero sí muy recomendable.

---

## 15. Guards de negocio

Todos los endpoints ligados a comparación o benchmarking deben validar el modo del inventario.

## 15.1 Endpoints a auditar

Como mínimo:

* compare aisle runs
* export aisle benchmark compare
* export aisle benchmark run
* promote aisle operational job
* endpoints que asuman selección múltiple de corridas
* vistas o datos agregados exclusivamente comparativos

## 15.2 Regla

Si `inventory.processing_mode != test`:

* rechazar operación con `409 Conflict` o error de negocio equivalente

Mensaje sugerido:

* `"This feature is only available for test inventories."`

## 15.3 Importancia

Esto asegura que la separación entre modos no dependa del frontend.

---

## 16. Frontend — creación de inventario

## 16.1 Nuevo control

Agregar en la pantalla de creación:

* switch
* radio group
* segmented control

Con dos opciones:

* `Modo real`
* `Modo prueba`

Default:

* `Modo real`

## 16.2 Texto de ayuda

Propuesta:

**Modo real**
Usa la configuración principal del sistema y oculta herramientas de comparación.

**Modo prueba**
Permite ejecutar pruebas con múltiples proveedores, modelos y comparar resultados.

## 16.3 Envío al backend

El frontend solo debería mandar:

```json
{
  "processing_mode": "production"
}
```

o

```json
{
  "processing_mode": "test"
}
```

El backend resuelve la config primaria en production.

---

## 17. Frontend — inventory detail

## 17.1 Badge del modo

Mostrar chip o badge visible:

* `Production`
* `Test`

Esto debe verse en:

* inventory list item o detail header
* inventory detail
* donde sea útil para no generar confusión

## 17.2 Configuración primaria

En `production`, puede mostrarse de forma discreta:

* proveedor principal
* modelo principal
* prompt operacional

No como selector editable, sino como dato operativo.

---

## 18. Frontend — aisle detail y resultados

## 18.1 En `production`

Ocultar o remover:

* compare views
* benchmark tabs
* runs selector comparativo
* provider/model/prompt pickers
* tablas de comparación entre ejecuciones
* acciones de promote
* export compare benchmark

La experiencia debe quedar centrada en:

* job principal
* resultado operativo
* revisión del resultado
* estado del procesamiento

## 18.2 En `test`

Mantener la experiencia comparativa completa.

---

## 19. Ajustes de copy y UX

La separación no debe sentirse como “una UI recortada” sino como dos modos distintos con propósitos distintos.

## 19.1 Lenguaje para `production`

Usar términos como:

* Resultado operativo
* Ejecución actual
* Configuración principal

## 19.2 Lenguaje para `test`

Usar términos como:

* Comparative runs
* Benchmark
* Tested providers
* Experimental executions

---

## 20. Observabilidad

## 20.1 Metadata

Agregar `processing_mode` en:

* run metadata
* execution log metadata
* contextos de auditoría relevantes

## 20.2 Beneficio

Esto permite separar en el futuro:

* performance real del producto
* performance experimental de benchmark

---

## 21. Testing

## 21.1 Unit tests

Agregar cobertura para:

* default de `processing_mode` en create inventory
* creación de inventory `production`
* creación de inventory `test`
* resolución de config primaria en `production`
* rechazo de compare/benchmark en `production`
* selección de flujo operacional vs experimental
* bloqueo de cambio de modo cuando hay procesamiento

## 21.2 Integration tests

Cubrir:

### Production

* create inventory
* snapshot de config primaria
* launch single operational job
* compare/export/promote rechazados

### Test

* create inventory
* multi-config launch permitido
* compare/export benchmark permitido

## 21.3 Frontend tests

Cubrir:

* default `production` en create form
* toggle a `test`
* render de chip del modo
* ocultamiento de herramientas experimentales en `production`
* permanencia de features avanzadas en `test`

---

## 22. Plan por fases

# Fase 1 — Dominio, DB y DTOs

Objetivo: introducir el concepto de modo en el sistema.

Tareas:

* crear `InventoryProcessingMode`
* extender entidad `Inventory`
* migración SQL en `inventories`
* actualizar repositorios
* actualizar schemas request/response
* backfill de inventarios existentes a `test`

Resultado:

* sistema ya soporta inventarios `production` y `test`

---

# Fase 2 — Configuración operacional primaria

Objetivo: definir cómo nace un inventario `production`.

Tareas:

* crear resolver de config operacional primaria
* definir fuente de defaults operacionales
* persistir snapshot al crear inventory `production`
* exponer `primary_execution_config` en responses

Resultado:

* todo inventario `production` nace con una configuración estable y trazable

---

# Fase 3 — Bifurcación del procesamiento

Objetivo: separar flujo operativo vs experimental.

Tareas:

* introducir coordinador de ejecución
* crear `LaunchOperationalAisleJobUseCase`
* adaptar o mantener `LaunchExperimentalAisleJobsUseCase`
* hacer dispatch según `processing_mode`
* opcional: marcar `job_mode`

Resultado:

* production crea una sola corrida operativa
* test mantiene multi-run

---

# Fase 4 — Guards backend

Objetivo: bloquear features experimentales en inventarios production.

Tareas:

* auditar endpoints de compare/benchmark/promote
* agregar validaciones por `processing_mode`
* estandarizar errores de negocio
* adaptar frontend a nuevos errores

Resultado:

* la separación entre modos queda enforced server-side

---

# Fase 5 — Frontend create + detail

Objetivo: exponer y visualizar el modo del inventario.

Tareas:

* agregar selector de modo al crear
* default `production`
* mostrar badge del modo
* mostrar config primaria donde tenga sentido

Resultado:

* usuario puede crear inventarios reales o de prueba de forma explícita

---

# Fase 6 — Frontend aisle/results cleanup

Objetivo: limpiar UX según modo.

Tareas:

* ocultar compare/benchmark/pickers en production
* simplificar detail/results en production
* preservar UX experimental en test

Resultado:

* production queda simple
* test conserva complejidad de benchmark

---

# Fase 7 — Hardening

Objetivo: cerrar huecos y verificar compatibilidad total.

Tareas:

* revisar inventarios existentes
* revisar exportes y vistas auxiliares
* revisar logs y metadata
* agregar tests faltantes
* hardening de edge cases

Resultado:

* feature robusta y lista para uso real

---

## 23. Riesgos

## 23.1 Riesgo

Romper inventarios existentes.

Mitigación:

* backfill inicial a `test`

## 23.2 Riesgo

Hacer solo cambios visuales.

Mitigación:

* guards backend obligatorios

## 23.3 Riesgo

Que cambios futuros del default global alteren inventarios viejos.

Mitigación:

* snapshot de config primaria en inventory

## 23.4 Riesgo

Confundir modo del inventario con tipo de job.

Mitigación:

* mantener ambos conceptos separados si se introduce `job_mode`

---

## 24. Criterios de aceptación

La implementación estará completa cuando:

* todo inventario nuevo se cree en `production` por defecto
* el usuario pueda activar explícitamente `test`
* un inventario `production` use una única configuración primaria
* un inventario `production` no permita compare/benchmark/promote
* un inventario `test` mantenga el flujo multiproveedor actual
* el backend rechace correctamente operaciones experimentales sobre `production`
* el frontend oculte las herramientas experimentales en `production`
* los inventarios existentes sigan funcionando sin ruptura

---

## 25. Recomendación final

Para esta fase, la decisión más sólida es:

* introducir `processing_mode`
* hacer `production` el default
* persistir snapshot de la config operacional primaria
* mover toda la experiencia comparativa a `test`
* backfillear inventarios existentes a `test`
* aplicar guards server-side
