import { describe, expect, it } from 'vitest';
import type { ExecutionLogEvent } from '../src/api/types';
import { parseProviderRequestPayload } from '../src/utils/parseExecutionLogProviderRequest';
import {
  formatProviderBrandLabel,
  resolveExecutionLogProviderKey,
} from '../src/utils/executionLogProviderTitle';

function ev(payload: Record<string, unknown>): ExecutionLogEvent {
  return {
    ts: 't',
    stage: 'AnalysisStage',
    level: 'info',
    message: 'm',
    payload,
  };
}

describe('executionLogProviderTitle', () => {
  it('prefers pipeline_provider over gemini_request event type when both exist', () => {
    const e = ev({
      event_type: 'gemini_request',
      pipeline_provider: 'claude',
      prompt_text: 'x',
    });
    const p = parseProviderRequestPayload(e)!;
    expect(resolveExecutionLogProviderKey(e, p)).toBe('claude');
  });

  it('falls back to gemini for legacy gemini_request without provider fields', () => {
    const e = ev({
      event_type: 'gemini_request',
      prompt_text: 'x',
    });
    const p = parseProviderRequestPayload(e)!;
    expect(resolveExecutionLogProviderKey(e, p)).toBe('gemini');
  });

  it('reads resolved_llm_provider_key from prompt_composition', () => {
    const e = ev({
      event_type: 'analysis_request',
      prompt_composition: { resolved_llm_provider_key: 'openai' },
    });
    const p = parseProviderRequestPayload(e)!;
    expect(resolveExecutionLogProviderKey(e, p)).toBe('openai');
  });

  it('formats known provider slugs to brand labels', () => {
    expect(formatProviderBrandLabel('claude')).toBe('Claude');
    expect(formatProviderBrandLabel('anthropic')).toBe('Claude');
    expect(formatProviderBrandLabel('gemini')).toBe('Gemini');
    expect(formatProviderBrandLabel('openai')).toBe('OpenAI');
  });
});
