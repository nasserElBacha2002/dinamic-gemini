/**
 * Parses execution-log payloads that describe an LLM request (Gemini legacy or hybrid analysis_request).
 */

import type { ExecutionLogEvent } from '../api/types';

export interface AttachmentSummarySlice {
  primary_evidence_count?: number;
  visual_reference_count?: number;
  total_count?: number;
}

export interface GeminiAttachmentSlice {
  role?: string;
  frame_ref?: string | null;
  reference_id?: string | null;
  filename?: string | null;
  mime_type?: string | null;
  resolved?: boolean;
}

export type ProviderRequestEventType = 'gemini_request' | 'analysis_request';

export interface ProviderRequestLogPayload {
  event_type: ProviderRequestEventType;
  prompt_text?: string;
  prompt_text_sha256?: string;
  prompt_text_len?: number;
  /** Optional wire-level provider hint (legacy gemini_request payloads). */
  provider?: string;
  pipeline_provider?: string;
  context_instruction?: string | null;
  attachment_summary?: AttachmentSummarySlice;
  primary_evidence_attachments?: GeminiAttachmentSlice[];
  visual_reference_attachments?: GeminiAttachmentSlice[];
  prompt_composition?: Record<string, unknown> | null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function asAttachments(value: unknown): GeminiAttachmentSlice[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => asRecord(item))
    .filter((item): item is Record<string, unknown> => item != null)
    .map((item) => ({
      role: asString(item.role) ?? undefined,
      frame_ref: asString(item.frame_ref) ?? undefined,
      reference_id: asString(item.reference_id) ?? undefined,
      filename: asString(item.filename) ?? undefined,
      mime_type: asString(item.mime_type) ?? undefined,
      resolved: typeof item.resolved === 'boolean' ? item.resolved : undefined,
    }));
}

/**
 * Returns structured request metadata when the payload is a known provider request shape.
 */
export function parseProviderRequestPayload(event: ExecutionLogEvent): ProviderRequestLogPayload | null {
  const payload = asRecord(event.payload);
  if (!payload) return null;
  const et = asString(payload.event_type);
  if (et !== 'gemini_request' && et !== 'analysis_request') return null;

  const summary = asRecord(payload.attachment_summary);
  const compRaw = payload.prompt_composition;
  const prompt_composition =
    compRaw != null && typeof compRaw === 'object' && !Array.isArray(compRaw)
      ? (compRaw as Record<string, unknown>)
      : null;

  return {
    event_type: et,
    prompt_text: asString(payload.prompt_text) ?? undefined,
    prompt_text_sha256: asString(payload.prompt_text_sha256) ?? undefined,
    prompt_text_len: asNumber(payload.prompt_text_len) ?? undefined,
    provider: asString(payload.provider) ?? undefined,
    pipeline_provider: asString(payload.pipeline_provider) ?? undefined,
    context_instruction: asString(payload.context_instruction),
    attachment_summary: summary
      ? {
          primary_evidence_count: asNumber(summary.primary_evidence_count) ?? undefined,
          visual_reference_count: asNumber(summary.visual_reference_count) ?? undefined,
          total_count: asNumber(summary.total_count) ?? undefined,
        }
      : undefined,
    primary_evidence_attachments: asAttachments(payload.primary_evidence_attachments),
    visual_reference_attachments: asAttachments(payload.visual_reference_attachments),
    prompt_composition,
  };
}
