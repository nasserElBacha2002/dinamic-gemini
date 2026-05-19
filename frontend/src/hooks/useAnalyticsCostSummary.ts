import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getAnalyticsCostSummary } from '../api/analyticsApi';
import type { AnalyticsCostSummaryParams } from '../api/types';
import { queryKeys } from '../api/queryKeys';

function stableParams(p: AnalyticsCostSummaryParams): Record<string, string | undefined> {
  return {
    date_from: p.date_from,
    date_to: p.date_to,
    inventory_id: p.inventory_id,
    aisle_id: p.aisle_id,
    client_id: p.client_id,
    client_supplier_id: p.client_supplier_id,
    provider_name: p.provider_name,
    model_name: p.model_name,
  };
}

export function useAnalyticsCostSummary(
  params: AnalyticsCostSummaryParams,
  options?: { enabled?: boolean }
) {
  const keyParams = useMemo(
    () => stableParams(params),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      params.date_from,
      params.date_to,
      params.inventory_id,
      params.aisle_id,
      params.client_id,
      params.client_supplier_id,
      params.provider_name,
      params.model_name,
    ]
  );

  return useQuery({
    queryKey: queryKeys.analytics.costSummary(keyParams),
    queryFn: () => getAnalyticsCostSummary(keyParams),
    enabled: options?.enabled !== false,
    staleTime: 120_000,
  });
}
