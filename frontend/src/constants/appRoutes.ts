/**
 * SPA routes for React Router and ``navigate`` / ``<Link>`` targets.
 * Must stay aligned with ``App.tsx`` ``<Route path=...>`` definitions.
 */

export const ROUTE_LOGIN = '/login';
export const ROUTE_HOME = '/';
export const ROUTE_REVIEW_QUEUE = '/review-queue';
export const ROUTE_METRICS = '/metrics';
export const ROUTE_ADMIN_AI_CONFIG = '/admin/ai-config';
export const ROUTE_INGESTION_SESSIONS = '/ingestion-sessions';

/** URL segment for inventory-scoped paths (leading slash added in builders). */
export const ROUTE_SEGMENT_INVENTORIES = 'inventories';

/** Nested ``Route path`` strings (relative to parent ``path="/"``). */
export const ROUTE_PATH = {
  inventories: 'inventories',
  reviewQueue: 'review-queue',
  metrics: 'metrics',
  ingestionSessions: 'ingestion-sessions',
  adminAiConfig: 'admin/ai-config',
  dashboard: 'dashboard',
  settings: 'settings',
  inventoryDetail: 'inventories/:inventoryId',
  aislePositions: 'inventories/:inventoryId/aisles/:aisleId/positions',
  analyticsCompare: 'inventories/:inventoryId/analytics/compare',
  analyticsCompareMany: 'inventories/:inventoryId/analytics/compare-many',
  legacyAisleCompare: 'inventories/:inventoryId/aisles/:aisleId/compare',
  positionDetail: 'inventories/:inventoryId/aisles/:aisleId/positions/:positionId',
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
  ingestionSessionDetail: `/ingestion-sessions/:sessionId`,
} as const;

export function pathToInventory(inventoryId: string): string {
  return `${ROUTE_INVENTORIES_ROOT}/${inventoryId}`;
}

export function pathToInventoryAnalyticsCompare(inventoryId: string): string {
  return `${ROUTE_INVENTORIES_ROOT}/${inventoryId}/analytics/compare`;
}

export function pathToInventoryAnalyticsCompareMany(inventoryId: string): string {
  return `${ROUTE_INVENTORIES_ROOT}/${inventoryId}/analytics/compare-many`;
}

export function pathToAislePositions(inventoryId: string, aisleId: string): string {
  return `${ROUTE_INVENTORIES_ROOT}/${inventoryId}/aisles/${aisleId}/positions`;
}

export function pathToIngestionSessionDetail(sessionId: string, inventoryId: string): string {
  const params = new URLSearchParams({ inventoryId });
  return `${ROUTE_INGESTION_SESSIONS}/${encodeURIComponent(sessionId)}?${params.toString()}`;
}
