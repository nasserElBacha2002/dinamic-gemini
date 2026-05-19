import { describe, expect, it } from 'vitest';
import type { ProcessingProviderOptionsResponse } from '../src/api/types';
import {
  initialProcessingSelection,
  modelKeyForProviderChange,
} from '../src/features/inventories/utils/processingProviderSelection';

const sampleOpts: ProcessingProviderOptionsResponse = {
  mode: 'production',
  default_provider_key: 'gemini',
  default_model_key: 'gemini-prod',
  default_prompt_key: 'global_v22',
  prompt_profiles: [],
  providers: [
    {
      key: 'gemini',
      label: 'Gemini',
      execution_mode: 'native',
      models: [{ id: 'gemini-prod', label: 'gemini-prod' }],
      default_model: 'gemini-prod',
    },
    {
      key: 'openai',
      label: 'OpenAI',
      execution_mode: 'native',
      models: [{ id: 'gpt-prod', label: 'gpt-prod' }],
      default_model: 'gpt-prod',
    },
  ],
};

describe('processingProviderSelection', () => {
  it('initializes production selection with default provider and model', () => {
    expect(initialProcessingSelection(sampleOpts, 'production')).toEqual({
      providerKey: 'gemini',
      modelKey: 'gemini-prod',
    });
  });

  it('initializes test selection with default provider only', () => {
    expect(initialProcessingSelection(sampleOpts, 'test')).toEqual({
      providerKey: 'gemini',
      modelKey: '',
    });
  });

  it('pins production model when provider changes', () => {
    expect(modelKeyForProviderChange('openai', sampleOpts, 'production')).toBe('gpt-prod');
    expect(modelKeyForProviderChange('openai', sampleOpts, 'test')).toBe('');
  });

});
