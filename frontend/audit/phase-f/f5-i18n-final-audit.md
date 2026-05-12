# F5 — i18n final audit (Phase F closure)

**Date:** 2026-05-11  
**Default UI locale:** Spanish (`frontend/src/i18n/locales/es/translation.json`).  
**Reference locale:** `en/translation.json` exists for parity checks only; product expectation is Spanish for operators.

---

## Automated check

```bash
npm run check:i18n
```

**Result:** Exit code **0** — all keys used by static extraction exist in `es`.  
**Warnings:** Suspicious English-looking *values* inside `es` for a few keys (e.g. `aisle_source_assets.empty_message` “Empty message”, KPI keys) — **pre-existing debt**, not introduced by Phase F supplier tabs.  
**Notes:** Many keys unused in static scan (dynamic keys / legacy aisle advanced prompt) — documented, not blocking.

---

## Targeted searches (manual / rg)

Se buscó en `frontend/src` (excluyendo comentarios de tipos en parsers):

| Pattern | Intent | Finding |
|---------|--------|---------|
| `Process`, `Prompt profile`, `standard scan`, `anti-hallucination` | Inglés visible | No matches in operator UI strings under Phase F paths; legacy keys remain in JSON unused by process dialog |
| `primary_evidence` / `visual_reference` | Raw roles in UI | Used in **TypeScript** for branching; user-facing labels use `t('execution_log.primary_evidence')`, etc. |
| `Opciones avanzadas` / `Perfil base del prompt` | Process regression | Keys exist; **not** referenced by current process dialog path (confirmed by tests) |

---

## Status / traceability copy (spec checklist)

Los textos operativos para trazabilidad y adjuntos están mayormente centralizados en `execution_log.*` y strings de cliente/proveedor en `clients.*` / `inventory.*`.  
Mapeos finos (`resolved` → “Resuelto”, etc.) deben vivir en utilidades de presentación o en `translation.json`; cualquier gap puntual se clasifica como **NON_BLOCKING_DEBT** en el documento de cierre si no bloquea operación.

---

## English in tests

Los tests de `InventoryDetailPage` usan regex bilingüe solo donde el menú aún expone claves técnicas en ciertos estados (p. ej. `upload_need_image`) — **intencional** para estabilidad del test, no UI final.

---

## Conclusion

**Spanish operator surfaces targeted by Phase F:** coherent with i18n keys; **no blocking missing keys** in `es`.  
Residual English **values** inside `es` JSON and incomplete `en` parity are tracked as **follow-up i18n hygiene** (Phase G or dedicated PR), not Phase F blockers.
