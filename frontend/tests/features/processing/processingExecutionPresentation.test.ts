/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from 'vitest';
import {
  buildJobExecutionPresentation,
  buildObsContentTabsForJob,
  computeMetadataInconsistencyReasons,
  extractConfiguredFallbackIdentity,
  extractExecutedFallbackIdentity,
  formatCurrentStageLabel,
  isLegacyIdentificationMode,
  parseLooseBoolean,
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

  it('parses loose booleans without treating "false" as true', () => {
    expect(parseLooseBoolean(true)).toBe(true);
    expect(parseLooseBoolean(false)).toBe(false);
    expect(parseLooseBoolean('true')).toBe(true);
    expect(parseLooseBoolean('false')).toBe(false);
    expect(parseLooseBoolean(1)).toBe(true);
    expect(parseLooseBoolean(0)).toBe(false);
    expect(parseLooseBoolean('FALSE')).toBe(false);
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
    expect(presentation.showFallbackConfiguredRows).toBe(false);
    expect(presentation.showPromptTab).toBe(false);
    expect(presentation.promptTabMode).toBe('hidden');
    expect(presentation.externalProviderUsedLabel).toBe('no');
    expect(presentation.currentStageLabel).toBe('InternalOcr');
  });

  it('separates configured Claude from executed Gemini', () => {
    const presentation = buildJobExecutionPresentation({
      identification_mode: 'INTERNAL_OCR',
      execution_strategy: 'INTERNAL_OCR',
      provider_name: 'gemini',
      identification_execution: {
        external_fallback: {
          fallback_enabled: true,
          fallback_provider: 'claude',
          fallback_model: 'claude-opus-4-7',
          prompt_key: 'external_fallback_v1',
          prompt_version: '1',
        },
      },
      fallback_asset_summaries: [
        {
          asset_id: 'a1',
          external_provider: 'gemini',
          executed_model: 'gemini-3.1-pro-preview',
          prompt_key: 'external_fallback_v1',
        },
      ],
      result_json: { fallback_progress: { fallback_requested: 1, resolved_external: 1 } },
    });
    expect(presentation.configured.provider).toBe('claude');
    expect(presentation.executed?.provider).toBe('gemini');
    expect(presentation.metadataInconsistencyReasons).toContain('PROVIDER_MISMATCH');
    expect(presentation.historicalMetadataWarning).toBe(true);
  });

  it('separates configured Gemini from executed Claude', () => {
    const presentation = buildJobExecutionPresentation({
      identification_mode: 'INTERNAL_OCR',
      execution_strategy: 'INTERNAL_OCR',
      identification_execution: {
        external_fallback: {
          fallback_enabled: true,
          fallback_provider: 'gemini',
          fallback_model: 'gemini-3.1-pro-preview',
          prompt_key: 'external_fallback_v1',
        },
      },
      fallback_asset_summaries: [
        {
          asset_id: 'a1',
          external_provider: 'claude',
          executed_model: 'claude-opus-4-7',
        },
      ],
      result_json: { fallback_progress: { fallback_requested: 1 } },
    });
    expect(presentation.configured.provider).toBe('gemini');
    expect(presentation.executed?.provider).toBe('claude');
    expect(presentation.metadataInconsistencyReasons).toContain('PROVIDER_MISMATCH');
  });

  it('flags same provider with different models', () => {
    const reasons = computeMetadataInconsistencyReasons({
      configured: {
        enabled: true,
        provider: 'claude',
        model: 'claude-opus-4-7',
        promptKey: 'external_fallback_v1',
        promptVersion: '1',
      },
      executed: {
        provider: 'claude',
        requestedModel: 'claude-opus-4-7',
        executedModel: 'claude-sonnet-4',
        promptKey: 'external_fallback_v1',
        promptVersion: '1',
        adapterName: null,
        schemaVersion: null,
        attemptNumber: null,
        providerRequestId: null,
        evidencePresent: true,
      },
      fallbackUsed: true,
    });
    expect(reasons).toContain('MODEL_MISMATCH');
  });

  it('flags prompt key mismatch', () => {
    const reasons = computeMetadataInconsistencyReasons({
      configured: {
        enabled: true,
        provider: 'claude',
        model: 'm',
        promptKey: 'external_fallback_v1',
        promptVersion: '1',
      },
      executed: {
        provider: 'claude',
        requestedModel: 'm',
        executedModel: 'm',
        promptKey: 'global_v22',
        promptVersion: '1',
        adapterName: null,
        schemaVersion: null,
        attemptNumber: null,
        providerRequestId: null,
        evidencePresent: true,
      },
      fallbackUsed: true,
    });
    expect(reasons).toContain('PROMPT_KEY_MISMATCH');
  });

  it('shows configured but not executed when fallback never ran', () => {
    const presentation = buildJobExecutionPresentation({
      identification_mode: 'INTERNAL_OCR',
      execution_strategy: 'INTERNAL_OCR',
      identification_execution: {
        external_fallback: {
          fallback_enabled: 'true',
          fallback_provider: 'claude',
          fallback_model: 'claude-opus-4-7',
          prompt_key: 'external_fallback_v1',
        },
      },
    });
    expect(presentation.fallbackConfigured).toBe(true);
    expect(presentation.fallbackUsed).toBe(false);
    expect(presentation.promptExecutedLabel).toBe('configured_not_executed');
    expect(presentation.executed).toBeNull();
  });

  it('marks executed identity unknown when fallback requested without provider evidence', () => {
    const presentation = buildJobExecutionPresentation({
      identification_mode: 'INTERNAL_OCR',
      execution_strategy: 'INTERNAL_OCR',
      identification_execution: {
        external_fallback: {
          fallback_enabled: true,
          fallback_provider: 'claude',
          fallback_model: 'claude-opus-4-7',
        },
      },
      result_json: { fallback_progress: { fallback_requested: 1 } },
      fallback_asset_summaries: [{ asset_id: 'a1', fallback_status: 'CLAIMED' }],
    });
    expect(presentation.metadataInconsistencyReasons).toContain('EXECUTED_IDENTITY_UNKNOWN');
  });

  it('treats historical boolean string false as disabled', () => {
    const configured = extractConfiguredFallbackIdentity({
      external_fallback: {
        fallback_enabled: 'false',
        fallback_provider: '',
      },
    });
    expect(configured.enabled).toBe(false);
  });

  it('does not invent provider when historical snapshot is incomplete', () => {
    const presentation = buildJobExecutionPresentation({
      identification_mode: 'INTERNAL_OCR',
      execution_strategy: 'INTERNAL_OCR',
      provider_name: 'gemini',
      result_json: { fallback_progress: { fallback_requested: 1 } },
    });
    expect(presentation.configured.provider).toBeNull();
    expect(presentation.displayProvider).toBeNull();
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

  it('hides prompt tab for CODE_SCAN without fallback', () => {
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

  it('presents historical LEGACY job with AI fields visible', () => {
    const presentation = buildJobExecutionPresentation({
      identification_mode: 'LEGACY_LLM',
      execution_strategy: 'LEGACY_LLM',
      provider_name: 'gemini',
      model_name: 'x',
      prompt_key: 'hybrid',
    });
    expect(presentation.requestedMode).toBe('LEGACY_LLM');
    expect(presentation.executedStrategy).toBe('LEGACY_LLM');
    expect(presentation.showProviderModelRows).toBe(true);
    expect(presentation.promptTabMode).toBe('legacy');
  });

  it('presents INTERNAL_OCR and CODE_SCAN without AI fields', () => {
    for (const strategy of ['INTERNAL_OCR', 'CODE_SCAN'] as const) {
      const presentation = buildJobExecutionPresentation({
        identification_mode: strategy,
        execution_strategy: strategy,
      });
      expect(presentation.showProviderModelRows).toBe(false);
      expect(presentation.showPromptTab).toBe(false);
    }
  });

  it('handles unknown strategy and requested≠executed without crashing', () => {
    const presentation = buildJobExecutionPresentation({
      identification_mode: 'INTERNAL_OCR',
      execution_strategy: 'FUTURE_STRATEGY',
      current_stage: 'UnknownStage',
    });
    expect(presentation.requestedMode).toBe('INTERNAL_OCR');
    expect(presentation.executedStrategy).toBe('FUTURE_STRATEGY');
    expect(presentation.currentStageLabel).toBe('UnknownStage');
    expect(presentation.showProviderModelRows).toBe(false);
  });

  it('keeps compatibility with sparse/legacy response shapes', () => {
    const presentation = buildJobExecutionPresentation({});
    expect(presentation.requestedMode).toBe('—');
    expect(presentation.executedStrategy).toBe('—');
    expect(presentation.showPromptTab).toBe(false);
  });

  it('extracts executed identity only from summaries', () => {
    expect(extractExecutedFallbackIdentity(null)).toBeNull();
    const executed = extractExecutedFallbackIdentity([
      {
        asset_id: 'a1',
        external_provider: 'claude',
        executed_model: 'claude-opus-4-7',
        prompt_key: 'external_fallback_v1',
      },
    ]);
    expect(executed?.provider).toBe('claude');
    expect(executed?.evidencePresent).toBe(true);
  });

  it('exposes executed prompt content when persisted on summaries', () => {
    const presentation = buildJobExecutionPresentation({
      identification_mode: 'INTERNAL_OCR',
      execution_strategy: 'INTERNAL_OCR',
      identification_execution: {
        external_fallback: {
          fallback_enabled: true,
          fallback_provider: 'claude',
          fallback_model: 'claude-opus-4-7',
          prompt_key: 'external_fallback_single_label',
          prompt_version: '1.0.0',
        },
        supplier_prompt: {
          prompt_id: 'p1',
          prompt_key: 'supplier_prompt_config',
          prompt_version: '3',
          content_sha256: 'suphash',
          content: 'UNIQUE_SUPPLIER_MARKER prefer labeled EAN-13.',
          source_level: 'aisle.client_supplier',
          required: true,
        },
      },
      fallback_asset_summaries: [
        {
          asset_id: 'a1',
          external_provider: 'claude',
          executed_model: 'claude-opus-4-7',
          prompt_key: 'external_fallback_single_label',
          prompt_version: '1.0.0',
          prompt_sha256: 'abc123',
          prompt_text:
            '[BASE]\n...\n[SUPPLIER CUSTOM INSTRUCTIONS]\nUNIQUE_SUPPLIER_MARKER prefer labeled EAN-13.',
          supplier_prompt_id: 'p1',
          supplier_prompt_key: 'supplier_prompt_config',
          supplier_prompt_version: '3',
          supplier_prompt_sha256: 'suphash',
          supplier_prompt_loaded: true,
          supplier_prompt_content: 'UNIQUE_SUPPLIER_MARKER prefer labeled EAN-13.',
        },
      ],
      result_json: { fallback_progress: { fallback_requested: 1 } },
    });
    expect(presentation.promptContentAvailability).toBe('available');
    expect(presentation.executedPromptContent).toContain('[SUPPLIER CUSTOM INSTRUCTIONS]');
    expect(presentation.executedPromptContent).toContain('UNIQUE_SUPPLIER_MARKER');
    expect(presentation.supplierPromptConfigured?.content).toContain('UNIQUE_SUPPLIER_MARKER');
    expect(presentation.supplierPromptExecuted?.loaded).toBe(true);
    expect(presentation.supplierPromptMissingAlert).toBe(false);
    expect(presentation.promptConfiguredLabel).not.toContain('global_v22');
  });

  it('alerts when supplier is associated but custom instructions missing from effective prompt', () => {
    const presentation = buildJobExecutionPresentation({
      identification_mode: 'INTERNAL_OCR',
      execution_strategy: 'INTERNAL_OCR',
      identification_execution: {
        external_fallback: {
          fallback_enabled: true,
          fallback_provider: 'claude',
          fallback_model: 'claude-opus-4-7',
          prompt_key: 'external_fallback_single_label',
          prompt_version: '1.0.0',
        },
        supplier_extraction_profile: {
          supplier_profile_id: 'c874',
          supplier_id: 'sup-1',
          quantity_rules: { required: true },
        },
      },
      fallback_asset_summaries: [
        {
          asset_id: 'a1',
          external_provider: 'claude',
          executed_model: 'claude-opus-4-7',
          prompt_key: 'external_fallback_single_label',
          prompt_sha256: 'abc',
          prompt_text: '[BASE]\n[SUPPLIER EXTRACTION PROFILE]\n- supplier_profile_id: c874',
          supplier_prompt_loaded: false,
        },
      ],
      result_json: { fallback_progress: { fallback_requested: 1 } },
    });
    expect(presentation.supplierPromptMissingAlert).toBe(true);
  });
});
