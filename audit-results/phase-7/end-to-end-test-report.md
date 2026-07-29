# Phase 7 — End-to-end test report

## Automated (this phase)

```bash
bash scripts/release/run_e2e_release_validation.sh
```

Includes SQL integration (claim, lease fencing, recovery), architecture fencing characterization, and structured process validation errors.

## Live ops E2E (synthetic tenant — manual)

```text
crear inventario → pasillo → imágenes → job → claim → process → fenced persist
→ finalización → promoción → artifacts → métricas
```

Plus cancel / retry / stale recovery / launch failure — use staging tenant only.

Live LLM spend and customer data: **out of automated gate**.
