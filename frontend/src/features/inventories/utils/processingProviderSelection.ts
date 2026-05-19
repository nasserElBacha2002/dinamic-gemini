import type { ProcessingProviderOptionsResponse } from '../../../api/types';

export type ProcessingProviderOptionsMode = 'test' | 'production';

/** Initial provider/model keys when opening the aisle process dialog. */
export function initialProcessingSelection(
  data: ProcessingProviderOptionsResponse | undefined,
  mode: ProcessingProviderOptionsMode
): { providerKey: string; modelKey: string } {
  if (!data?.providers?.length) {
    return { providerKey: '', modelKey: '' };
  }
  const defaultProvider = data.default_provider_key ?? '';
  const provider =
    data.providers.find((p) => p.key === defaultProvider) ?? data.providers[0];
  const providerKey = provider?.key ?? '';
  const defaultModel =
    data.default_model_key ??
    provider?.default_model ??
    provider?.models?.[0]?.id ??
    '';
  if (mode === 'production') {
    return { providerKey, modelKey: defaultModel };
  }
  return { providerKey, modelKey: '' };
}

/** When the operator changes provider in production mode, pin the sole production model. */
export function modelKeyForProviderChange(
  providerKey: string,
  data: ProcessingProviderOptionsResponse | undefined,
  mode: ProcessingProviderOptionsMode
): string {
  if (mode !== 'production' || !providerKey.trim()) {
    return '';
  }
  const provider = (data?.providers ?? []).find((p) => p.key === providerKey);
  return provider?.default_model ?? provider?.models?.[0]?.id ?? '';
}

export function hasProductionProviders(
  data: ProcessingProviderOptionsResponse | undefined
): boolean {
  return (data?.providers?.length ?? 0) > 0;
}
