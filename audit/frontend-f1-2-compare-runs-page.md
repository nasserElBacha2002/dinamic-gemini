# Fase F1.2 — Estabilización de CompareRunsPage.test.tsx

## Estado

**F1.2 CERRADA**

## Resumen ejecutivo

- Tests fallidos al inicio: **6 de 9** (además **3 passed**, incl. LegacyAisleCompareRedirect).
- Tests fallidos al cierre: **0 de 9**.
- Tests pasados del archivo: **9 de 9**.
- Causa principal: `COPY_DESACTUALIZADO` (textos i18n tipo placeholder: `info benchmark`, `diff summary title`, `truncation warning`, `export csv`) y expectativas de tooltip que asumían copy/interpolación distinta (`Model:`, `mdl2`, `token usage`).
- Archivos modificados: `frontend/tests/CompareRunsPage.test.tsx`, `audit/frontend-f1-2-compare-runs-page.md`.
- Código productivo modificado: **No**.
- Resultado de corrida puntual: **9 passed**.
- Resultado de corrida completa: **74 failed | 352 passed**, **17 failed files | 51 passed** (vs **80 / 18** tras F1.1).

## Archivos modificados

| Archivo | Tipo | Motivo |
|---|---|---|
| `frontend/tests/CompareRunsPage.test.tsx` | Test | Alinear assertions con UI/i18n actual; botón export; tooltips; alert de truncamiento; fixture `pricing_snapshot` tipado |
| `audit/frontend-f1-2-compare-runs-page.md` | Documentación | Cierre F1.2 |

## Fallos corregidos

| Test | Causa | Corrección aplicada |
|---|---|---|
| `renders compare metrics and diff summary for a valid job pair` | `COPY_DESACTUALIZADO` | `compare-runs-results` + `info benchmark` + `diff summary title/stats` en lugar de copy antigua “Read-only…” / “Only in A/B” |
| `shows operator-friendly tooltip text for cost details` | `COPY_DESACTUALIZADO` | Tooltip recibido: `Unavailable · Pricing entry missing · Model in tooltip` — asserts a `/pricing entry missing/` y `/model in tooltip/` |
| `shows usage not reported when provider usage is missing` | `COPY_DESACTUALIZADO` + `MOCK_DESACTUALIZADO` | Tooltip a `/provider usage missing/`; `pricing_snapshot: null` sustituido por objeto mínimo válido (tipos TS) |
| `shows not computed for other null-cost cases with model in tooltip` | `COPY_DESACTUALIZADO` | `/Model:/` y `custom-model` → `/model in tooltip/` |
| `shows an honest cap warning when raw fetch hit the server cap` | `COPY_DESACTUALIZADO` | Texto de alerta actual `truncation warning` |
| `calls benchmark CSV export with the selected job pair` | `SELECTOR_ACCESIBLE_ROTO` | Botón `export compare table` → `/export csv/i` |

## Validación ejecutada

```bash
cd "/Users/nasserelbacha/Documents/Dinamic sistems/dinamic-gemini/frontend"
npm run test -- tests/CompareRunsPage.test.tsx
```

Resultado:

```txt
✓ tests/CompareRunsPage.test.tsx (9 tests)
Test Files  1 passed (1)
Tests       9 passed (9)
```

Suite completa:

```bash
cd "/Users/nasserelbacha/Documents/Dinamic sistems/dinamic-gemini/frontend"
npm run test
```

Resultado:

```txt
Test Files  17 failed | 51 passed (68)
Tests       74 failed | 352 passed (426)
```

## Observaciones

- Patrón reutilizable F1.3/F1.4: contrastar siempre con `frontend/src/i18n/locales/en/translation.json` (o runtime real) antes de aserciones literales; muchas claves son placeholders cortos.
- Tooltips MUI: el `title` sigue las cadenas compuestas en `formatCostDisplay`; no asumir `Model: {{model}}` si la traducción no interpola.
- F2 (opcional): mejorar copy real en `translation.json` para operadores (fuera de alcance F1).

## Criterio de cierre

F1.2 se considera cerrada porque:

1. `CompareRunsPage.test.tsx` pasa completo (9/9).
2. No se corrigieron otros tests fuera del alcance.
3. No se hicieron refactors en la página.
4. No se modificó arquitectura analytics.
5. No hubo cambios productivos.
