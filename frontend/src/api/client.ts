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
  deleteInventoryVisualReference,
  exportInventoryResultsCsv,
  fetchInventoryVisualReferenceFile,
  getInventories,
  getInventory,
  getInventoryMetrics,
  getInventoryVisualReferences,
  replaceInventoryVisualReference,
  uploadInventoryVisualReferences,
} from './inventoriesApi';
export type { AislesListQuery } from './aislesApi';
export {
  createAisle,
  exportAisleResultsCsv,
  getAisles,
  getAisleMergeResults,
  runAisleMerge,
  startAisleProcessing,
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
  getExecutionLog,
  getExecutionLogTxtUrl,
  listAisleJobs,
  promoteAisleOperationalJob,
  retryAisleJob,
} from './jobsApi';
export type { EvidenceImageLoadSpec, FetchEvidenceImageResult } from './assetsApi';
export {
  deleteAisleSourceAsset,
  fetchEvidenceImageDisplay,
  getReferenceImageDisplayUrl,
  getReferenceImageFileUrl,
  listAisleAssets,
  uploadAisleAssets,
} from './assetsApi';
export type { AnalyticsQueryParams } from './analyticsApi';
export {
  downloadAisleBenchmarkExportCsv,
  getAisleBenchmarkCompare,
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
export type { ReviewQueueListQuery } from './reviewQueueApi';
export {
  buildReviewQueueQueryString,
  getPositionDetail,
  getReviewQueuePositions,
  submitReviewAction,
} from './reviewQueueApi';
export type { ClientsListQuery } from './clientsApi';
export { createClient, getClient, listClients } from './clientsApi';
export type { ClientSuppliersListQuery } from './clientSuppliersApi';
export {
  createClientSupplier,
  getClientSupplier,
  listClientSuppliers,
} from './clientSuppliersApi';

