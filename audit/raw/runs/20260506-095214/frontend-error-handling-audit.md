# Auditoría frontend - manejo de errores

## Resumen

- Archivos con patrones de manejo de errores detectados (aprox): 107
- Bloques try detectados (aprox): 65
- Bloques catch detectados (aprox): 31

## Archivos detectados

- src/pages/analytics/CompareManyRunsPage.tsx
- src/pages/analytics/compareManyRunsDraft.ts
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
- src/components/ReferenceImagesDrawer.tsx
- src/components/adminAiInspector/InspectorPrimitives.tsx
- src/features/analytics/hooks.ts
- src/components/shell/PageHeader.tsx
- src/types/statusAlignment.ts
- src/main.tsx
- src/components/ExecutionLogPanel.tsx
- src/types/captureSession.ts
- src/components/CreateAisleDialog.tsx
- src/components/AisleObservabilityDialog.tsx
- src/types/screenTargets.ts
- src/features/analytics/MetricsPage.tsx
- tests/CompareRunsPage.test.tsx
- src/utils/errorTranslations.ts
- tests/ConfirmDialog.test.tsx
- src/utils/positionStatus.ts
- src/features/imageAssets/hooks/useInventoryReferencePreview.ts
- tests/ImportSessionGroupingPanel.g6-preview.test.tsx
- tests/AislePositionsPage.test.tsx
- src/utils/jobStatus.ts
- src/features/executionLogs/hooks/useExecutionLogDownloads.ts
- tests/MetricsPage.test.tsx
- src/features/results/utils/reviewStatusDisplay.ts
- src/features/inventories/hooks/useAisleAssetUploadFlow.ts
- tests/CompareManyRunsPage.test.tsx
- src/utils/formatDate.ts
- tests/aisleStatus.test.ts
- src/components/ui/TraceabilityChip.tsx
- src/features/inventories/hooks/useCreateInventoryFlow.ts
- src/features/results/components/detail/ResultEvidenceViewer.tsx
- src/features/auth/store.ts
- tests/statusAlignment.test.ts
- src/utils/aisleStatus.ts
- src/features/inventories/hooks/useAisleProcessingFlow.ts
- src/features/auth/AuthProvider.tsx
- src/features/results/components/detail/ResultReviewActions.tsx
- tests/ImportSessionDetail.grouping.g4.test.tsx
- src/features/results/hooks/useEvidenceImageLoad.ts
- src/features/reviewQueue/components/QuickReviewDrawer.tsx
- src/features/inventories/hooks/useCreateAisleAction.ts
- src/utils/inventoryRowStatus.ts
- tests/useUploadCaptureItems.batch.test.tsx
- src/features/auth/types.ts
- src/features/inventories/components/InventoryReferenceImagesModule.tsx
- src/features/results/hooks/useResultSummaries.ts
- src/features/auth/api.ts
- src/features/inventories/components/AisleSourceAssetsManageModule.tsx
- src/features/reviewQueue/components/ReviewQueueTable.tsx
- src/features/auth/storage.ts
- src/components/ui/ErrorAlert.tsx
- tests/ReferenceImagesDrawer.test.tsx
- src/features/inventories/components/InventoryDetailHeader.tsx
- src/features/inventories/components/AisleProcessingDialog.tsx
- src/utils/apiErrors.ts
- tests/ingestionSessionsR2Corrections.test.tsx
- src/features/auth/LoginPage.tsx
- tests/ReviewQueuePage.test.tsx
- src/components/ui/useAppSnackbar.ts
- src/features/results/components/detail/ResultEvidencePanel.tsx
- src/features/inventories/adapters/processAisleMenuState.ts
- tests/InventoryDetailPage.test.tsx
- tests/CreateInventoryDialog.visualReferences.test.tsx
- src/features/results/components/ResultsTable.tsx
- src/features/ingestionSessions/pages/IngestionSessionsPage.tsx
- tests/ResultReviewActions.test.tsx
- tests/auth/LoginPage.test.tsx
- src/features/ingestionSessions/pages/IngestionSessionDetailPage.tsx
- src/components/ui/RowActionMenu.tsx
- tests/auth/authStorage.test.ts
- src/features/inventories/adapters/referenceUsageViewModel.ts
- tests/QuickReviewDrawer.anchorSync.test.tsx
- src/features/ingestionSessions/api/captureSessionsApi.ts
- src/components/ui/StatusBadge.tsx
- src/components/ui/appSnackbarContext.ts
- tests/jobStatus.test.ts
- src/components/ui/ImageViewer.tsx
- tests/applyStagingChunkResult.test.ts
- src/components/ui/types.ts
- src/components/ui/ConfirmDialog.tsx
- src/features/ingestionSessions/components/ImportSessionGroupingPanel.tsx
- src/features/ingestionSessions/hooks/useUploadCaptureItems.ts
- src/components/ui/AppSnackbarProvider.tsx
- tests/processAisleMenuState.test.ts
- tests/QuickReviewDrawer.test.tsx
- tests/PositionDetailPage.test.tsx
- tests/ImportSessionDetail.grouping.test.tsx
- tests/api/evidenceImageLoad.test.tsx
- src/features/ingestionSessions/components/ImportSessionDetail.tsx
- src/features/ingestionSessions/components/ImportSessionUpload.tsx

## Patrones encontrados

- catch vacio (aprox): 0
- catch con solo console.error (aprox): 0
- uso de onError (aprox): 58
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
