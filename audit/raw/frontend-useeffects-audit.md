# Auditoría frontend - useEffect

## Resumen

- Cantidad aproximada de usos de `useEffect`: 64
- Cantidad aproximada de archivos con `useEffect`: 41

## Archivos detectados

- src/pages/ClientsList.tsx
- src/pages/PositionDetailPage.tsx
- src/pages/AislePositionsPage.tsx
- src/pages/AdminStorageMaintenancePage.tsx
- src/features/analytics/compare/useCompareManyAppliedState.ts
- src/features/analytics/compare/CompareManyRunsWorkspace.tsx
- src/hooks/useBeforeUnloadWarning.ts
- src/hooks/useDebouncedSearchInput.ts
- src/features/inventories/hooks/useAisleProcessingFlow.ts
- src/features/aisle-code-scans/components/CodeScanDetectionsTable.tsx
- src/components/CreateInventoryDialog.tsx
- src/features/inventories/components/EditInventoryNameDialog.tsx
- src/components/imageAssets/ManagedImageAssetsDrawer.tsx
- src/components/JobObservabilityDiagnosticsPanel.tsx
- src/features/aisle-code-scans/components/CodeScanSummaryTable.tsx
- src/features/inventories/components/EditAisleCodeDialog.tsx
- src/features/inventories/components/InventoryAislesSection.tsx
- src/components/AisleObservabilityWorkspace.tsx
- src/features/processing/ReprocessDialog.tsx
- src/components/CreateAisleDialog.tsx
- tests/useAisleProcessingFlow.identification.test.tsx
- src/components/ui/DataTable.tsx
- src/components/ui/ImageViewer.tsx
- src/features/processing/InvalidateResultDialog.tsx
- src/features/analytics-dashboard/AnalyticsDashboardPage.tsx
- src/features/auth/AuthProvider.tsx
- src/features/processing/ManualResultForm.tsx
- src/features/processing/ProcessingWorkspace.tsx
- src/layout/AppShell.tsx
- src/features/processing/ProcessingAssetDrawer.tsx
- src/features/clients/components/InventoryBarcode.tsx
- src/features/ingestionSessions/components/ImportSessionGroupingPanel.tsx
- src/features/clients/components/SupplierExtractionProfilesModule.tsx
- src/features/clients/components/ReferenceAnnotationCanvas.tsx
- src/features/clients/components/SupplierReferenceAnnotationEditorDialog.tsx
- src/features/results/hooks/useEvidenceImageLoad.ts
- src/features/clients/components/SupplierPromptConfigsModule.tsx
- src/features/reviewQueue/components/QuickReviewDrawer.tsx
- src/features/results/components/detail/ResultEvidenceViewer.tsx
- src/features/results/components/imageCoverage/ManualImageResultDrawer.tsx
- src/features/results/components/detail/ResultEvidencePanel.tsx

## Patrones a revisar

- useEffect sin dependency array (aprox): 64
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
