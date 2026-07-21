/**
 * Phase 8 — present requested/executed processing without implying unused AI execution.
 */

import type {
  AisleIdentificationExecutionStrategy,
  AisleIdentificationMode,
  AssetFallbackSummary,
} from '../../../api/types';

export type ProcessingObsTabId =
  | 'events'
  | 'processing'
  | 'prompt'
  | 'attachments'
  | 'traceability'
  | 'auditability'
  | 'diagnostics';

export type MetadataInconsistencyReason =
  | 'PROVIDER_MISMATCH'
  | 'MODEL_MISMATCH'
  | 'PROMPT_KEY_MISMATCH'
  | 'PROMPT_VERSION_MISMATCH'
  | 'EXECUTED_IDENTITY_UNKNOWN';

export interface ExternalFallbackConfiguredIdentity {
  enabled: boolean;
  provider: string | null;
  model: string | null;
  promptKey: string | null;
  promptVersion: string | null;
}

export interface ExternalFallbackExecutedIdentity {
  provider: string | null;
  requestedModel: string | null;
  executedModel: string | null;
  promptKey: string | null;
  promptVersion: string | null;
  adapterName: string | null;
  schemaVersion: string | null;
  attemptNumber: number | null;
  providerRequestId: string | null;
  /** True when at least one durable fallback attempt/result exists. */
  evidencePresent: boolean;
}

export interface ExternalFallbackSnapshot {
  enabled: boolean;
  provider: string | null;
  model: string | null;
  promptKey: string | null;
  promptVersion: string | null;
  fallbackMode: string | null;
}

export interface GlobalFallbackPresentation {
  mode: string | null;
  provider: string | null;
  model: string | null;
  schemaVersion: string | null;
  analysisContract: string | null;
  imagesSent: number | null;
  batchCount: number | null;
  requestsCount: number | null;
  entityCount: number | null;
  conflicts: number | null;
  persistenceStatus: string | null;
  promptKey: string | null;
}

export interface IdentificationExecutionSnapshot {
  externalFallback: ExternalFallbackSnapshot | null;
  supplierPrompt: Record<string, unknown> | null;
}

export interface JobExecutionPresentationInput {
  identification_mode?: string | null;
  execution_strategy?: string | null;
  current_stage?: string | null;
  provider_name?: string | null;
  model_name?: string | null;
  prompt_key?: string | null;
  prompt_version?: string | null;
  result_json?: Record<string, unknown> | null;
  identification_execution?: Record<string, unknown> | IdentificationExecutionSnapshot | null;
  fallback_asset_summaries?: AssetFallbackSummary[] | null;
  external_execution_used?: boolean | null;
  global_fallback?: {
    fallback_mode?: string | null;
    requests_count?: number | null;
    persistence_status?: string | null;
  } | null;
}

export interface JobExecutionPresentation {
  requestedMode: string;
  executedStrategy: string;
  currentStageLabel: string;
  usesExternalLlm: boolean;
  showProviderModelRows: boolean;
  showFallbackConfiguredRows: boolean;
  showPromptTab: boolean;
  externalProviderUsedLabel: 'yes' | 'no';
  fallbackUsed: boolean;
  fallbackConfigured: boolean;
  configured: ExternalFallbackConfiguredIdentity;
  executed: ExternalFallbackExecutedIdentity | null;
  fallbackProvider: string | null;
  fallbackModel: string | null;
  fallbackPromptKey: string | null;
  fallbackPromptVersion: string | null;
  displayProvider: string | null;
  displayModel: string | null;
  displayPromptKey: string | null;
  historicalMetadataWarning: boolean;
  metadataInconsistencyReasons: MetadataInconsistencyReason[];
  promptTabMode: 'legacy' | 'fallback' | 'hidden';
  promptConfiguredLabel: string | null;
  promptExecutedLabel: string | null;
  /** Effective prompt text actually sent (when persisted). */
  executedPromptContent: string | null;
  executedPromptSha256: string | null;
  promptContentAvailability: 'not_executed' | 'available' | 'not_persisted';
  supplierPromptConfigured: {
    promptId: string | null;
    promptKey: string | null;
    promptVersion: string | null;
    contentSha256: string | null;
    content: string | null;
    source: string | null;
    required: boolean;
  } | null;
  supplierPromptExecuted: {
    promptId: string | null;
    promptKey: string | null;
    promptVersion: string | null;
    contentSha256: string | null;
    content: string | null;
    loaded: boolean | null;
  } | null;
  supplierPromptMissingAlert: boolean;
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

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

/** Parse historical / loose boolean values without treating `"false"` as true. */
export function parseLooseBoolean(value: unknown): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value === 1;
  if (typeof value === 'string') {
    const s = value.trim().toLowerCase();
    if (s === 'true' || s === '1' || s === 'yes') return true;
    if (s === 'false' || s === '0' || s === 'no' || s === '') return false;
  }
  return false;
}

function optionalString(value: unknown): string | null {
  if (value == null) return null;
  const s = String(value).trim();
  return s || null;
}

export function parseExternalFallbackSnapshot(
  raw: unknown,
): ExternalFallbackSnapshot | null {
  const ef = asRecord(raw);
  if (!ef) return null;
  return {
    enabled: parseLooseBoolean(ef.fallback_enabled ?? ef.enabled),
    provider: optionalString(ef.fallback_provider ?? ef.provider),
    model: optionalString(ef.fallback_model ?? ef.model),
    promptKey: optionalString(ef.prompt_key),
    promptVersion: optionalString(ef.prompt_version),
    fallbackMode: optionalString(ef.fallback_mode),
  };
}

export function parseGlobalFallbackPresentation(
  resultJson: Record<string, unknown> | null | undefined,
): GlobalFallbackPresentation | null {
  const root = asRecord(resultJson);
  if (!root) return null;
  const gf = asRecord(root.global_fallback);
  if (!gf) return null;
  const num = (v: unknown): number | null =>
    typeof v === 'number' && Number.isFinite(v) ? v : null;
  return {
    mode: optionalString(gf.fallback_mode),
    provider: optionalString(gf.provider),
    model: optionalString(gf.model),
    schemaVersion: optionalString(gf.schema_version),
    analysisContract: optionalString(gf.analysis_contract),
    imagesSent: num(gf.images_sent),
    batchCount: num(gf.batch_count),
    requestsCount: num(gf.requests_count),
    entityCount: num(gf.entity_count),
    conflicts: num(gf.conflicts),
    persistenceStatus: optionalString(gf.persistence_status),
    promptKey: optionalString(gf.prompt_key),
  };
}

/** Map API ``global_fallback`` summary onto presentation shape. */
export function globalFallbackFromJobSummary(
  summary: {
    fallback_mode?: string | null;
    provider?: string | null;
    model?: string | null;
    schema_version?: string | null;
    analysis_contract?: string | null;
    images_sent?: number | null;
    batch_count?: number | null;
    requests_count?: number | null;
    entity_count?: number | null;
    conflicts?: number | null;
    persistence_status?: string | null;
    prompt_key?: string | null;
  } | null | undefined,
): GlobalFallbackPresentation | null {
  if (!summary) return null;
  return {
    mode: optionalString(summary.fallback_mode),
    provider: optionalString(summary.provider),
    model: optionalString(summary.model),
    schemaVersion: optionalString(summary.schema_version),
    analysisContract: optionalString(summary.analysis_contract),
    imagesSent:
      typeof summary.images_sent === 'number' ? summary.images_sent : null,
    batchCount:
      typeof summary.batch_count === 'number' ? summary.batch_count : null,
    requestsCount:
      typeof summary.requests_count === 'number' ? summary.requests_count : null,
    entityCount:
      typeof summary.entity_count === 'number' ? summary.entity_count : null,
    conflicts: typeof summary.conflicts === 'number' ? summary.conflicts : null,
    persistenceStatus: optionalString(summary.persistence_status),
    promptKey: optionalString(summary.prompt_key),
  };
}

export function parseIdentificationExecutionSnapshot(
  raw: unknown,
): IdentificationExecutionSnapshot | null {
  const root = asRecord(raw);
  if (!root) return null;
  return {
    externalFallback: parseExternalFallbackSnapshot(root.external_fallback),
    supplierPrompt: asRecord(root.supplier_prompt),
  };
}

/** Configured identity from the immutable execution snapshot (never from job.provider_*). */
export function extractConfiguredFallbackIdentity(
  identificationExecution: unknown,
): ExternalFallbackConfiguredIdentity {
  const parsed = parseIdentificationExecutionSnapshot(identificationExecution);
  const ef = parsed?.externalFallback;
  if (!ef) {
    return {
      enabled: false,
      provider: null,
      model: null,
      promptKey: null,
      promptVersion: null,
    };
  }
  return {
    enabled: ef.enabled || Boolean(ef.provider),
    provider: ef.provider,
    model: ef.model,
    promptKey: ef.promptKey,
    promptVersion: ef.promptVersion,
  };
}

/** Executed identity from durable fallback asset summaries — not inferred from config. */
export function extractExecutedFallbackIdentity(
  summaries: AssetFallbackSummary[] | null | undefined,
): ExternalFallbackExecutedIdentity | null {
  if (!summaries || summaries.length === 0) return null;
  const withProvider = summaries.find(
    (row) => optionalString(row.external_provider) || optionalString(row.executed_model),
  );
  if (!withProvider) {
    return {
      provider: null,
      requestedModel: null,
      executedModel: null,
      promptKey: null,
      promptVersion: null,
      adapterName: null,
      schemaVersion: null,
      attemptNumber: null,
      providerRequestId: null,
      evidencePresent: false,
    };
  }
  return {
    provider: optionalString(withProvider.external_provider),
    requestedModel: optionalString(withProvider.requested_model ?? withProvider.external_model),
    executedModel: optionalString(withProvider.executed_model ?? withProvider.external_model),
    promptKey: optionalString(withProvider.prompt_key),
    promptVersion: optionalString(withProvider.prompt_version),
    adapterName: optionalString((withProvider as { adapter_name?: string }).adapter_name),
    schemaVersion: optionalString((withProvider as { schema_version?: string }).schema_version),
    attemptNumber: null,
    providerRequestId: optionalString(withProvider.external_attempt_id),
    evidencePresent: true,
  };
}

export function computeMetadataInconsistencyReasons(options: {
  configured: ExternalFallbackConfiguredIdentity;
  executed: ExternalFallbackExecutedIdentity | null;
  fallbackUsed: boolean;
  jobProvider?: string | null;
}): MetadataInconsistencyReason[] {
  const reasons: MetadataInconsistencyReason[] = [];
  const { configured, executed, fallbackUsed, jobProvider } = options;

  if (fallbackUsed && (!executed || !executed.evidencePresent || !executed.provider)) {
    reasons.push('EXECUTED_IDENTITY_UNKNOWN');
  }

  if (executed?.evidencePresent && executed.provider && configured.provider) {
    if (executed.provider.toLowerCase() !== configured.provider.toLowerCase()) {
      reasons.push('PROVIDER_MISMATCH');
    }
  }

  const configuredModel = configured.model;
  const executedModel = executed?.executedModel ?? executed?.requestedModel;
  if (executed?.evidencePresent && configuredModel && executedModel) {
    if (configuredModel.toLowerCase() !== executedModel.toLowerCase()) {
      reasons.push('MODEL_MISMATCH');
    }
  }

  if (executed?.evidencePresent && configured.promptKey && executed.promptKey) {
    if (configured.promptKey !== executed.promptKey) {
      reasons.push('PROMPT_KEY_MISMATCH');
    }
  }

  if (executed?.evidencePresent && configured.promptVersion && executed.promptVersion) {
    if (configured.promptVersion !== executed.promptVersion) {
      reasons.push('PROMPT_VERSION_MISMATCH');
    }
  }

  // Legacy hybrid job fields disagreeing with configured fallback (historical drift).
  if (
    configured.provider &&
    jobProvider &&
    jobProvider.trim().toLowerCase() !== configured.provider.toLowerCase()
  ) {
    if (!reasons.includes('PROVIDER_MISMATCH')) {
      reasons.push('PROVIDER_MISMATCH');
    }
  }

  return reasons;
}

/** @deprecated Prefer extractConfiguredFallbackIdentity */
export function extractExternalFallbackIdentity(
  identificationExecution: Record<string, unknown> | null | undefined,
): ExternalFallbackConfiguredIdentity {
  return extractConfiguredFallbackIdentity(identificationExecution);
}

export function buildJobExecutionPresentation(
  input: JobExecutionPresentationInput,
): JobExecutionPresentation {
  const requested = String(input.identification_mode || '—');
  const executedStrategy = String(input.execution_strategy || '—');
  const strategyUpper = executedStrategy.trim().toUpperCase();
  const isInternal = INTERNAL_STRATEGIES.has(strategyUpper);
  const isLegacy = LEGACY_STRATEGIES.has(strategyUpper) || strategyUpper === 'EXTERNAL_PROVIDER';

  const fallbackProgress = input.result_json?.fallback_progress as
    | Record<string, unknown>
    | undefined;
  const globalFallback =
    parseGlobalFallbackPresentation(input.result_json) ||
    globalFallbackFromJobSummary(input.global_fallback ?? null);
  const fallbackUsed =
    Boolean(input.external_execution_used) ||
    Number(fallbackProgress?.resolved_external || 0) > 0 ||
    Number(fallbackProgress?.fallback_requested || 0) > 0 ||
    Boolean(globalFallback && (globalFallback.requestsCount ?? 0) > 0) ||
    Boolean(globalFallback?.persistenceStatus);

  const configured = extractConfiguredFallbackIdentity(input.identification_execution);
  const executed = extractExecutedFallbackIdentity(input.fallback_asset_summaries);
  const fallbackConfigured = configured.enabled || Boolean(configured.provider);

  const usesExternalLlm = strategyUsesExternalLlm(executedStrategy, {
    externalExecutionUsed: input.external_execution_used || fallbackUsed,
  });

  const jobProvider = optionalString(input.provider_name);
  const jobModel = optionalString(input.model_name);
  const jobPrompt = optionalString(input.prompt_key);

  const displayProvider = isInternal ? configured.provider : jobProvider;
  const displayModel = isInternal ? configured.model : jobModel;
  const displayPromptKey = isInternal ? configured.promptKey : jobPrompt;

  const metadataInconsistencyReasons = isInternal
    ? computeMetadataInconsistencyReasons({
        configured,
        executed,
        fallbackUsed,
        jobProvider,
      })
    : [];

  const showFallbackConfiguredRows = isInternal && (fallbackConfigured || fallbackUsed);
  const showProviderModelRows = isLegacy && usesExternalLlm;
  const promptTabMode: JobExecutionPresentation['promptTabMode'] = isLegacy
    ? 'legacy'
    : isInternal && (fallbackConfigured || fallbackUsed)
      ? 'fallback'
      : 'hidden';

  const promptConfiguredLabel =
    promptTabMode === 'fallback'
      ? [configured.promptKey, configured.promptVersion].filter(Boolean).join('@') || null
      : null;
  let promptExecutedLabel: string | null = null;
  let executedPromptContent: string | null = null;
  let executedPromptSha256: string | null = null;
  let promptContentAvailability: JobExecutionPresentation['promptContentAvailability'] =
    'not_executed';
  let supplierPromptExecuted: JobExecutionPresentation['supplierPromptExecuted'] = null;
  if (promptTabMode === 'fallback') {
    if (!fallbackUsed) {
      promptExecutedLabel = 'configured_not_executed';
      promptContentAvailability = 'not_executed';
    } else if (executed?.evidencePresent) {
      const withText = (input.fallback_asset_summaries || []).find(
        (row) => optionalString(row.prompt_text) || optionalString(row.prompt_sha256),
      );
      executedPromptContent = optionalString(withText?.prompt_text);
      executedPromptSha256 = optionalString(withText?.prompt_sha256);
      if (executed.promptKey || executed.promptVersion) {
        promptExecutedLabel =
          [executed.promptKey, executed.promptVersion].filter(Boolean).join('@') || null;
      } else {
        promptExecutedLabel = 'unknown';
      }
      promptContentAvailability = executedPromptContent ? 'available' : 'not_persisted';
      const supplierRow = (input.fallback_asset_summaries || []).find(
        (row) =>
          optionalString(row.supplier_prompt_content) ||
          optionalString(row.supplier_prompt_sha256) ||
          row.supplier_prompt_loaded != null,
      );
      if (supplierRow) {
        supplierPromptExecuted = {
          promptId: optionalString(supplierRow.supplier_prompt_id),
          promptKey: optionalString(supplierRow.supplier_prompt_key),
          promptVersion: optionalString(supplierRow.supplier_prompt_version),
          contentSha256: optionalString(supplierRow.supplier_prompt_sha256),
          content: optionalString(supplierRow.supplier_prompt_content),
          loaded:
            typeof supplierRow.supplier_prompt_loaded === 'boolean'
              ? supplierRow.supplier_prompt_loaded
              : null,
        };
      }
    } else {
      promptExecutedLabel = 'configured_not_executed';
      promptContentAvailability = 'not_executed';
    }
  }

  const identParsed = parseIdentificationExecutionSnapshot(input.identification_execution);
  const snapSupplier = identParsed?.supplierPrompt;
  const supplierPromptConfigured =
    snapSupplier != null
      ? {
          promptId: optionalString(snapSupplier.prompt_id),
          promptKey: optionalString(snapSupplier.prompt_key),
          promptVersion: optionalString(snapSupplier.prompt_version),
          contentSha256: optionalString(snapSupplier.content_sha256),
          content: optionalString(snapSupplier.content),
          source: optionalString(snapSupplier.source_level),
          required: parseLooseBoolean(snapSupplier.required ?? true),
        }
      : null;

  const supplierAssociated =
    Boolean(supplierPromptConfigured) ||
    Boolean(
      asRecord(asRecord(input.identification_execution)?.supplier_extraction_profile)?.supplier_id,
    );
  const supplierPromptMissingAlert =
    promptTabMode === 'fallback' &&
    supplierAssociated &&
    ((fallbackUsed && supplierPromptExecuted?.loaded === false) ||
      (fallbackUsed &&
        Boolean(executedPromptContent) &&
        !Boolean(executedPromptContent?.includes('[SUPPLIER CUSTOM INSTRUCTIONS]'))) ||
      (supplierPromptConfigured?.required === true && !supplierPromptConfigured.content));

  return {
    requestedMode: requested,
    executedStrategy,
    currentStageLabel: formatCurrentStageLabel(input.current_stage, executedStrategy),
    usesExternalLlm,
    showProviderModelRows,
    showFallbackConfiguredRows,
    showPromptTab: promptTabMode !== 'hidden',
    externalProviderUsedLabel: fallbackUsed || (isLegacy && usesExternalLlm) ? 'yes' : 'no',
    fallbackUsed,
    fallbackConfigured,
    configured,
    executed,
    fallbackProvider: configured.provider,
    fallbackModel: configured.model,
    fallbackPromptKey: configured.promptKey,
    fallbackPromptVersion: configured.promptVersion,
    displayProvider,
    displayModel,
    displayPromptKey,
    historicalMetadataWarning: metadataInconsistencyReasons.length > 0,
    metadataInconsistencyReasons,
    promptTabMode,
    promptConfiguredLabel,
    promptExecutedLabel,
    executedPromptContent,
    executedPromptSha256,
    promptContentAvailability,
    supplierPromptConfigured,
    supplierPromptExecuted,
    supplierPromptMissingAlert,
  };
}

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
