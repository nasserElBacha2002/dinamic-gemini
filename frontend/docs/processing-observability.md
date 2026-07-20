# Processing observability (Phase 7)

Operational UX for per-image processing lives under the aisle observability workspace tab **Procesamiento** (`?tab=procesamiento`).

## Feature flags

Backend capabilities: `GET /api/v3/config/processing-observability-capabilities`.

Optional Vite fallback: `VITE_PROCESSING_OBSERVABILITY_ENABLED=true` (used only if the capabilities call fails).

## URL filters

Persisted in query params (shareable):

```text
?tab=procesamiento&assetId=...&status=...&strategy=...&resolvedBy=...&search=...&page=...
```

Helpers: `frontend/src/features/processing/utils/processingUrlFilters.ts`.

## Components

| Component | Role |
|-----------|------|
| `ProcessingWorkspace` | Shell: filters, list, drawer |
| `ProcessingJobHeader` / `ProcessingProgressSummary` | Job-level summary |
| `ProcessingAssetFilters` / `ProcessingAssetList` | Filters + desktop table / mobile cards |
| `ProcessingAssetDrawer` | Detail: summary, attempts, evidence, logs, actions |
| `ReprocessDialog` / `InvalidateResultDialog` / `ManualResultForm` | Mutations with confirmation |

Hooks: `useProcessingAssets`, `useProcessingAssetDetail`, `useProcessingEvents`, `useReprocessAsset`, `useInvalidateResult`, `useProcessingObservabilityCapabilities`.

## Rules

- Do not infer status from filenames or raw logs.
- Backend `available_actions` gates buttons; mutations still validate server-side.
- Costly actions require confirmation; concurrency conflicts refresh detail and do not auto-retry.
- Manual result reuses the existing `manual-result` API.
