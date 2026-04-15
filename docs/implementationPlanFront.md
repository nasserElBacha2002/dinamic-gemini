# Plan de implementación

## Objetivo general

Optimizar el flujo end to end de datos en el frontend para que:

* cada interacción del usuario genere la menor cantidad posible de requests
* el cache sea la fuente principal de verdad en lectura
* las mutaciones no disparen invalidaciones globales innecesarias
* las pantallas críticas reutilicen mejor los datos ya cargados
* se reduzca el jitter visual por `isFetching` y remounts evitables

---

# Fase 0 — Línea de base y medición

## Objetivo

Antes de tocar comportamiento, medir el estado actual para validar mejoras reales.

## Tareas

* Mapear requests por flujo crítico:

  * crear inventario
  * abrir inventory detail
  * abrir aisle positions
  * ejecutar review action
  * merge
  * promote operational job
  * abrir metrics
* Agregar instrumentación temporal en desarrollo para contar:

  * requests por interacción
  * invalidaciones por mutación
  * refetches manuales
* Revisar con DevTools de React Query:

  * queries activas
  * observers
  * invalidaciones
  * loops de refetch
* Documentar baseline:

  * cantidad de requests por acción
  * pantallas con mayor fan-out
  * queries con más frecuencia de refetch

## Entregable

* Documento corto o markdown con:

  * flujo
  * requests actuales
  * hipótesis de duplicación
  * target esperado después de optimizar

## Criterio de éxito

Tener una foto clara del “antes” para comparar el impacto de cada fase.

---

# Fase 1 — Eliminar duplicación obvia: invalidate + refetch manual

## Objetivo

Eliminar el patrón más costoso y simple de corregir.

## Problema que resuelve

Hoy varias mutaciones hacen:

* invalidación
* `refetch()` manual
* y a veces además otros componentes reaccionan al cambio

Eso duplica requests innecesariamente.

## Tareas

* Auditar mutaciones en:

  * `InventoriesList`
  * `InventoryDetail`
  * `AislePositionsPage`
  * hooks dentro de `useMutations.ts`
* Detectar todos los casos donde ocurre:

  * `invalidateQueries(...)` + `refetch()`
* Definir regla única:

  * usar **o invalidación**
  * **o refetch dirigido**
  * pero no ambos para el mismo dato
* Priorizar corrección en:

  * create inventory
  * create aisle
  * upload/process aisle
  * merge
  * promote operational job

## Estrategia recomendada

* Si hay múltiples filtros o vistas escuchando el dato: preferir `invalidateQueries`
* Si es una query singular y visible: evaluar `setQueryData` o `refetch` dirigido
* Evitar que la página vuelva a “asegurarse” si el hook de mutación ya resuelve actualización

## Entregable

* Primer PR de limpieza táctica
* Lista de flows corregidos

## Criterio de éxito

Reducir requests redundantes sin cambiar comportamiento funcional visible.

---

# Fase 2 — Ordenar query keys y canonicalización de parámetros

## Objetivo

Hacer que el cache sea consistente y reutilizable.

## Problema que resuelve

Cuando las query keys se construyen con objetos inestables o inconsistentes:

* se fragmenta cache
* se pierden hits reutilizables
* aumentan refetches
* se vuelve difícil invalidar correctamente

## Tareas

* Centralizar todas las keys en una factory común
* Migrar keys inline a `queryKeys`

  * especialmente review queue
* Crear una utilidad de canonicalización de params:

  * normalizar `undefined`, `null`, strings vacíos
  * ordenar claves si aplica
  * evitar objetos reconstruidos con shape variable
* Revisar:

  * inventories list
  * review queue
  * analytics
  * aisles / positions / jobs
* Confirmar que las keys representen correctamente:

  * filtros
  * paginación
  * sorting
  * job seleccionado
  * inventory/aisle ids

## Decisión de diseño

Cada query key debe representar solo el estado realmente relevante para el request.

## Entregable

* Key factory unificada
* Helper de params normalizados
* Refactor de hooks prioritarios

## Criterio de éxito

Menor fragmentación de cache y mayor previsibilidad al invalidar.

---

# Fase 3 — Reducir fan-out de invalidaciones en mutaciones críticas

## Objetivo

Hacer que una acción chica no refresque media aplicación.

## Problema que resuelve

Mutaciones como review actions hoy impactan demasiados dominios a la vez:

* detail
* positions
* merge results
* jobs
* metrics
* inventory detail
* review queue

Eso genera bursts de red por cada click.

## Tareas

* Auditar cada mutación crítica y listar:

  * qué invalida hoy
  * qué debería invalidar realmente
* Reducir invalidaciones por contexto
* Separar entre:

  * invalidación estrictamente necesaria
  * invalidación “por seguridad”
* Eliminar invalidaciones no visibles o no relevantes para la pantalla actual
* Revisar especialmente:

  * `useSubmitReviewAction`
  * merge flow
  * promote flow
  * create/update/delete ligados a results

## Regla nueva

Toda mutación debe declarar explícitamente:

* dato afectado directo
* vistas que dependen realmente de ese dato
* si necesita patch local o invalidación
* si alguna métrica puede refrescarse después o bajo demanda

## Entregable

* Matriz de invalidaciones por mutación
* Refactor de las mutaciones de mayor impacto

## Criterio de éxito

Bajar drásticamente requests por interacción en review y resultados.

---

# Fase 4 — Introducir Mutation Strategy por contexto

## Objetivo

Evitar que una misma mutación se comporte igual en todos los contextos.

## Problema que resuelve

No es lo mismo ejecutar una review action desde:

* review queue
* aisle positions
* detail drawer

Si todas invalidan igual, se pierde precisión y se sobrecarga red.

## Propuesta

Crear una estrategia por contexto de uso.

## Ejemplo conceptual

* `queue`
* `aisle`
* `detail`

Cada una decide:

* qué cache patch local aplicar
* qué queries invalidar
* qué no tocar

## Tareas

* Diseñar contrato de strategy
* Aplicarlo primero a review actions
* Luego extender a merge/promote si aporta valor
* Mantener API simple para uso en componentes

## Beneficio

Esto da control fino sin duplicar toda la lógica de mutación.

## Entregable

* Primera versión de mutation strategy layer
* Integración con review flow

## Criterio de éxito

La misma acción produce efectos distintos y controlados según pantalla.

---

# Fase 5 — Introducir cache patching con `setQueryData`

## Objetivo

Mover parte de la actualización post-mutation del backend hacia el cache local.

## Problema que resuelve

Muchos cambios son chicos y locales:

* una fila cambia estado
* una posición sale de la queue
* una cantidad corregida impacta una lista puntual

No hace falta refetchear todo.

## Tareas

* Identificar mutaciones aptas para patch local:

  * review actions sobre una fila
  * confirm / unknown / corrected quantity
  * cambios puntuales en lists visibles
* Implementar `setQueryData` sobre:

  * positions list
  * review queue
  * detail puntual si corresponde
* Dejar invalidación diferida o secundaria solo donde sea necesario
* Asegurar consistencia en casos de:

  * paginación
  * filtros
  * datos derivados visibles

## Regla

Usar patch local cuando:

* el cambio es pequeño
* el impacto está contenido
* el shape del dato es conocido

## Entregable

* Primeras mutaciones con patch local
* Menor dependencia en refetch post-action

## Criterio de éxito

UI más inmediata y menos requests por acción.

---

# Fase 6 — Revisar ownership de datos por pantalla

## Objetivo

Ordenar quién “posee” cada dato en pantallas complejas.

## Problema que resuelve

Hoy hay páginas donde:

* varios componentes escuchan el mismo dato
* varios disparan refresh
* varios sincronizan URL + estado + query

Eso genera fetches intermedios y contratos de props demasiado pesados.

## Tareas

* Revisar ownership en:

  * `InventoryDetail`
  * `AislePositionsPage`
  * `ReviewQueuePage`
* Separar claramente:

  * estado de URL
  * estado de UI local
  * datos remotos
  * acciones/mutations
* Evitar que subcomponentes vuelvan a pedir datos que el contenedor ya posee
* Reducir props de gran tamaño
* Pasar solo los slices necesarios

## Entregable

* Refactor ligero de contenedores principales
* Contratos de props más chicos y estables

## Criterio de éxito

Menos rerenders, menos lógica repetida y menos fetch indirecto por cambios de props.

---

# Fase 7 — Estabilizar efectos y sincronización URL/estado

## Objetivo

Eliminar requests intermedios por sincronización mal secuenciada.

## Problema que resuelve

Pantallas como `AislePositionsPage` pueden:

* alinear jobId por URL
* recalcular selección
* disparar queries en estados transitorios

Eso produce fetches que el usuario ni llega a usar.

## Tareas

* Revisar `useEffect` dependientes de:

  * objetos no memoizados
  * ids derivados
  * route params + local state
* Unificar normalización de estado antes de habilitar queries
* Aplicar `enabled` con condiciones más estables
* Evitar que cambios de UI gatillen queries sin necesidad
* Revisar drawers, dialogs y tabs:

  * cuándo montan
  * cuándo habilitan fetch
  * cuándo reutilizan cache

## Entregable

* Efectos simplificados en pantallas críticas
* Menos queries intermedias por transición

## Criterio de éxito

Navegación más limpia y menor ruido de red.

---

# Fase 8 — Afinar política de cache por tipo de endpoint

## Objetivo

Configurar la cache según naturaleza del dato, no con defaults genéricos.

## Problema que resuelve

No todos los endpoints tienen la misma volatilidad.

## Tareas

Clasificar endpoints:

### Tipo A — Muy volátiles

Ejemplo:

* positions activas
* review queue
* jobs en ejecución

Para estos:

* `staleTime` corto
* invalidación precisa
* patch local donde se pueda

### Tipo B — Moderadamente estables

Ejemplo:

* inventories list
* aisles list
* merge results ya consolidados

Para estos:

* `staleTime` mayor
* menos refetch al navegar

### Tipo C — Casi estáticos

Ejemplo:

* catálogos
* options
* provider settings
* metadata

Para estos:

* `staleTime` alto
* evitar refetch on mount innecesario

## Revisar

* `refetchOnMount`
* `refetchOnWindowFocus`
* `refetchOnReconnect`
* `retry`
* `gcTime`
* `placeholderData`

## Entregable

* Tabla de política de cache por endpoint/hook

## Criterio de éxito

Menos refetch automático sin perder consistencia donde importa.

---

# Fase 9 — Reutilización de datos entre lista y detalle

## Objetivo

Evitar pedir de nuevo datos que ya existen en cache en otra vista.

## Problema que resuelve

Hay casos donde:

* la lista ya tiene parte del dato
* el detalle vuelve a pedir todo desde cero
* se desaprovecha cache ya cargado

## Tareas

* Revisar transiciones:

  * inventories list → inventory detail
  * aisles list → aisle detail/results
  * review queue → quick review drawer
* Usar:

  * `placeholderData`
  * `initialData`
  * `select`
  * prefetch bajo intención de navegación cuando tenga sentido
* Aprovechar entidades ya presentes para “primer render útil”

## Entregable

* Mejoras puntuales de reuse en flows principales

## Criterio de éxito

Menos loading states duros y menos refetches redundantes al navegar.

---

# Fase 10 — Limpieza de props, callbacks y contratos de componentes

## Objetivo

Evitar rerenders y efectos indirectos innecesarios.

## Problema que resuelve

Las props no solo afectan render: también pueden disparar:

* efectos
* recomputaciones
* cambios de query key
* fetches

## Tareas

* Detectar componentes que reciben DTOs enteros sin necesitarlos
* Reducir props a campos mínimos
* Estabilizar callbacks donde realmente importe
* Evitar pasar objetos derivados recreados en cada render si alimentan hooks/effects
* Separar:

  * props puramente visuales
  * props de comportamiento
  * props de datos remotos

## Entregable

* Refactor incremental en componentes de mayor tráfico

## Criterio de éxito

Menos rerender útil perdido y menos fetch inducido por cambios de referencia.

---

# Fase 11 — Validación final y hardening

## Objetivo

Confirmar que la optimización es real y no introdujo inconsistencias.

## Tareas

* Repetir medición de Fase 0
* Comparar:

  * requests por interacción
  * invalidaciones por mutación
  * tiempo percibido de actualización
  * estabilidad visual
* Validar escenarios críticos:

  * navegación rápida
  * varias review actions consecutivas
  * merge + promote
  * abrir/cerrar drawers repetidamente
  * cambios de filtros
* Ajustar casos borde detectados

## Entregable

* Resumen before/after
* Lista de mejoras efectivamente logradas
* Pendientes de segunda etapa si existieran

---

# Orden recomendado de implementación

## Etapa 1 — Alto ROI y bajo riesgo

1. Fase 0 — línea de base
2. Fase 1 — eliminar invalidate + refetch manual
3. Fase 2 — query keys y canonicalización
4. Fase 3 — reducir invalidaciones masivas

## Etapa 2 — Mejora estructural real

5. Fase 4 — mutation strategy por contexto
6. Fase 5 — cache patching con `setQueryData`
7. Fase 6 — data ownership por pantalla
8. Fase 7 — estabilizar URL/estado/effects

## Etapa 3 — Optimización fina

9. Fase 8 — tuning de cache por endpoint
10. Fase 9 — reuse lista/detalle
11. Fase 10 — limpieza de props
12. Fase 11 — validación final

---

# Prioridades concretas

## Prioridad máxima

* `useSubmitReviewAction`
* flows de `AislePositionsPage`
* mutaciones que combinan invalidación + refetch

## Prioridad alta

* `ReviewQueuePage`
* `InventoryDetail`
* keys de analytics y review queue

## Prioridad media

* drawers, dialogs, observability
* prefetch y placeholderData
* afinado de props

---

# Resultado esperado

Si este plan se ejecuta bien, deberías lograr:

* menos requests por interacción
* menos bursts después de mutaciones
* mejor reutilización de cache
* menor carga sobre backend
* UI más estable
* menos complejidad accidental en hooks y pantallas críticas

---

# Criterios de éxito medibles

Podés medir éxito con estos indicadores:

* reducción de requests por review action
* reducción de requests por merge/promote
* menor cantidad de queries invalidadas por mutación
* menor cantidad de refetches manuales
* menor tiempo de actualización visible
* menor jitter de loading en pantallas críticas

---

# Recomendación final

Yo lo implementaría así:

**Sprint 1**

* Fase 0
* Fase 1
* Fase 2
* Fase 3

**Sprint 2**

* Fase 4
* Fase 5
* Fase 6

**Sprint 3**

* Fase 7
* Fase 8
* Fase 9
* Fase 10
* Fase 11
