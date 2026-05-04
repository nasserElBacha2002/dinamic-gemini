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
- src/components/CreateInventoryDialog.tsx
- src/components/imageAssets/ManagedImageAssetsDrawer.tsx
- src/utils/errorTranslations.ts
- src/components/adminAiInspector/InspectorPrimitives.tsx
- src/components/ReferenceImagesDrawer.tsx
- src/utils/positionStatus.ts
- src/utils/jobStatus.ts
- src/components/ui/TraceabilityChip.tsx
- src/components/CreateAisleDialog.tsx
- src/components/ui/types.ts
- src/utils/formatDate.ts
- src/components/AisleObservabilityDialog.tsx
- src/components/ExecutionLogPanel.tsx
- src/components/shell/PageHeader.tsx
- src/utils/aisleStatus.ts
- src/components/ui/ErrorAlert.tsx
- tests/aisleStatus.test.ts
- src/utils/inventoryRowStatus.ts
- src/types/captureSession.ts
- src/types/screenTargets.ts
- src/components/ui/AppSnackbarProvider.tsx
- src/types/statusAlignment.ts
- tests/statusAlignment.test.ts
- src/main.tsx
- src/utils/apiErrors.ts
- tests/ImportSessionDetail.grouping.g4.test.tsx
- tests/AislePositionsPage.test.tsx
- tests/applyStagingChunkResult.test.ts
- src/components/ui/ConfirmDialog.tsx
- tests/useUploadCaptureItems.batch.test.tsx
- src/components/ui/ImageViewer.tsx
- tests/MetricsPage.test.tsx
- src/components/ui/RowActionMenu.tsx
- src/components/ui/StatusBadge.tsx
- tests/ConfirmDialog.test.tsx
- tests/CreateInventoryDialog.visualReferences.test.tsx
- tests/ImportSessionGroupingPanel.g6-preview.test.tsx
- tests/CompareRunsPage.test.tsx
- tests/ReferenceImagesDrawer.test.tsx
- tests/ResultReviewActions.test.tsx
- tests/InventoryDetailPage.test.tsx
- tests/ingestionSessionsR2Corrections.test.tsx
- tests/CompareManyRunsPage.test.tsx
- tests/ReviewQueuePage.test.tsx
- src/features/analytics/hooks.ts
- tests/QuickReviewDrawer.anchorSync.test.tsx
- tests/auth/LoginPage.test.tsx
- tests/auth/authStorage.test.ts
- tests/ImportSessionDetail.grouping.test.tsx
- src/features/auth/store.ts
- tests/QuickReviewDrawer.test.tsx
- tests/jobStatus.test.ts
- tests/PositionDetailPage.test.tsx
- tests/processAisleMenuState.test.ts
- tests/api/evidenceImageLoad.test.tsx
- src/features/auth/types.ts
- src/features/auth/AuthProvider.tsx
- src/features/auth/storage.ts
- src/features/auth/api.ts
- src/features/auth/LoginPage.tsx
- src/features/analytics/MetricsPage.tsx
- src/features/inventories/hooks/useAisleAssetUploadFlow.ts
- src/features/ingestionSessions/components/ImportSessionDetail.tsx
- src/features/ingestionSessions/components/ImportSessionGroupingPanel.tsx
- src/features/ingestionSessions/pages/IngestionSessionsPage.tsx
- src/features/ingestionSessions/components/ImportSessionUpload.tsx
- src/features/inventories/hooks/useAisleProcessingFlow.ts
- src/features/ingestionSessions/pages/IngestionSessionDetailPage.tsx
- src/features/results/utils/reviewStatusDisplay.ts
- src/features/inventories/adapters/processAisleMenuState.ts
- src/features/reviewQueue/components/QuickReviewDrawer.tsx
- src/features/ingestionSessions/hooks/useUploadCaptureItems.ts
- src/features/results/hooks/useEvidenceImageLoad.ts
- src/features/ingestionSessions/api/captureSessionsApi.ts
- src/features/inventories/components/InventoryReferenceImagesModule.tsx
- src/features/results/hooks/useResultSummaries.ts
- src/features/results/components/ResultsTable.tsx
- src/features/reviewQueue/components/ReviewQueueTable.tsx
- src/features/results/components/detail/ResultEvidenceViewer.tsx
- src/features/inventories/adapters/referenceUsageViewModel.ts
- src/features/inventories/components/AisleProcessingDialog.tsx
- src/features/inventories/components/AisleSourceAssetsManageModule.tsx
- src/features/results/components/detail/ResultReviewActions.tsx
- src/features/inventories/components/InventoryDetailHeader.tsx
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
