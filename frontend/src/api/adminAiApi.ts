import { V3_ADMIN_BASE, V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import type { AdminAiComposedPromptResponse, AdminAiConfigResponse, ProcessingProviderOptionsResponse } from './types';
import { apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export async function getProcessingProviderOptions(
  mode: 'test' | 'production' = 'test'
): Promise<ProcessingProviderOptionsResponse> {
  const q = new URLSearchParams({ mode });
  return apiRequestJson<ProcessingProviderOptionsResponse>(
    `${API_BASE}${V3_INVENTORIES_BASE}/processing-provider-options?${q.toString()}`
  );
}

export async function getAdminAiConfig(): Promise<AdminAiConfigResponse> {
  return apiRequestJson<AdminAiConfigResponse>(`${API_BASE}${V3_ADMIN_BASE}/ai-config`);
}

export async function getAdminAiComposedPrompt(params: {
  pipeline_provider_key: string;
  prompt_key: string;
  prompt_parity_mode: boolean;
}): Promise<AdminAiComposedPromptResponse> {
  const q = new URLSearchParams({
    prompt_key: params.prompt_key,
    pipeline_provider_key: params.pipeline_provider_key,
    prompt_parity_mode: String(params.prompt_parity_mode),
  });
  return apiRequestJson<AdminAiComposedPromptResponse>(
    `${API_BASE}${V3_ADMIN_BASE}/ai-config/composed-prompt?${q.toString()}`
  );
}
