import type { AislePositionsListQuery, InventoriesListQuery, ReviewQueueListQuery } from './client';
import { DEFAULT_LIST_PAGE_SIZE } from '../constants/dataTable';

type QueryKeyPrimitive = string | number;

export type QueryKeyParams = Record<string, QueryKeyPrimitive>;

function normalizeText(value: unknown, options?: { lowercase?: boolean }): string | undefined {
  if (value == null) return undefined;
  const trimmed = String(value).trim();
  if (trimmed === '') return undefined;
  return options?.lowercase ? trimmed.toLowerCase() : trimmed;
}

function normalizeFiniteNumber(value: unknown): number | undefined {
  if (typeof value !== 'number' || Number.isNaN(value)) return undefined;
  return value;
}

function normalizePositiveInt(value: unknown): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 1) return undefined;
  return Math.trunc(value);
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
 * Canonical key fragment for review queue filters.
 * Matches API query-string semantics so key identity follows backend request identity.
 */
export function reviewQueueListKeyPart(listQuery?: ReviewQueueListQuery): QueryKeyParams {
  const out: QueryKeyParams = {};
  const inventoryId = normalizeText(listQuery?.inventory_id);
  const aisleId = normalizeText(listQuery?.aisle_id);
  const minConfidence = normalizeFiniteNumber(listQuery?.min_confidence);
  const maxConfidence = normalizeFiniteNumber(listQuery?.max_confidence);
  const traceability = normalizeText(listQuery?.traceability, { lowercase: true });
  const skuContains = normalizeText(listQuery?.sku_contains);
  const positionStatus = normalizeText(listQuery?.position_status, { lowercase: true });
  const sortBy = normalizeText(listQuery?.sort_by);
  const sortDir = normalizeText(listQuery?.sort_dir);
  const page = normalizePositiveInt(listQuery?.page);
  const pageSize = normalizePositiveInt(listQuery?.page_size);

  if (inventoryId) out.inventory_id = inventoryId;
  if (aisleId) out.aisle_id = aisleId;
  if (minConfidence != null) out.min_confidence = minConfidence;
  if (maxConfidence != null) out.max_confidence = maxConfidence;
  if (traceability) out.traceability = traceability;
  if (listQuery?.has_evidence === true) out.has_evidence = 1;
  if (listQuery?.has_evidence === false) out.has_evidence = 0;
  if (listQuery?.qty_zero === true) out.qty_zero = 1;
  if (listQuery?.qty_zero === false) out.qty_zero = 0;
  if (skuContains) out.sku_contains = skuContains;
  if (positionStatus) out.position_status = positionStatus;
  if (sortBy) out.sort_by = sortBy;
  if (sortDir) out.sort_dir = sortDir;
  if (page != null) out.page = page;
  if (pageSize != null) out.page_size = pageSize;
  return out;
}

/** Stable cache identity for positions list: job_id and pagination must not alias across runs. */
export function positionsListKeyPart(
  listQuery?: AislePositionsListQuery
): QueryKeyParams {
  const out: QueryKeyParams = {};
  const page = normalizePositiveInt(listQuery?.page);
  const pageSize = normalizePositiveInt(listQuery?.page_size);
  const jobId = normalizeText(listQuery?.job_id);
  const status = normalizeText(listQuery?.status);
  const skuFilter = normalizeText(listQuery?.sku_filter);
  const sortBy = normalizeText(listQuery?.sort_by);
  const sortDir = normalizeText(listQuery?.sort_dir);
  const minConfidence = normalizeFiniteNumber(listQuery?.min_confidence);

  if (page != null) out.page = page;
  if (pageSize != null) out.page_size = pageSize;
  // Keep resolver default separate from explicit runs.
  if (jobId) out.job_id = jobId;
  else out.job_slice = 'resolver_default';
  if (status) out.status = status;
  if (listQuery?.needs_review != null) out.needs_review = listQuery.needs_review ? 1 : 0;
  if (minConfidence != null) out.min_confidence = minConfidence;
  if (skuFilter) out.sku_filter = skuFilter;
  if (sortBy) out.sort_by = sortBy;
  if (sortDir) out.sort_dir = sortDir;
  if (listQuery?.consolidate_by_sku === false) out.consolidate_by_sku = 0;
  return out;
}
