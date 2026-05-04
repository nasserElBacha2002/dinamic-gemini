# Auditoría frontend - useEffect

## Resumen

- Cantidad aproximada de usos de `useEffect`: 46
- Cantidad aproximada de archivos con `useEffect`: 20

## Archivos detectados

- src/pages/analytics/CompareManyRunsPage.tsx
- src/pages/analytics/CompareRunsPage.tsx
- src/pages/AdminAiConfigPage.tsx
- src/pages/PositionDetailPage.tsx
- src/pages/InventoriesList.tsx
- src/pages/AislePositionsPage.tsx
- src/pages/ReviewQueuePage.tsx
- src/components/CreateInventoryDialog.tsx
- src/components/imageAssets/ManagedImageAssetsDrawer.tsx
- src/hooks/useDebouncedValue.ts
- src/components/CreateAisleDialog.tsx
- src/components/ui/ImageViewer.tsx
- src/hooks/useDebouncedSearchInput.ts
- src/components/ExecutionLogPanel.tsx
- src/features/auth/AuthProvider.tsx
- src/features/reviewQueue/components/QuickReviewDrawer.tsx
- src/features/analytics/MetricsPage.tsx
- src/features/inventories/hooks/useAisleProcessingFlow.ts
- src/features/results/hooks/useEvidenceImageLoad.ts
- src/features/results/components/detail/ResultReviewActions.tsx

## Patrones a revisar

- useEffect sin dependency array (aprox): 46
- useEffect con dependency array vacio [] (aprox): 0
- useEffect con fetch (aprox): 0
- useEffect con setInterval/setTimeout (aprox): 0
- useEffect con addEventListener (aprox): 0
- useEffect con console.error (aprox): 0
- useEffect con posible logica de API movible a TanStack Query (aprox): 0

## Recomendaciones futuras

- Revisar useEffect sin dependencias declaradas para evitar efectos no deterministas.
- Evaluar migracion de fetching manual a hooks de TanStack Query donde aplique.
- Confirmar limpieza de listeners y timers en efectos con recursos persistentes.
- Validar manualmente los conteos aproximados; este reporte usa heuristicas por patron de texto.
