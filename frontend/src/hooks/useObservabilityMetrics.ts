import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getObservabilityMetrics, type ObservabilityMetricsQueryParams } from '../api/observabilityApi';
import { queryKeys } from '../api/queryKeys';

function stableParams(p: ObservabilityMetricsQueryParams): Record<string, string | undefined> {
  return {
    from: p.from,
    to: p.to,
    clientId: p.clientId,
    clientSupplierId: p.clientSupplierId,
    providerName: p.providerName,
    modelName: p.modelName,
  };
}

export function useObservabilityMetrics(
  params: ObservabilityMetricsQueryParams,
  options?: { enabled?: boolean }
) {
  const keyParams = useMemo(
    () => stableParams(params),
    // Intentionally depend on primitive fields so the query key does not churn when callers
    // pass a fresh params object with the same values on each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      params.from,
      params.to,
      params.clientId,
      params.clientSupplierId,
      params.providerName,
      params.modelName,
    ]
  );
  return useQuery({
    queryKey: queryKeys.observability.metrics(keyParams),
    queryFn: () =>
      getObservabilityMetrics({
        from: keyParams.from,
        to: keyParams.to,
        clientId: keyParams.clientId,
        clientSupplierId: keyParams.clientSupplierId,
        providerName: keyParams.providerName,
        modelName: keyParams.modelName,
      }),
    enabled: options?.enabled !== false,
    staleTime: 120_000,
  });
}
