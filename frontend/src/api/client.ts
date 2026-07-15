/**
 * v3 API client — inventories and aisles.
 * Base URL is relative so Vite proxy forwards /api to the backend.
 * Protected requests include Authorization: Bearer <token> from auth storage.
 *
 * User-visible fallback copy should use i18n.t keys (see translation.json), not raw English.
 */


export type { InventoriesListQuery } from './inventoriesApi';
export {
  createInventory,
  exportInventoryPackageZip,
  exportInventoryResultsCsv,
  exportInventorySummaryCsv,
  getInventories,
  getInventory,
  getInventoryMetrics,
  updateInventory,
} from './inventoriesApi';
export type { AislesListQuery } from './aislesApi';
export {
  activateAisle,
  createAisle,
  deactivateAisle,
  exportAisleOperationalCsv,
  exportAisleResultsCsv,
  getAisles,
  getAisleMergeResults,
  runAisleMerge,
  startAisleProcessing,
  updateAisle,
} from './aislesApi';
export type { AislePositionsListQuery } from './jobsApi';
export {
  cancelAisleJob,
  downloadAisleExecutionLogTxt,
  downloadExecutionLogTxt,
  getAisleExecutionLog,
  getAisleExecutionLogTxtUrl,
  getAisleJobDetail,
  getAislePositions,
  getPositionDetail,
  getExecutionLog,
  getExecutionLogTxtUrl,
  getJobAuditability,
  getJobAuditabilityPath,
  listAisleJobs,
  promoteAisleOperationalJob,
  retryAisleJob,
  submitReviewAction,
} from './jobsApi';
export type { EvidenceImageLoadSpec, FetchEvidenceImageResult } from './assetsApi';
export {
  aisleAssetsResponseToOutcomes,
  deleteAisleSourceAsset,
  fetchEvidenceImageDisplay,
  getReferenceImageDisplayUrl,
  getReferenceImageFileUrl,
  listAisleAssets,
  uploadAisleAssets,
  uploadAisleAssetsBatch,
} from './assetsApi';
export type { AnalyticsQueryParams } from './analyticsApi';
export {
  downloadAisleBenchmarkExportCsv,
  getAisleBenchmarkCompareMany,
  getAnalyticsAisleIssues,
  getAnalyticsInventoryPerformance,
  getAnalyticsManualInterventions,
  getAnalyticsQualityPatterns,
  getAnalyticsSummary,
  getAnalyticsTrends,
} from './analyticsApi';
export {
  getAdminAiComposedPrompt,
  getAdminAiConfig,
  getProcessingProviderOptions,
} from './adminAiApi';
export { postAdminStorageCleanup } from './adminStorageApi';
export type {
  AdminStorageCleanupRequest,
  AdminStorageCleanupResponse,
} from './adminStorageApi';
export type {
  CodeScanCodeType,
  CodeScanDetection,
  CodeScanDetectionStatus,
  CodeScanRunStatus,
  CodeScanRunSummary,
  CodeScanSummaryItem,
  ListAisleCodeScansResponse,
  RunAisleCodeScanResponse,
  SummarizeAisleCodeScansResponse,
} from './types/codeScans';
export {
  getAisleCodeScanSummary,
  listAisleCodeScans,
  runAisleCodeScan,
} from './codeScansApi';
export type { ClientsListQuery } from './clientsApi';
export { createClient, getClient, listClients } from './clientsApi';
export type { ClientSuppliersListQuery, SupplierPromptConfigsListQuery } from './clientSuppliersApi';
export {
  activateSupplierPromptConfigVersion,
  createSupplierPromptConfigVersion,
  createClientSupplier,
  deleteSupplierReferenceImage,
  fetchSupplierReferenceImageDisplay,
  fetchSupplierReferenceImageFile,
  getActiveSupplierPromptConfig,
  getClientSupplier,
  getSupplierPromptConfigById,
  getSupplierReferenceImageDisplayUrl,
  getSupplierReferenceImageFileUrl,
  listClientSuppliers,
  listSupplierPromptConfigs,
  listSupplierReferenceImages,
  uploadSupplierReferenceImages,
} from './clientSuppliersApi';
export type { ObservabilityMetricsQueryParams } from './observabilityApi';
export { getObservabilityMetrics, getObservabilityMetricsPath } from './observabilityApi';

