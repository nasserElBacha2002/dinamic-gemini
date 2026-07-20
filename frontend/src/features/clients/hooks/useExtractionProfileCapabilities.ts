/** Runtime extraction-profile feature flags (backend config with env fallback). */
import { useQuery } from '@tanstack/react-query';
import { apiRequestJson } from '../../../api/request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export interface ExtractionProfileCapabilities {
  reference_template_annotations_enabled: boolean;
  profile_aware_validation_enabled: boolean;
  client_extraction_profiles_enabled: boolean;
}

export type ExtractionProfileCapabilitiesSource = 'backend' | 'fallback';

export interface ResolvedExtractionProfileCapabilities extends ExtractionProfileCapabilities {
  source: ExtractionProfileCapabilitiesSource;
  isLoading: boolean;
}

function parseEnvBool(value: unknown, defaultValue = false): boolean {
  if (value === undefined || value === null || value === '') return defaultValue;
  const normalized = String(value).trim().toLowerCase();
  return normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on';
}

function envFallback(): ExtractionProfileCapabilities {
  return {
    reference_template_annotations_enabled: parseEnvBool(
      import.meta.env.VITE_REFERENCE_TEMPLATE_ANNOTATIONS_ENABLED
    ),
    profile_aware_validation_enabled: parseEnvBool(import.meta.env.VITE_PROFILE_AWARE_VALIDATION_ENABLED),
    client_extraction_profiles_enabled: parseEnvBool(import.meta.env.VITE_CLIENT_EXTRACTION_PROFILES_ENABLED),
  };
}

export async function fetchExtractionProfileCapabilities(): Promise<ExtractionProfileCapabilities> {
  return apiRequestJson<ExtractionProfileCapabilities>(
    `${API_BASE}/api/v3/config/extraction-profile-capabilities`
  );
}

export function useExtractionProfileCapabilities(options?: {
  enabled?: boolean;
}): ResolvedExtractionProfileCapabilities {
  const query = useQuery({
    queryKey: ['config', 'extraction-profile-capabilities'],
    queryFn: fetchExtractionProfileCapabilities,
    staleTime: 5 * 60 * 1000,
    retry: false,
    enabled: options?.enabled !== false,
  });

  if (query.data) {
    return {
      ...query.data,
      source: 'backend',
      isLoading: query.isLoading,
    };
  }

  return {
    ...envFallback(),
    source: 'fallback',
    isLoading: query.isLoading,
  };
}
