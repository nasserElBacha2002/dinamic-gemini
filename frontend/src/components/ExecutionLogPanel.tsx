/**
 * Execution log panel (v3.1.1) — operator-facing processing log.
 * Shows timestamp, level, stage, message; highlights errors.
 * Error prop is typed as unknown for safe handling of API/query error shapes.
 */

import {
  Box,
  Chip,
  CircularProgress,
  Divider,
  List,
  ListItem,
  ListItemText,
  Paper,
  Typography,
} from '@mui/material';
import type { ExecutionLogEvent } from '../api/types';

/** Derive a readable error message from unknown query/API error shape. */
export function getReadableErrorMessage(error: unknown): string {
  if (error == null) return 'Unknown error';
  if (typeof error === 'string') return error;
  if (error instanceof Error) return error.message;
  if (typeof error === 'object' && error !== null && 'message' in error) {
    const m = (error as { message?: unknown }).message;
    if (typeof m === 'string') return m;
  }
  try {
    return String(error);
  } catch {
    return 'Unknown error';
  }
}

function formatTs(ts: string): string {
  try {
    const d = new Date(ts);
    return Number.isNaN(d.getTime()) ? ts : d.toLocaleString();
  } catch {
    return ts;
  }
}

function levelColor(level: string): 'default' | 'warning' | 'error' | 'success' {
  switch (level.toLowerCase()) {
    case 'error':
      return 'error';
    case 'warning':
      return 'warning';
    case 'info':
    default:
      return 'default';
  }
}

function safePayloadString(payload: Record<string, unknown> | null | undefined): string {
  if (!payload || typeof payload !== 'object') return '';
  try {
    return JSON.stringify(payload);
  } catch {
    return '[unable to display payload]';
  }
}

interface AttachmentSummary {
  primary_evidence_count?: number;
  visual_reference_count?: number;
  total_count?: number;
}

interface GeminiAttachment {
  role?: string;
  frame_ref?: string | null;
  reference_id?: string | null;
  filename?: string | null;
  mime_type?: string | null;
  resolved?: boolean;
}

interface GeminiRequestPayload {
  event_type?: string;
  prompt_text?: string;
  context_instruction?: string | null;
  attachment_summary?: AttachmentSummary;
  primary_evidence_attachments?: GeminiAttachment[];
  visual_reference_attachments?: GeminiAttachment[];
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

function asAttachments(value: unknown): GeminiAttachment[] {
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

function parseGeminiRequestPayload(event: ExecutionLogEvent): GeminiRequestPayload | null {
  const payload = asRecord(event.payload);
  if (!payload || payload.event_type !== 'gemini_request') return null;
  const summary = asRecord(payload.attachment_summary);
  return {
    event_type: 'gemini_request',
    prompt_text: asString(payload.prompt_text) ?? undefined,
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
  };
}

function formatAttachmentLabel(item: GeminiAttachment): string {
  const id = item.reference_id ?? item.frame_ref ?? item.role ?? 'attachment';
  const filename = item.filename ?? 'unknown file';
  const mime = item.mime_type ? ` (${item.mime_type})` : '';
  const resolved = item.role === 'visual_reference' && item.resolved === false ? ' [not resolved]' : '';
  return `${id}: ${filename}${mime}${resolved}`;
}

interface ExecutionLogPanelProps {
  events: ExecutionLogEvent[];
  isLoading?: boolean;
  /** Query/API error; typed unknown so panel never crashes on unexpected shape. */
  error?: unknown;
  emptyMessage?: string;
}

export default function ExecutionLogPanel({
  events,
  isLoading,
  error,
  emptyMessage = 'No log entries yet.',
}: ExecutionLogPanelProps) {
  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
        <CircularProgress size={24} />
      </Box>
    );
  }
  if (error != null) {
    return (
      <Typography color="error" variant="body2" sx={{ p: 1 }}>
        Failed to load log: {getReadableErrorMessage(error)}
      </Typography>
    );
  }
  if (!events || events.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ p: 1 }}>
        {emptyMessage}
      </Typography>
    );
  }
  const parsedEvents = events.map((evt) => ({
    event: evt,
    geminiRequest: parseGeminiRequestPayload(evt),
  }));
  const geminiRequests = parsedEvents
    .filter((entry): entry is { event: ExecutionLogEvent; geminiRequest: GeminiRequestPayload } => entry.geminiRequest != null);
  const timelineEvents = parsedEvents
    .filter((entry) => entry.geminiRequest == null)
    .map((entry) => entry.event);
  return (
    <Box sx={{ display: 'grid', gap: 2 }}>
      {geminiRequests.map(({ event, geminiRequest }, requestIndex) => (
        <Paper key={`${event.ts}-${requestIndex}`} variant="outlined" sx={{ p: 2, display: 'grid', gap: 1.5 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap' }}>
            <Typography variant="subtitle2">
              Gemini request{geminiRequests.length > 1 ? ` ${requestIndex + 1}` : ''}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {formatTs(event.ts)}
            </Typography>
          </Box>

          <Box>
            <Typography variant="subtitle2">Prompt</Typography>
            <Box
              component="pre"
              sx={{
                m: 0,
                mt: 0.75,
                py: 1,
                px: 1.25,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                fontFamily: 'monospace',
                fontSize: '0.875rem',
                maxHeight: 240,
                overflow: 'auto',
                borderRadius: 1,
                bgcolor: 'action.hover',
              }}
            >
              {geminiRequest.prompt_text ?? 'Prompt not available.'}
            </Box>
          </Box>

          {geminiRequest.context_instruction ? (
            <Box>
              <Typography variant="subtitle2">Reference guidance</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, whiteSpace: 'pre-wrap' }}>
                {geminiRequest.context_instruction}
              </Typography>
            </Box>
          ) : null}

          <Divider />

          <Box sx={{ display: 'grid', gap: 1.25 }}>
            <Typography variant="subtitle2">Attached files</Typography>
            <Typography variant="body2" color="text.secondary">
              Primary evidence: {geminiRequest.attachment_summary?.primary_evidence_count ?? 0} | Reference images:{' '}
              {geminiRequest.attachment_summary?.visual_reference_count ?? 0} | Total:{' '}
              {geminiRequest.attachment_summary?.total_count ?? 0}
            </Typography>

            <Box>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                Primary evidence
              </Typography>
              {geminiRequest.primary_evidence_attachments?.length ? (
                <List dense disablePadding>
                  {geminiRequest.primary_evidence_attachments.map((item, index) => (
                    <ListItem key={`primary-${requestIndex}-${index}`} disableGutters sx={{ py: 0.25 }}>
                      <ListItemText primary={formatAttachmentLabel(item)} />
                    </ListItem>
                  ))}
                </List>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  No primary evidence attachments recorded.
                </Typography>
              )}
            </Box>

            <Box>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                Reference images
              </Typography>
              {geminiRequest.visual_reference_attachments?.length ? (
                <List dense disablePadding>
                  {geminiRequest.visual_reference_attachments.map((item, index) => (
                    <ListItem key={`reference-${requestIndex}-${index}`} disableGutters sx={{ py: 0.25 }}>
                      <ListItemText primary={formatAttachmentLabel(item)} />
                    </ListItem>
                  ))}
                </List>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  No reference images were attached to this Gemini request.
                </Typography>
              )}
            </Box>
          </Box>
        </Paper>
      ))}

      <List dense disablePadding sx={{ maxHeight: 360, overflow: 'auto' }}>
        {timelineEvents.map((evt, i) => (
          <ListItem key={i} alignItems="flex-start" disableGutters sx={{ py: 0.25 }}>
            <ListItemText
              primary={
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexWrap: 'wrap' }}>
                  <Typography component="span" variant="caption" color="text.secondary">
                    {formatTs(evt.ts)}
                  </Typography>
                  <Chip
                    label={evt.stage}
                    size="small"
                    variant="outlined"
                    sx={{ fontFamily: 'monospace', fontSize: '0.7rem' }}
                  />
                  <Chip
                    label={evt.level}
                    size="small"
                    color={levelColor(evt.level)}
                    sx={{ fontSize: '0.65rem' }}
                  />
                </Box>
              }
              secondary={
                <>
                  <Typography variant="body2" component="span" sx={{ display: 'block', mt: 0.25 }}>
                    {evt.message}
                  </Typography>
                  {evt.payload && typeof evt.payload === 'object' && Object.keys(evt.payload).length > 0 && (
                    <Typography
                      variant="caption"
                      component="span"
                      sx={{ display: 'block', color: 'text.secondary', fontFamily: 'monospace' }}
                    >
                      {safePayloadString(evt.payload as Record<string, unknown>)}
                    </Typography>
                  )}
                </>
              }
              primaryTypographyProps={{ component: 'div' }}
              secondaryTypographyProps={{ component: 'div' }}
              sx={{
                '& .MuiListItemText-secondary': {
                  color: evt.level === 'error' ? 'error.main' : undefined,
                },
              }}
            />
          </ListItem>
        ))}
      </List>
    </Box>
  );
}
