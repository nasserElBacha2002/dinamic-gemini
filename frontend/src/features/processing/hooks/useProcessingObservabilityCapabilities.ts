import { useQuery } from '@tanstack/react-query';
import { getProcessingObservabilityCapabilities } from '../../../api/processingApi';
import { queryKeys } from '../../../api/queryKeys';

function parseEnvBool(value: unknown, defaultValue = false): boolean {
  if (value === undefined || value === null || value === '') return defaultValue;
  const normalized = String(value).trim().toLowerCase();
  return normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on';
}

function envFallback() {
  return {
    processing_observability_enabled: parseEnvBool(
      import.meta.env.VITE_PROCESSING_OBSERVABILITY_ENABLED
    ),
  };
}

export function useProcessingObservabilityCapabilities(options?: { enabled?: boolean }) {
  const query = useQuery({
    queryKey: queryKeys.config.processingObservabilityCapabilities(),
    queryFn: getProcessingObservabilityCapabilities,
    staleTime: 5 * 60 * 1000,
    retry: false,
    enabled: options?.enabled !== false,
  });

  if (query.data) {
    return {
      ...query.data,
      source: 'backend' as const,
      isLoading: query.isLoading,
      isError: query.isError,
    };
  }

  return {
    ...envFallback(),
    source: 'fallback' as const,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}
