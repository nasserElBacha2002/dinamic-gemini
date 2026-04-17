/**
 * v3 REST URL path prefixes (after ``VITE_API_BASE_URL``).
 * Must stay aligned with backend ``APIRouter`` prefixes under ``/api/v3``.
 */

export const V3_API_PREFIX = '/api/v3';

export const V3_INVENTORIES_BASE = `${V3_API_PREFIX}/inventories`;
export const V3_ADMIN_BASE = `${V3_API_PREFIX}/admin`;
export const V3_ANALYTICS_BASE = `${V3_API_PREFIX}/analytics`;
export const V3_REVIEW_QUEUE_BASE = `${V3_API_PREFIX}/review-queue`;
