# Plan de implementación del módulo de ingesta de medios

## 1. Resumen ejecutivo

El plan se actualiza por una corrección de producto: el flujo principal real no es aisle-first, sino ingestión de lote completo post-vuelo con descubrimiento de pasillos a partir de agrupación automática.

La dirección oficial pasa a ser:

```plaintext
inventario -> sesión de importación (nivel inventario) -> upload vuelo completo
-> agrupación automática -> revisión de grupos -> asignación grupo->pasillo
-> materialización -> procesamiento por pasillo
```

Esta corrección no invalida el backend construido. La estrategia es preservar la base ya implementada (staging, extracción temporal, idempotencia, materialización, handoff a SourceAsset) y reorientar la orquestación.

## 2. Problema del modelo previo aisle-first

El modelo anterior asumía como camino principal:

```plaintext
inventario -> pasillo -> sesión -> upload
```

Limitaciones principales:

- Requiere decidir el pasillo antes de subir el lote, lo cual no coincide con el flujo operativo post-vuelo.
- Obliga al operador a separar manualmente imágenes por pasillo antes de aprovechar la lógica del sistema.
- Coloca demasiado pronto decisiones de destino (`aisle_id`) que en la práctica se resuelven tras revisar el lote.
- Empuja UI y casos de uso hacia carga “por pasillo conocido”, perdiendo el valor central de descubrimiento y organización automática.

Conclusión: el enfoque aisle-first puede existir como camino secundario, pero no debe seguir siendo la ruta de entrega principal.

## 3. Valor backend actual a preservar

### Keep

Capacidades implementadas y conceptualmente correctas sin conflicto con el nuevo modelo:

- Ciclo de vida de sesión (base de orquestación de importación).
- `CaptureSessionItem` como staging persistente.
- Extracción temporal determinística (`EXIF`, `mtime`, fallback) y política explícita.
- `clock_offset_seconds` y consistencia temporal.
- Spine de materialización a `SourceAsset`.
- Idempotencia de materialización y rollback seguro.
- Errores estructurados (`code` + `detail`).
- Invariante de pipeline: `process_aisle` consume solo `SourceAsset`.

### Adapt

Capacidades valiosas que deben reescalarse al modelo grouping-first:

- Scope de sesión: de `inventory_id + aisle_id` a sesión primaria a nivel inventario.
- Preview actual: reubicarlo como etapa downstream después de asignación grupo->pasillo.
- Materialización: mantener mecánica técnica, cambiar el disparador/orquestación para operar sobre items ya asignados por grupo.
- UI R2 ya iniciada: reutilizar componentes de upload/listado/detalle, cambiando semántica y secuencia.

### Reconsider

Elementos definidos bajo la suposición aisle-first que no deben seguir como camino principal:

- Crear sesión obligatoriamente ligada a un pasillo.
- UX de “seleccionar pasillo primero, subir después” como flujo por defecto.
- Lectura de valor centrada en “asignación a posiciones” antes de resolver agrupación y mapping a pasillos.

## 4. Modelo conceptual revisado

### 4.1 Sesión de importación a nivel inventario

- Unidad principal para un vuelo completo.
- Puede contener imágenes de múltiples pasillos potenciales.

### 4.2 Upload de vuelo completo

- Carga masiva en staging de todos los archivos del vuelo.
- Trazabilidad por item y feedback por archivo.

### 4.3 Agrupación automática

- El sistema genera grupos provisionales (candidatos de pasillo/segmento operativo).
- La agrupación es previa a cualquier materialización.

### 4.4 Revisión de grupos

- Operador valida grupos y su calidad operativa.
- En fases posteriores se habilitan acciones avanzadas (merge/split/relabel), no necesarias para el primer corte.

### 4.5 Asignación grupo->pasillo

- Cada grupo se asigna a pasillo existente o crea nuevo pasillo.
- La decisión de destino queda explícita y auditable antes de materializar.

### 4.6 Materialización consciente de asignación

- Solo items con asignación válida se materializan a `SourceAsset`.
- Se mantiene idempotencia y rollback seguro.

### 4.7 Handoff a pipeline

- El procesamiento sigue siendo por pasillo.
- No cambia el contrato: solo `SourceAsset`.

## 5. Roadmap actualizado por fases

## G0 — Alineación y congelamiento de dirección

- **Objetivo:** detener deriva aisle-first y alinear ingeniería/producto/UX en modelo grouping-first.
- **Backend scope:** documentación de contratos y semántica de transición.
- **UI scope:** ajuste del roadmap y mensajes para nueva secuencia operativa.
- **Dependencias:** estado actual R1/R2.
- **Prioridad:** inmediata.

## G1 — Fundación de sesión a nivel inventario

- **Objetivo:** establecer sesión primaria sin requerir pasillo de entrada.
- **Backend scope:** endpoints/uc de sesión para scope inventario (manteniendo compatibilidad con flujos existentes durante transición).
- **UI scope:** crear/listar sesiones de importación por inventario.
- **Dependencias:** G0.
- **Prioridad:** inmediata.

## G2 — Workspace de upload de vuelo completo

- **Objetivo:** soportar carga operativa de lotes completos (post-vuelo).
- **Backend scope:** reutilizar staging actual, validaciones y metadata temporal.
- **UI scope:** upload masivo robusto, estados por archivo, listado ordenado de items.
- **Dependencias:** G1.
- **Prioridad:** inmediata.

## G3 — Motor de agrupación automática

- **Objetivo:** producir grupos provisionales a partir del lote cargado.
- **Backend scope:** servicio/caso de uso de agrupación + persistencia de membresía por grupo.
- **UI scope:** visualización inicial de grupos y métricas básicas de agrupación.
- **Dependencias:** G2.
- **Prioridad:** inmediata siguiente.

## G4 — Revisión de grupos y asignación a pasillos

- **Objetivo:** permitir decisión operativa de destino por grupo.
- **Backend scope:** casos de uso para asignar grupo a pasillo existente o crear pasillo desde grupo.
- **UI scope:** pantalla de revisión/decisión por grupo.
- **Dependencias:** G3 y APIs de pasillos existentes.
- **Prioridad:** inmediata siguiente.

## G5 — Materialización con asignación previa

- **Objetivo:** materializar solo grupos/items con destino confirmado.
- **Backend scope:** reutilizar spine actual de materialización e idempotencia, cambiando orquestación de entrada.
- **UI scope:** acción de materializar por sesión/grupo y feedback de resultados.
- **Dependencias:** G4.
- **Prioridad:** núcleo posterior.

## G6 — Preview a nivel posición en lugar correcto

- **Objetivo:** aplicar preview item->posición luego de conocer el pasillo destino.
- **Backend scope:** reubicar precondiciones del preview actual.
- **UI scope:** vista de preview downstream por pasillo asignado.
- **Dependencias:** G4/G5.
- **Prioridad:** posterior.

## G7 — Hardening operativo

- **Objetivo:** robustez de operación, soporte y observabilidad.
- **Backend scope:** métricas, logs, trazabilidad y herramientas de recuperación.
- **UI scope:** vistas operativas para sesiones/grupos con incidencias.
- **Dependencias:** G1-G6.
- **Prioridad:** posterior.

## G8 — Integración directa con dron (track separado)

- **Objetivo:** explorar integración conectada sin bloquear el core post-vuelo.
- **Backend scope:** diseño de adaptador de ingesta externa.
- **UI scope:** mínimo para discovery, sin comprometer roadmap principal.
- **Dependencias:** madurez del core grouping-first.
- **Prioridad:** futuro separado.

## 6. Implicancias para UI

### 6.1 Qué no debe continuar como ruta principal

- El flujo de UI centrado en “elegir pasillo primero y subir después” no debe guiar la entrega principal.

### 6.2 Qué se puede reutilizar de R2

- Componentes de upload masivo con progreso/errores por archivo.
- Patrones de guardrails de estado, listas y detalle de sesión.
- Integración base con query/mutations y manejo de errores estructurados.

### 6.3 Nueva secuencia UI prioritaria

1. Selección/creación de inventario.
2. Creación de sesión de importación a nivel inventario.
3. Upload de vuelo completo.
4. Revisión de lote agrupado.
5. Asignación de grupos a pasillos (existente/nuevo).
6. Materialización y handoff a procesamiento por pasillo.

## 7. Implicancias de preview y materialización

### Preview

- El preview determinístico actual no se descarta.
- Se reposiciona como capacidad downstream (después de asignar grupo->pasillo).
- Se incorpora una nueva etapa upstream: preview de agrupación/descubrimiento.

### Materialización

- Debe ocurrir solo después de tener asignación de pasillo por grupo.
- El spine técnico actual se mantiene: idempotencia, rollback, trazabilidad y persistencia en `SourceAsset`.
- Cambia la orquestación de entrada (items elegibles definidos por grupos asignados).

## 8. Iniciativa futura separada

La integración directa con dron se mantiene como iniciativa separada.

Razones:

- El valor principal inmediato está en post-vuelo + grouping-first.
- Evita acoplar roadmap core a dependencias de SDK/proveedores.
- Permite entregar valor operativo antes de resolver integración conectada.

## 9. Recomendación final

Recomendación de ejecución:

1. Detener la evolución del flujo UI aisle-first como ruta principal.
2. Preservar la base backend ya implementada.
3. Reorientar la orquestación a sesión de inventario + agrupación + asignación.
4. Mantener materialización y pipeline sobre `SourceAsset` sin cambios de contrato.
5. Entregar primero el flujo completo de negocio real:

```plaintext
inventario -> sesión inventario -> upload vuelo completo -> agrupación
-> revisión/asignación -> materialización -> procesamiento
```

Esta ruta maximiza reutilización de lo construido y corrige la alineación producto-arquitectura sin reiniciar el proyecto.
