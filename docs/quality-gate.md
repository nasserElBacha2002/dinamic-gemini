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

Nota: en esta etapa los scripts de `scripts/audit/` son placeholders seguros; verifican disponibilidad y preparan estructura, pero no ejecutan auditorías reales todavía.

## No objetivos (por ahora)

- No se corrigen bugs.
- No se corrigen vulnerabilidades.
- No se cambia lógica de negocio ni flujo funcional.
- No se incorporan herramientas pesadas adicionales fuera de lo necesario para esta base.
