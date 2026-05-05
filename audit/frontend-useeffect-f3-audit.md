# F3 — Inventario `useEffect` (subconjunto inicial)

**Referencia de cierre:** ver **`audit/frontend-f3-closeout.md`** para decisiones, archivos tocados y validación consolidada.

## F3.0 — Métricas del subconjunto auditado

| Métrica | Valor |
|---------|------:|
| Archivos listados | 20 |
| Archivos con `useEffect` | 13 |
| Archivos sin `useEffect` | 7 |
| Total `useEffect` (en archivos que tenían efectos) | 21 |

### Archivos sin `useEffect`

- `frontend/src/pages/AdminAiConfigPage.tsx`
- `frontend/src/pages/InventoriesList.tsx`
- `frontend/src/features/reviewQueue/components/QuickReviewDrawer.tsx`
- `frontend/src/features/analytics/MetricsPage.tsx`
- `frontend/src/features/inventories/hooks/useAisleProcessingFlow.ts`
- `frontend/src/components/CreateAisleDialog.tsx`
- `frontend/src/components/ExecutionLogPanel.tsx`

### Evidencia histórica adicional

Inventario más amplio del frontend en corrida previa: `audit/raw/runs/20260504-171421/frontend-useeffects-audit.md`.
