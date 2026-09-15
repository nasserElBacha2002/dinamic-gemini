# 01 — Repository baseline

## Git (inicio de auditoría)

| Campo | Valor | Evidencia |
|-------|-------|-----------|
| Branch | `DIN-357` | `_baseline-branch.txt` |
| Commit | `219b88bcae1181a0b434425efe48b5fa2c70f3b3` | `_baseline-commit.txt` |
| Working tree inicial | Limpio (0 líneas porcelain al primer `git status` de sesión) | Conversación / re-baseline |
| Working tree al cerrar | Solo `?? audit/september-code-audit/` | `_final-git-status.txt` |
| Commit / push | **No realizados** | Política fase 1 |

Nota: durante la sesión, un glob accidental dejó archivos `audit/*.md` como `D`; se restauraron con `git restore audit/` **antes** de escribir artefactos. Estado final no conserva esas borraduras.

## Runtimes

| Runtime | Versión |
|---------|---------|
| OS | macOS 26.5.1 (Darwin 25.5.0, arm64) |
| Python sistema | 3.14.6 |
| Python backend `.venv` | 3.13.12 (`backend/.venv`) |
| Node | v22.14.0 |
| npm | 11.4.2 |
| Docker CLI | 28.1.1 (daemon **no usable** desde sandbox del agente) |
| gitleaks host | 8.30.1 (`/opt/homebrew/bin/gitleaks`) |

## Gestores de paquetes

- Python: `pip` / `backend/pyproject.toml` (`pip install -e ".[dev]"`)
- Node: npm + lockfiles (`frontend/package-lock.json`, `mobile/package-lock.json`, root `package-lock.json`)
- No Poetry / pnpm / yarn detectados como primario

## Estructura top-level (VERIFIED)

| Path | Rol |
|------|-----|
| `backend/` | FastAPI, domain/application/infrastructure, jobs, pipeline, migraciones |
| `frontend/` | React + Vite + MUI |
| `mobile/` | Expo / React Native captura |
| `contracts/` | JSON schemas versionados |
| `scripts/audit/` | Quality gate / collectors |
| `scripts/release/` | Scanners / smoke / drills |
| `docs/` | Arquitectura, quality-gate, capture, deployment |
| `audit/` | Evidencia de auditorías |
| `security-audit.yaml` | Config security-agents (SAST/DAST) |
| `.github/workflows/` | CI quality + deploy + mobile |
| `secrets/` | Montajes locales (ejemplos; reales gitignored) |
| `.env` | Presente localmente, **gitignored** (no inspeccionar valores) |

## Instrucciones encontradas

| Artefacto | Estado |
|-----------|--------|
| `AGENTS.md` | **No encontrado** en el repo |
| `.cursor/skills/cv-inventory-repo-assistant/SKILL.md` | Presente (guía producto) |
| `README.md` | Presente |
| `PROJECT_CONTEXT.md` | Presente (auditoría 2026-08-27) |
| `REPO_STRUCTURE.md` | Presente |
| `docs/quality-gate.md` | Presente — fuente de comandos de auditoría |
| `CONTRIBUTING*` | No encontrado |
| `.pre-commit-config.yaml` | No encontrado |
| Makefile / Taskfile | No encontrados |

## Componentes confirmados

Ver `05-architecture-review.md` y `04-functional-inventory.md`. Stack alineado con README/PROJECT_CONTEXT: FastAPI, React, Expo, SQL Server, workers, CODE_SCAN + Vision fallback, Gemini/OpenAI/Anthropic.
