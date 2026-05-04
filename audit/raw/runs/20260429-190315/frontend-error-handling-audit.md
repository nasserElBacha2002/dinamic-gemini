# Auditoría frontend - manejo de errores

## Resumen

- Archivos con patrones de manejo de errores detectados (aprox): 100
- Bloques try detectados (aprox): 59
- Bloques catch detectados (aprox): 25

## Archivos detectados

- src/pages/analytics/CompareManyRunsPage.tsx
- src/pages/analytics/CompareRunsPage.tsx
- src/pages/InventoryDetail.tsx
- src/pages/AdminAiConfigPage.tsx
- src/pages/InventoriesList.tsx
- src/pages/AislePositionsPage.tsx
- src/pages/ReviewQueuePage.tsx
- src/i18n/index.ts
- src/theme.ts
- src/dev/cacheMutationGuardrails.ts
- src/dev/cacheMutationObservability.ts
- src/api/client.ts
- src/api/types/responses.ts
- src/api/types/index.ts
- src/api/types/errors.ts
- src/utils/errorTranslations.ts
- src/utils/positionStatus.ts
- src/main.tsx
- src/utils/jobStatus.ts
- src/types/statusAlignment.ts
- src/components/CreateInventoryDialog.tsx
- src/utils/apiErrors.ts
- src/utils/formatDate.ts
- src/types/screenTargets.ts
- src/types/captureSession.ts
- src/utils/aisleStatus.ts
- src/features/analytics/MetricsPage.tsx
- tests/AislePositionsPage.test.tsx
- src/utils/inventoryRowStatus.ts
- src/features/analytics/hooks.ts
- tests/MetricsPage.test.tsx
- tests/ImportSessionDetail.grouping.g4.test.tsx
- tests/CreateInventoryDialog.visualReferences.test.tsx
- tests/useUploadCaptureItems.batch.test.tsx
- src/features/auth/store.ts
- src/components/shell/PageHeader.tsx
- src/features/inventories/hooks/useAisleAssetUploadFlow.ts
- src/components/imageAssets/ManagedImageAssetsDrawer.tsx
- tests/ResultReviewActions.test.tsx
- tests/api/evidenceImageLoad.test.tsx
- tests/ImportSessionDetail.grouping.test.tsx
- src/features/auth/AuthProvider.tsx
- src/features/inventories/hooks/useAisleProcessingFlow.ts
- src/features/ingestionSessions/pages/IngestionSessionsPage.tsx
- src/features/reviewQueue/components/QuickReviewDrawer.tsx
- tests/ReferenceImagesDrawer.test.tsx
- src/components/AisleObservabilityDialog.tsx
- tests/QuickReviewDrawer.anchorSync.test.tsx
- src/features/inventories/components/InventoryReferenceImagesModule.tsx
- tests/ingestionSessionsR2Corrections.test.tsx
- src/components/CreateAisleDialog.tsx
- src/features/ingestionSessions/pages/IngestionSessionDetailPage.tsx
- tests/aisleStatus.test.ts
- src/features/auth/types.ts
- tests/PositionDetailPage.test.tsx
- tests/ReviewQueuePage.test.tsx
- tests/jobStatus.test.ts
- tests/statusAlignment.test.ts
- tests/processAisleMenuState.test.ts
- src/features/auth/api.ts
- tests/InventoryDetailPage.test.tsx
- src/components/ReferenceImagesDrawer.tsx
- src/features/reviewQueue/components/ReviewQueueTable.tsx
- src/features/inventories/components/AisleSourceAssetsManageModule.tsx
- src/features/ingestionSessions/api/captureSessionsApi.ts
- tests/QuickReviewDrawer.test.tsx
- src/features/inventories/components/AisleProcessingDialog.tsx
- tests/auth/LoginPage.test.tsx
- src/features/auth/storage.ts
- src/components/ui/StatusBadge.tsx
- tests/auth/authStorage.test.ts
- src/features/inventories/components/InventoryDetailHeader.tsx
- src/components/adminAiInspector/InspectorPrimitives.tsx
- src/components/ui/types.ts
- src/components/ui/TraceabilityChip.tsx
- src/features/auth/LoginPage.tsx
- src/features/ingestionSessions/hooks/useUploadCaptureItems.ts
- src/components/ui/ErrorAlert.tsx
- tests/applyStagingChunkResult.test.ts
- src/features/inventories/adapters/processAisleMenuState.ts
- src/components/ui/RowActionMenu.tsx
- src/features/ingestionSessions/components/ImportSessionGroupingPanel.tsx
- src/components/ui/AppSnackbarProvider.tsx
- tests/CompareRunsPage.test.tsx
- src/features/ingestionSessions/components/ImportSessionDetail.tsx
- tests/ImportSessionGroupingPanel.g6-preview.test.tsx
- src/features/results/hooks/useEvidenceImageLoad.ts
- src/features/inventories/adapters/referenceUsageViewModel.ts
- src/features/results/hooks/useResultSummaries.ts
- tests/ConfirmDialog.test.tsx
- src/features/ingestionSessions/components/ImportSessionUpload.tsx
- src/features/results/utils/reviewStatusDisplay.ts
- src/features/results/components/ResultsTable.tsx
- src/components/ui/ImageViewer.tsx
- src/components/ExecutionLogPanel.tsx
- tests/CompareManyRunsPage.test.tsx
- src/components/ui/ConfirmDialog.tsx
- src/features/results/components/detail/ResultEvidenceViewer.tsx
- src/features/results/components/detail/ResultReviewActions.tsx
- src/features/results/components/detail/ResultEvidencePanel.tsx

## Patrones encontrados

- catch vacio (aprox): 0
- catch con solo console.error (aprox): 0
- uso de onError (aprox): 61
- uso de isError (aprox): 117
- throw new Error (aprox): 5

## Riesgos a revisar

- Bloques catch que no escalan ni muestran feedback al usuario.
- Errores solo logueados en consola sin estrategia de UX de error.
- Flujos de query/mutation sin manejo explicito de estados de error.
- Mensajes tecnicos potencialmente expuestos de forma directa en UI.

## Recomendaciones futuras

- Definir un patron comun de error UI (toast/alerta/estado en pantalla).
- Estandarizar manejo de errores en hooks de datos con TanStack Query.
- Revisar manualmente resultados: el analisis actual es estatico por patrones de texto.
