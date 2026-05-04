# Auditoría backend - SOLID y GRASP

## Alcance

Evaluación heurística de arquitectura backend sobre capas `api`, `application`, `domain`, `infrastructure`, `pipeline`, `llm`, `runtime`, sin modificar comportamiento funcional.

## Señales automáticas analizadas

- Complejidad ciclomática (radon): indicadores de riesgo alto detectados aprox=962
- Code smells (pylint/vulture):
  - too-many-arguments: 117
  - too-many-branches: 24
  - too-many-returns: 21
  - clases/metodos voluminosos: 64
  - broad-exception: 0
  - imports no usados: 7
  - codigo potencialmente muerto (vulture): 758
- Límites de imports entre capas: FAIL=1, REVIEW=2
- Rutas API sospechosas de lógica pesada (heurística): 5

## SOLID

### Single Responsibility Principle
- Señales: módulos/rutas extensas y métricas de métodos con alta complejidad o demasiadas ramas.
- Observación inicial: revisar rutas API y servicios con señales de tamaño/ramificación elevadas.

### Open/Closed Principle
- Señales: condicionales extensos por provider/status/modelo en pipeline/llm.
- Observación inicial: auditar puntos con `if/elif` largos antes de introducir nuevos proveedores.

### Liskov Substitution Principle
- Señales: adapters con retornos incompatibles o contratos débiles detectados por análisis estático.
- Observación inicial: cruzar findings de tipado con implementación de ports/adapters.

### Interface Segregation Principle
- Señales: interfaces/ports con demasiadas responsabilidades o métodos no cohesivos.
- Observación inicial: revisar puertos de application/domain con crecimiento orgánico.

### Dependency Inversion Principle
- Señales: imports prohibidos entre capas (especialmente domain/application hacia capas externas).
- Observación inicial: hallazgos de boundaries requieren validación manual y eventual refactor dirigido.

## GRASP

### Information Expert
- Señal: reglas de dominio ubicadas fuera de `domain` o con acoplamiento a infraestructura.

### Controller
- Señal: rutas FastAPI con coordinación/lógica de negocio extensa.

### Low Coupling
- Señal: imports cruzados entre capas y dependencia circular implícita.

### High Cohesion
- Señal: módulos mezclando validación, orquestación y persistencia en la misma unidad.

### Creator
- Señal: creación de entidades/dtos lejos del contexto experto del dominio.

### Indirection
- Señal: uso parcial de ports/adapters o bypass directo de infraestructura.

### Protected Variations
- Señal: cambios de proveedor LLM impactando más capas que adapters y configuración.

## Hallazgos iniciales

- Se detectaron señales de complejidad y code smells suficientes para justificar auditoría manual por módulo.
- Los límites de imports muestran señales `FAIL/REVIEW` en reglas clave de capas.
- Existen rutas API con indicadores heurísticos de posible sobrecarga de coordinación.
- El patrón de encapsulación de proveedores requiere seguimiento para mantener DIP/Protected Variations.

## Limitaciones

- SOLID y GRASP no se validan de forma determinista como tests unitarios.
- Esta auditoría usa señales heurísticas automatizadas y semi-automatizadas.
- Requiere revisión manual posterior para confirmar severidad e impacto.
- Puede contener falsos positivos o falsos negativos por parseo estático.

## Recomendaciones futuras

- Definir contratos explícitos de imports por capa (policy as code) y versionarlos.
- Priorizar refactor en módulos con complejidad C/D/E/F y code smells recurrentes.
- Revisar rutas API con señales de orquestación excesiva y mover lógica a application/use-cases.
- Fortalecer test de arquitectura para prevenir regresiones de acoplamiento.
- generated_at: 2026-05-04 10:30:17
