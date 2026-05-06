import { V3_ADMIN_BASE, V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import type { AdminAiComposedPromptResponse, AdminAiConfigResponse, ProcessingProviderOptionsResponse } from './types';
import { handleResponse, protectedFetch } from './http';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export async function getProcessingProviderOptions(): Promise<ProcessingProviderOptionsResponse> {
  const response = await protectedFetch(`${API_BASE}${V3_INVENTORIES_BASE}/processing-provider-options`);
  return handleResponse<ProcessingProviderOptionsResponse>(response);
}

export async function getAdminAiConfig(): Promise<AdminAiConfigResponse> {
  const response = await protectedFetch(`${API_BASE}${V3_ADMIN_BASE}/ai-config`);
  return handleResponse<AdminAiConfigResponse>(response);
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
  const response = await protectedFetch(
    `${API_BASE}${V3_ADMIN_BASE}/ai-config/composed-prompt?${q.toString()}`
  );
  return handleResponse<AdminAiComposedPromptResponse>(response);
}
