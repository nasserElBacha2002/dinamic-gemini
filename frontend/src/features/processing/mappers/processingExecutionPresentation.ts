/**
 * Phase 8 — present requested/executed processing without implying unused AI execution.
 */

import type {
  AisleIdentificationExecutionStrategy,
  AisleIdentificationMode,
} from '../../../api/types';

export type ProcessingObsTabId =
  | 'events'
  | 'processing'
  | 'prompt'
  | 'attachments'
  | 'traceability'
  | 'auditability'
  | 'diagnostics';

export interface JobExecutionPresentationInput {
  identification_mode?: string | null;
  execution_strategy?: string | null;
  current_stage?: string | null;
  provider_name?: string | null;
  model_name?: string | null;
  prompt_key?: string | null;
  result_json?: Record<string, unknown> | null;
  /** True when at least one external attempt / fallback ran. */
  external_execution_used?: boolean | null;
}

export interface JobExecutionPresentation {
  requestedMode: string;
  executedStrategy: string;
  currentStageLabel: string;
  usesExternalLlm: boolean;
  showProviderModelRows: boolean;
  showPromptTab: boolean;
  externalProviderUsedLabel: 'yes' | 'no';
  fallbackUsed: boolean;
}

const LEGACY_STRATEGIES = new Set(['LEGACY_LLM', 'LEGACY_LLM_TEMPORARY']);
const INTERNAL_STRATEGIES = new Set(['CODE_SCAN', 'INTERNAL_OCR']);

export function isLegacyIdentificationMode(mode: string | null | undefined): boolean {
  const raw = String(mode || '').trim().toUpperCase();
  return raw === 'LEGACY_LLM' || raw === 'LEGACY_LLM_TEMPORARY';
}

export function strategyUsesExternalLlm(
  strategy: string | null | undefined,
  options?: { externalExecutionUsed?: boolean | null },
): boolean {
  if (options?.externalExecutionUsed === true) return true;
  const raw = String(strategy || '').trim().toUpperCase();
  if (!raw) return false;
  if (INTERNAL_STRATEGIES.has(raw)) return false;
  return LEGACY_STRATEGIES.has(raw) || raw === 'EXTERNAL_PROVIDER';
}

export function formatCurrentStageLabel(
  stage: string | null | undefined,
  strategy: string | null | undefined,
): string {
  const s = String(stage || '').trim();
  const strat = String(strategy || '').trim().toUpperCase();
  if (!s) return '—';
  if (s === 'CodeScan' && strat === 'INTERNAL_OCR') return 'InternalOcr';
  return s;
}

export function buildJobExecutionPresentation(
  input: JobExecutionPresentationInput,
): JobExecutionPresentation {
  const requested = String(input.identification_mode || '—');
  const executed = String(input.execution_strategy || '—');
  const fallbackProgress = input.result_json?.fallback_progress as
    | Record<string, unknown>
    | undefined;
  const fallbackUsed =
    Boolean(input.external_execution_used) ||
    Number(fallbackProgress?.resolved_external || 0) > 0 ||
    Number(fallbackProgress?.fallback_requested || 0) > 0;
  const usesExternalLlm = strategyUsesExternalLlm(executed, {
    externalExecutionUsed: input.external_execution_used || fallbackUsed,
  });
  return {
    requestedMode: requested,
    executedStrategy: executed,
    currentStageLabel: formatCurrentStageLabel(input.current_stage, executed),
    usesExternalLlm,
    showProviderModelRows: usesExternalLlm,
    showPromptTab: usesExternalLlm,
    externalProviderUsedLabel: usesExternalLlm ? 'yes' : 'no',
    fallbackUsed,
  };
}

/** New process-aisle options (legacy omitted from selector). */
export const PROCESS_AISLE_IDENTIFICATION_OPTIONS: AisleIdentificationMode[] = [
  'CODE_SCAN',
  'INTERNAL_OCR',
];

export function buildObsContentTabsForJob(options: {
  processingEnabled: boolean;
  presentation: JobExecutionPresentation;
  hasAttachments?: boolean;
}): ProcessingObsTabId[] {
  const tabs: ProcessingObsTabId[] = ['events'];
  if (options.processingEnabled) tabs.push('processing');
  if (options.presentation.showPromptTab) tabs.push('prompt');
  if (options.hasAttachments) tabs.push('attachments');
  tabs.push('traceability', 'auditability', 'diagnostics');
  return tabs;
}

export function strategyLabelKey(strategy: string | null | undefined): string {
  const raw = String(strategy || '').trim().toUpperCase();
  if (raw === 'INTERNAL_OCR') return 'aisle.execution_strategy_internal_ocr';
  if (raw === 'CODE_SCAN') return 'aisle.execution_strategy_code_scan';
  if (raw === 'LEGACY_LLM_TEMPORARY') return 'aisle.execution_strategy_legacy_llm_temporary';
  if (raw === 'LEGACY_LLM') return 'aisle.execution_strategy_legacy_llm_historical';
  return 'aisle.execution_strategy_unknown';
}

export type { AisleIdentificationExecutionStrategy };
