/**
 * v3.1.1 — Hooks that expose the Result-centric visible model (Epic 1).
 *
 * These hooks wrap the existing position API and map responses to ResultSummary
 * and ResultDetail so UI can consume a single visible model without touching
 * raw Position/Entity types.
 */

import { useMemo } from 'react';
import { useAislePositions, usePositionDetail } from '../../../hooks';
import {
  mapPositionSummaryToResultSummary,
  mapPositionDetailToResultDetail,
} from '../mappers';
import type { ResultSummary, ResultDetail } from '../types';
import type { AislePositionsListQuery } from '../../../api/client';

/** Large page: results overview filters client-side; differs from `DEFAULT_LIST_PAGE_SIZE` until paged API UX ships. */
const defaultResultsListQuery: AislePositionsListQuery = { page: 1, page_size: 500 };

/**
 * Returns the list of results for an aisle as ResultSummary[].
 * Uses the same API as AislePositionsPage but exposes the visible Result model.
 */
export function useResultSummaries(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  options?: { enabled?: boolean; listQuery?: AislePositionsListQuery }
) {
  const listQuery = options?.listQuery ?? defaultResultsListQuery;
  const query = useAislePositions(inventoryId, aisleId, { ...options, listQuery });
  const results: ResultSummary[] = useMemo(() => {
    const positions = query.data?.positions ?? [];
    return positions.map(mapPositionSummaryToResultSummary);
  }, [query.data?.positions]);

  return {
    ...query,
    results,
  };
}

/**
 * Returns a single result detail as ResultDetail, or undefined when loading/error.
 * Uses the same API as PositionDetailPage but exposes the visible Result model.
 */
export function useResultDetail(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  positionId: string | undefined,
  options?: { enabled?: boolean }
) {
  const query = usePositionDetail(
    inventoryId,
    aisleId,
    positionId,
    options
  );
  const result: ResultDetail | undefined = useMemo(() => {
    const data = query.data;
    if (!data) return undefined;
    return mapPositionDetailToResultDetail(data);
  }, [query.data]);

  return {
    ...query,
    result,
  };
}
