/**
 * SPA routes for React Router and ``navigate`` / ``<Link>`` targets.
 * Must stay aligned with ``App.tsx`` ``<Route path=...>`` definitions.
 */

import { ANALYTICS_TAB_QUERY_KEY, analyticsTabToUrl } from './analyticsTabs';
import type { AnalyticsDashboardTab } from '../features/analytics-dashboard/types';

export const ROUTE_LOGIN = '/login';
export const ROUTE_HOME = '/';
export const ROUTE_METRICS = '/metrics';
export const ROUTE_ANALITICA = '/analitica';
export const ROUTE_OBSERVABILIDAD = '/observabilidad';

/** Legacy analytics routes — redirect into unified Analítica tabs. */
export const LEGACY_METRICS_ROUTE = ROUTE_METRICS;
export const LEGACY_OBSERVABILITY_ROUTE = ROUTE_OBSERVABILIDAD;
export const ROUTE_CLIENTS = '/clientes';
export const ROUTE_ADMIN_AI_CONFIG = '/admin/ai-config';
export const ROUTE_ADMIN_STORAGE_MAINTENANCE = '/admin/storage-maintenance';
export const ROUTE_INGESTION_SESSIONS = '/ingestion-sessions';

/** URL segment for inventory-scoped paths (leading slash added in builders). */
export const ROUTE_SEGMENT_INVENTORIES = 'inventories';

/** Nested ``Route path`` strings (relative to parent ``path="/"``). */
export const ROUTE_PATH = {
  inventories: 'inventories',
  reviewQueue: 'review-queue',
  metrics: 'metrics',
  analitica: 'analitica',
  observabilidad: 'observabilidad',
  clients: 'clientes',
  clientDetail: 'clientes/:clientId',
  /** Detalle de proveedor del cliente (Phase F). */
  clientSupplierDetail: 'clientes/:clientId/proveedores/:supplierId',
  ingestionSessions: 'ingestion-sessions',
  adminAiConfig: 'admin/ai-config',
  adminStorageMaintenance: 'admin/storage-maintenance',
  dashboard: 'dashboard',
  settings: 'settings',
  inventoryDetail: 'inventories/:inventoryId',
  aislePositions: 'inventories/:inventoryId/aisles/:aisleId/positions',
  analyticsCompare: 'inventories/:inventoryId/analytics/compare',
  analyticsCompareMany: 'inventories/:inventoryId/analytics/compare-many',
  legacyAisleCompare: 'inventories/:inventoryId/aisles/:aisleId/compare',
  positionDetail: 'inventories/:inventoryId/aisles/:aisleId/positions/:positionId',
  aisleObservability: 'inventories/:inventoryId/aisles/:aisleId/observability',
  ingestionSessionDetail: 'ingestion-sessions/:sessionId',
} as const;

/** Full path prefix for inventory list/detail area (``/inventories``). */
export const ROUTE_INVENTORIES_ROOT = `/${ROUTE_SEGMENT_INVENTORIES}`;

/** Absolute patterns for ``matchPath`` (must match ``Route`` URL shapes). */
export const ROUTE_MATCH = {
  inventoryDetail: `${ROUTE_INVENTORIES_ROOT}/:inventoryId`,
  aislePositions: `${ROUTE_INVENTORIES_ROOT}/:inventoryId/aisles/:aisleId/positions`,
  analyticsCompare: `${ROUTE_INVENTORIES_ROOT}/:inventoryId/analytics/compare`,
  analyticsCompareMany: `${ROUTE_INVENTORIES_ROOT}/:inventoryId/analytics/compare-many`,
  legacyAisleCompare: `${ROUTE_INVENTORIES_ROOT}/:inventoryId/aisles/:aisleId/compare`,
  positionDetail: `${ROUTE_INVENTORIES_ROOT}/:inventoryId/aisles/:aisleId/positions/:positionId`,
  aisleObservability: `${ROUTE_INVENTORIES_ROOT}/:inventoryId/aisles/:aisleId/observability`,
  ingestionSessionDetail: `/ingestion-sessions/:sessionId`,
  clientDetail: '/clientes/:clientId',
  clientSupplierDetail: '/clientes/:clientId/proveedores/:supplierId',
} as const;

export function pathToInventory(inventoryId: string): string {
  return `${ROUTE_INVENTORIES_ROOT}/${inventoryId}`;
}

/**
 * Canonical analytics comparison URL (compare-many). Kept for backward-compatible call sites.
 * The legacy path `/analytics/compare` still exists in the router and redirects here.
 */
export function pathToInventoryAnalyticsCompare(inventoryId: string): string {
  return pathToInventoryAnalyticsCompareMany(inventoryId);
}

export function pathToInventoryAnalyticsCompareMany(
  inventoryId: string,
  options?: { aisleId?: string; jobIds?: string[]; baseline?: string }
): string {
  const base = `${ROUTE_INVENTORIES_ROOT}/${inventoryId}/analytics/compare-many`;
  const params = new URLSearchParams();
  const aisleId = options?.aisleId?.trim();
  if (aisleId) params.set('aisleId', aisleId);
  const jobIds = (options?.jobIds ?? []).map((id) => id.trim()).filter(Boolean);
  if (jobIds.length > 0) params.set('jobIds', jobIds.join(','));
  const baseline = options?.baseline?.trim();
  if (baseline) params.set('baseline', baseline);
  const query = params.toString();
  return query ? `${base}?${query}` : base;
}

export function pathToAislePositions(inventoryId: string, aisleId: string): string {
  return `${ROUTE_INVENTORIES_ROOT}/${inventoryId}/aisles/${aisleId}/positions`;
}

export function pathToAisleObservability(
  inventoryId: string,
  aisleId: string,
  jobId?: string | null
): string {
  const base = `${ROUTE_INVENTORIES_ROOT}/${inventoryId}/aisles/${aisleId}/observability`;
  if (jobId != null && String(jobId).trim() !== '') {
    return `${base}?jobId=${encodeURIComponent(String(jobId).trim())}`;
  }
  return base;
}

export function pathToIngestionSessionDetail(sessionId: string, inventoryId: string): string {
  const params = new URLSearchParams({ inventoryId });
  return `${ROUTE_INGESTION_SESSIONS}/${encodeURIComponent(sessionId)}?${params.toString()}`;
}

export function pathToClient(clientId: string): string {
  return `${ROUTE_CLIENTS}/${encodeURIComponent(clientId)}`;
}

export function pathToClientSupplier(clientId: string, supplierId: string): string {
  return `${ROUTE_CLIENTS}/${encodeURIComponent(clientId)}/proveedores/${encodeURIComponent(supplierId)}`;
}

export function pathToAnalytics(tab?: AnalyticsDashboardTab): string {
  const urlTab = analyticsTabToUrl(tab ?? 'summary');
  return `${ROUTE_ANALITICA}?${ANALYTICS_TAB_QUERY_KEY}=${urlTab}`;
}
