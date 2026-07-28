# Repository Backend Policy (Phase 2)

## Environments

`RuntimeEnvironment`: test | local | development | staging | preproduction | production | unknown

| Mode | Allowed when |
|------|----------------|
| MEMORY_ONLY | test, local, development only |
| MEMORY_FALLBACK | same; never production/staging/preprod/unknown |
| SQL | required when `requires_sql()` (hosted + unknown) |

## Rules

- Unknown / unset APP_ENV (non-pytest) → `requires_sql=True`.
- Pytest without APP_ENV → TEST (MEMORY_ONLY allowed for unit suites).
- `V3_ALLOW_IN_MEMORY_FALLBACK=true` is **ignored** in forbidden environments.
- SQL probe failure in forbidden env → fail-fast (raise), never silent memory.
- Runtime SQL errors do not switch to memory after SQL mode is selected.

## Observability

- Logs: `event=repository_backend_selected`, `event=repository_backend_policy_violation`
- Health: `repository_backend`, `repository_backend_environment`, `fallback_activated`
