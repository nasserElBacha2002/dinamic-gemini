/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from 'vitest';
import {
  buildJobExecutionPresentation,
  buildObsContentTabsForJob,
  formatCurrentStageLabel,
  isLegacyIdentificationMode,
  PROCESS_AISLE_IDENTIFICATION_OPTIONS,
  strategyUsesExternalLlm,
} from '../../../src/features/processing/mappers/processingExecutionPresentation';

describe('processingExecutionPresentation', () => {
  it('excludes legacy modes from new process options', () => {
    expect(PROCESS_AISLE_IDENTIFICATION_OPTIONS).toEqual(['CODE_SCAN', 'INTERNAL_OCR']);
    expect(PROCESS_AISLE_IDENTIFICATION_OPTIONS).not.toContain('LEGACY_LLM');
  });

  it('detects legacy modes', () => {
    expect(isLegacyIdentificationMode('LEGACY_LLM')).toBe(true);
    expect(isLegacyIdentificationMode('LEGACY_LLM_TEMPORARY')).toBe(true);
    expect(isLegacyIdentificationMode('INTERNAL_OCR')).toBe(false);
  });

  it('hides provider/prompt for INTERNAL_OCR without external execution', () => {
    const presentation = buildJobExecutionPresentation({
      identification_mode: 'INTERNAL_OCR',
      execution_strategy: 'INTERNAL_OCR',
      current_stage: 'CodeScan',
      provider_name: 'Gemini',
      model_name: 'gemini-3.1-pro-preview',
    });
    expect(presentation.showProviderModelRows).toBe(false);
    expect(presentation.showPromptTab).toBe(false);
    expect(presentation.externalProviderUsedLabel).toBe('no');
    expect(presentation.currentStageLabel).toBe('InternalOcr');
  });

  it('shows provider/prompt when fallback external ran', () => {
    const presentation = buildJobExecutionPresentation({
      identification_mode: 'INTERNAL_OCR',
      execution_strategy: 'INTERNAL_OCR',
      result_json: {
        fallback_progress: { fallback_requested: 1, resolved_external: 1 },
      },
    });
    expect(presentation.showProviderModelRows).toBe(true);
    expect(presentation.showPromptTab).toBe(true);
    expect(presentation.fallbackUsed).toBe(true);
  });

  it('shows provider for LEGACY_LLM historical jobs', () => {
    expect(strategyUsesExternalLlm('LEGACY_LLM')).toBe(true);
    const tabs = buildObsContentTabsForJob({
      processingEnabled: true,
      presentation: buildJobExecutionPresentation({
        execution_strategy: 'LEGACY_LLM',
      }),
      hasAttachments: false,
    });
    expect(tabs).toContain('prompt');
    expect(tabs).toContain('processing');
    expect(tabs).not.toContain('attachments');
  });

  it('hides prompt tab for CODE_SCAN', () => {
    const tabs = buildObsContentTabsForJob({
      processingEnabled: false,
      presentation: buildJobExecutionPresentation({
        execution_strategy: 'CODE_SCAN',
      }),
    });
    expect(tabs).not.toContain('prompt');
    expect(tabs).toContain('events');
    expect(tabs).toContain('diagnostics');
  });

  it('corrects CodeScan stage label when strategy is INTERNAL_OCR', () => {
    expect(formatCurrentStageLabel('CodeScan', 'INTERNAL_OCR')).toBe('InternalOcr');
    expect(formatCurrentStageLabel('CodeScan', 'CODE_SCAN')).toBe('CodeScan');
  });
});
