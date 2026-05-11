/**
 * Resolve human-facing LLM provider identity from execution-log request payloads.
 */

import type { TFunction } from 'i18next';
import type { ExecutionLogEvent } from '../api/types';
import type { ProviderRequestLogPayload } from './parseExecutionLogProviderRequest';

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

/**
 * Resolves a stable provider key (slug) for titling, using the same precedence as the product spec.
 */
export function resolveExecutionLogProviderKey(
  event: ExecutionLogEvent,
  parsed: ProviderRequestLogPayload
): string {
  const pip = parsed.pipeline_provider?.trim().toLowerCase();
  if (pip) return pip;
  const prov = parsed.provider?.trim().toLowerCase();
  if (prov) return prov;
  const comp = parsed.prompt_composition;
  if (comp) {
    const rlk = comp.resolved_llm_provider_key;
    if (typeof rlk === 'string' && rlk.trim()) return rlk.trim().toLowerCase();
    const lid = comp.llm_identity;
    const lidRec = asRecord(lid);
    if (lidRec) {
      const pn = asString(lidRec.provider_name);
      if (pn) return pn.trim().toLowerCase();
    }
  }
  if (parsed.event_type === 'gemini_request') return 'gemini';
  const raw = asRecord(event.payload);
  const et = raw ? asString(raw.event_type) : null;
  if (et === 'gemini_request') return 'gemini';
  return '';
}

/** Short brand label for section titles (proper nouns where applicable). */
export function formatProviderBrandLabel(rawKey: string): string {
  const k = rawKey.trim().toLowerCase();
  if (!k) return '';
  if (k === 'gemini') return 'Gemini';
  if (k === 'claude' || k === 'anthropic') return 'Claude';
  if (k === 'openai') return 'OpenAI';
  if (k === 'deepseek') return 'DeepSeek';
  if (k === 'azure_openai' || k === 'azure-openai') return 'Azure OpenAI';
  const spaced = rawKey.replace(/[_-]+/g, ' ').trim();
  if (!spaced) return '';
  return spaced.charAt(0).toUpperCase() + spaced.slice(1).toLowerCase();
}

/** Section title above a parsed provider request card (Spanish via ``t``). */
export function buildProviderRequestPaperTitle(
  t: TFunction,
  event: ExecutionLogEvent,
  parsed: ProviderRequestLogPayload,
  requestIndex: number,
  requestCount: number
): string {
  const slug = resolveExecutionLogProviderKey(event, parsed);
  const brand = formatProviderBrandLabel(slug);
  if (brand) {
    return requestCount > 1
      ? t('execution_log.provider_request_title_named_n', { name: brand, n: requestIndex + 1 })
      : t('execution_log.provider_request_title_named', { name: brand });
  }
  return requestCount > 1
    ? t('execution_log.provider_request_title_generic_n', { n: requestIndex + 1 })
    : t('execution_log.provider_request_title_generic');
}
