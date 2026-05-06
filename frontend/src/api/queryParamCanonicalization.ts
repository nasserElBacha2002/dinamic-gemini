import type { InventoriesListQuery } from './inventoriesApi';
import type { AislePositionsListQuery } from './jobsApi';
import type { ReviewQueueListQuery } from './reviewQueueApi';
import { DEFAULT_LIST_PAGE_SIZE } from '../constants/dataTable';

type QueryKeyPrimitive = string | number;

export type QueryKeyParams = Record<string, QueryKeyPrimitive>;

function normalizeText(value: unknown, options?: { lowercase?: boolean }): string | undefined {
  if (value == null) return undefined;
  const trimmed = String(value).trim();
  if (trimmed === '') return undefined;
  return options?.lowercase ? trimmed.toLowerCase() : trimmed;
}

/**
 * Integer pagination / page size: positive finite integers only, truncated toward zero.
 * Invalid values (NaN, Infinity, < 1, non-number) are omitted from canonical payloads.
 * Same rule applies to query keys and request bodies so cache identity matches the wire.
 */
export function normalizePositiveInt(value: unknown): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 1) return undefined;
  return Math.trunc(value);
}

/** Confidence bounds: finite numbers only (excludes NaN and Infinity). */
function normalizeFiniteConfidence(value: unknown): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value)) return undefined;
  return value;
}

/**
 * Canonical nullable id for query key identity.
 * - `undefined` / `null` / empty / whitespace => null
 * - non-empty string-like values => trimmed string
 */
export function canonicalizeOptionalId(value: unknown): string | null {
  const normalized = normalizeText(value);
  return normalized ?? null;
}

/**
 * Canonical list params for inventories table.
 * Includes stable defaults for page and page_size so equivalent states map to one key.
 */
export function canonicalizeInventoriesListQuery(
  listQuery?: InventoriesListQuery
): InventoriesListQuery & { page: number; page_size: number } {
  const out: InventoriesListQuery & { page: number; page_size: number } = {
    page: normalizePositiveInt(listQuery?.page) ?? 1,
    page_size: normalizePositiveInt(listQuery?.page_size) ?? DEFAULT_LIST_PAGE_SIZE,
  };
  const search = normalizeText(listQuery?.search);
  const status = normalizeText(listQuery?.status);
  const sortBy = normalizeText(listQuery?.sort_by);
  const sortDir = normalizeText(listQuery?.sort_dir);
  if (search) out.search = search;
  if (status) out.status = status;
  if (sortBy) out.sort_by = sortBy;
  if (sortDir) out.sort_dir = sortDir;
  return out;
}

export function inventoriesListKeyPart(
  listQuery?: InventoriesListQuery
): QueryKeyParams {
  const q = canonicalizeInventoriesListQuery(listQuery);
  const out: QueryKeyParams = {
    page: q.page,
    page_size: q.page_size,
  };
  if (q.sort_by) out.sort_by = q.sort_by;
  if (q.sort_dir) out.sort_dir = q.sort_dir;
  if (q.search) out.search = q.search;
  if (q.status) out.status = q.status;
  return out;
}

/**
 * Canonical GET review-queue params aligned with `buildReviewQueueQueryString` in `reviewQueueApi.ts`.
 * Omitted fields are not sent on the wire.
 */
export function canonicalizeReviewQueueListQuery(
  listQuery?: ReviewQueueListQuery
): ReviewQueueListQuery {
  const out: ReviewQueueListQuery = {};
  const inventoryId = normalizeText(listQuery?.inventory_id);
  const aisleId = normalizeText(listQuery?.aisle_id);
  if (inventoryId) out.inventory_id = inventoryId;
  if (aisleId) out.aisle_id = aisleId;
  const minC = normalizeFiniteConfidence(listQuery?.min_confidence);
  const maxC = normalizeFiniteConfidence(listQuery?.max_confidence);
  if (minC != null) out.min_confidence = minC;
  if (maxC != null) out.max_confidence = maxC;
  const traceability = normalizeText(listQuery?.traceability, { lowercase: true });
  if (traceability) out.traceability = traceability;
  if (listQuery?.has_evidence === true) out.has_evidence = true;
  if (listQuery?.has_evidence === false) out.has_evidence = false;
  if (listQuery?.qty_zero === true) out.qty_zero = true;
  if (listQuery?.qty_zero === false) out.qty_zero = false;
  const skuContains = normalizeText(listQuery?.sku_contains);
  if (skuContains) out.sku_contains = skuContains;
  const positionStatus = normalizeText(listQuery?.position_status, { lowercase: true });
  if (positionStatus) out.position_status = positionStatus;
  const sortBy = normalizeText(listQuery?.sort_by);
  const sortDir = normalizeText(listQuery?.sort_dir);
  if (sortBy) out.sort_by = sortBy;
  if (sortDir) out.sort_dir = sortDir;
  const page = normalizePositiveInt(listQuery?.page);
  const pageSize = normalizePositiveInt(listQuery?.page_size);
  if (page != null) out.page = page;
  if (pageSize != null) out.page_size = pageSize;
  return out;
}

function reviewQueueKeyPartFromCanonical(q: ReviewQueueListQuery): QueryKeyParams {
  const out: QueryKeyParams = {};
  if (q.inventory_id) out.inventory_id = q.inventory_id;
  if (q.aisle_id) out.aisle_id = q.aisle_id;
  if (q.min_confidence != null) out.min_confidence = q.min_confidence;
  if (q.max_confidence != null) out.max_confidence = q.max_confidence;
  if (q.traceability) out.traceability = q.traceability;
  if (q.has_evidence === true) out.has_evidence = 1;
  if (q.has_evidence === false) out.has_evidence = 0;
  if (q.qty_zero === true) out.qty_zero = 1;
  if (q.qty_zero === false) out.qty_zero = 0;
  if (q.sku_contains) out.sku_contains = q.sku_contains;
  if (q.position_status) out.position_status = q.position_status;
  if (q.sort_by) out.sort_by = q.sort_by;
  if (q.sort_dir) out.sort_dir = q.sort_dir;
  if (q.page != null) out.page = q.page;
  if (q.page_size != null) out.page_size = q.page_size;
  return out;
}

/**
 * Stable key fragment for review queue; derived only from canonical query semantics.
 */
export function reviewQueueListKeyPart(listQuery?: ReviewQueueListQuery): QueryKeyParams {
  return reviewQueueKeyPartFromCanonical(canonicalizeReviewQueueListQuery(listQuery));
}

/**
 * Canonical GET aisle positions params aligned with `buildAislePositionsQueryString` in `jobsApi.ts`.
 */
export function canonicalizeAislePositionsListQuery(
  listQuery?: AislePositionsListQuery
): AislePositionsListQuery {
  const out: AislePositionsListQuery = {};
  const status = normalizeText(listQuery?.status);
  if (status) out.status = status;
  if (listQuery?.needs_review != null) out.needs_review = listQuery.needs_review;
  const minC = normalizeFiniteConfidence(listQuery?.min_confidence);
  if (minC != null) out.min_confidence = minC;
  const skuFilter = normalizeText(listQuery?.sku_filter);
  if (skuFilter) out.sku_filter = skuFilter;
  const page = normalizePositiveInt(listQuery?.page);
  const pageSize = normalizePositiveInt(listQuery?.page_size);
  if (page != null) out.page = page;
  if (pageSize != null) out.page_size = pageSize;
  const sortBy = normalizeText(listQuery?.sort_by);
  const sortDir = normalizeText(listQuery?.sort_dir);
  if (sortBy) out.sort_by = sortBy;
  if (sortDir) out.sort_dir = sortDir;
  const jobId = normalizeText(listQuery?.job_id);
  if (jobId) out.job_id = jobId;
  if (listQuery?.consolidate_by_sku === false) out.consolidate_by_sku = false;
  return out;
}

function positionsKeyPartFromCanonical(c: AislePositionsListQuery): QueryKeyParams {
  const out: QueryKeyParams = {};
  if (c.page != null) out.page = c.page;
  if (c.page_size != null) out.page_size = c.page_size;
  if (c.job_id) out.job_id = c.job_id;
  else out.job_slice = 'resolver_default';
  if (c.status) out.status = c.status;
  if (c.needs_review != null) out.needs_review = c.needs_review ? 1 : 0;
  if (c.min_confidence != null) out.min_confidence = c.min_confidence;
  if (c.sku_filter) out.sku_filter = c.sku_filter;
  if (c.sort_by) out.sort_by = c.sort_by;
  if (c.sort_dir) out.sort_dir = c.sort_dir;
  if (c.consolidate_by_sku === false) out.consolidate_by_sku = 0;
  return out;
}

/** Stable cache identity for positions list: job_id and pagination must not alias across runs. */
export function positionsListKeyPart(listQuery?: AislePositionsListQuery): QueryKeyParams {
  return positionsKeyPartFromCanonical(canonicalizeAislePositionsListQuery(listQuery));
}
