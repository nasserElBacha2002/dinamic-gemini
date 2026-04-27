# Quality Gate previo a deploy en develop

## Estado de esta implementación

Este documento define la base inicial del Quality Gate en modalidad progresiva.
En esta etapa solo se prepara alcance, estructura y documentación de auditoría.
No se corrigen hallazgos todavía y no se modifica lógica funcional del sistema.

## Objetivo general

- Ejecutar validaciones automáticas antes del deploy a `develop`.
- Detectar bugs, vulnerabilidades y problemas de calidad técnica.
- Generar evidencia documentable y descargable de cada ejecución.
- Registrar hallazgos para tratamiento posterior, sin corregirlos en esta fase.

## Áreas a validar

### Backend (Python + FastAPI)

- Ruff
- Mypy
- Bandit
- pip-audit
- Pytest
- Trivy

### Frontend (React + TypeScript + Vite + MUI)

- ESLint
- Typecheck
- npm audit
- Vitest

### Sistema corriendo

- OWASP ZAP baseline scan

## Política inicial del gate

- El Quality Gate comienza en modo progresivo.
- En el arranque, el bloqueo se limita a errores graves o fallos de build/ejecución.
- Los hallazgos de seguridad se documentan siempre, aunque no bloqueen aún.
- La política de bloqueo se endurece por fases en iteraciones futuras.

## Resultado esperado en esta etapa

- Antes de deployar a `develop`, el sistema tendrá una base para ejecutar validaciones.
- Los reportes y evidencias se almacenarán en la carpeta `audit/`.
- Se podrá rastrear qué herramienta detectó cada hallazgo.
- Queda lista la estructura para automatización gradual sin afectar el deploy actual.

## Fases implementadas en este paso

### Fase 0 — Alcance

- Documento de alcance inicial del Quality Gate.
- Definición de herramientas por área.
- Política progresiva de bloqueo.

### Fase 1 — Estructura de auditoría

- Estructura base `audit/` para reportes y backlog.
- Scripts placeholder en `scripts/audit/` para orquestación futura.
- Preparación de `audit/raw/` como repositorio de evidencia.

### Fase 2 — Auditoría local del backend

En esta fase, `scripts/audit/run_backend_audit.sh` ejecuta auditoría local real del backend (sin bloquear deploy).

Herramientas ejecutadas cuando están disponibles:

- Ruff
- Mypy
- Bandit
- pip-audit
- Pytest

Archivos de salida generados en `audit/raw/`:

- `audit/raw/backend-ruff.txt`
- `audit/raw/backend-mypy.txt`
- `audit/raw/backend-bandit.json`
- `audit/raw/backend-pip-audit.json`
- `audit/raw/backend-pytest.txt`

Comportamiento clave:

- Sigue siendo **no bloqueante** en esta etapa.
- Si una herramienta no está instalada, se documenta y se continúa.
- Si hay findings o errores en una herramienta, se registra y se continúa.
- El script finaliza con `exit 0` para no frenar el flujo actual.

Ejecución:

```bash
bash scripts/audit/run_backend_audit.sh
```

### Fase 3 — Auditoría local del frontend

En esta fase, `scripts/audit/run_frontend_audit.sh` ejecuta auditoría local real del frontend en modo no bloqueante.

Herramientas ejecutadas cuando están disponibles:

- ESLint
- Typecheck
- npm audit
- Vitest

Auditorías estáticas adicionales:

- Auditoría de `useEffect`
- Auditoría de manejo de errores frontend
- Auditoría de componentes reutilizables/genéricos

Archivos de salida generados en `audit/raw/`:

- `audit/raw/frontend-eslint.txt`
- `audit/raw/frontend-typecheck.txt`
- `audit/raw/frontend-npm-audit.json`
- `audit/raw/frontend-vitest.txt`
- `audit/raw/frontend-useeffects-audit.md`
- `audit/raw/frontend-error-handling-audit.md`
- `audit/raw/frontend-reusable-components-audit.md`

Comportamiento clave:

- Sigue siendo **no bloqueante** en esta etapa.
- Si una herramienta no está instalada o no existe script npm, se documenta y se continúa.
- Si hay findings o errores, se registra estado por herramienta y se continúa.
- El script finaliza con `exit 0` para no bloquear el flujo actual.

Ejecución:

```bash
bash scripts/audit/run_frontend_audit.sh
```

## Dependencias de auditoría (backend)

Las herramientas de auditoría del backend se declaran como dependencias de desarrollo en:

- `backend/pyproject.toml` → `[project.optional-dependencies].dev`

Herramientas declaradas en dev para el gate inicial:

- `ruff`
- `mypy`
- `bandit`
- `pip-audit`
- `pytest`

Instalación recomendada (sin instalar globalmente):

```bash
cd backend
pip install -e ".[dev]"
```

Nota: en Fase 2 el script de backend ya ejecuta auditorías reales en modo no bloqueante. Los demás scripts pueden continuar como placeholders hasta su fase correspondiente.

## No objetivos (por ahora)

- No se corrigen bugs.
- No se corrigen vulnerabilidades.
- No se cambia lógica de negocio ni flujo funcional.
- No se incorporan herramientas pesadas adicionales fuera de lo necesario para esta base.
