/**
 * Execution log panel — operator-facing processing log with optional enriched filters.
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  Divider,
  FormControl,
  InputLabel,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Typography,
} from '@mui/material';
import type {
  AisleExecutionLogResponse,
  ExecutionLogEvent,
  ExecutionLogPanelLog,
} from '../api/types';
import i18n from '../i18n';

const JOB_FILTER_REQUESTED = '__job_filter_requested__';
const JOB_FILTER_ALL = '__job_filter_all__';

/** Derive a readable error message from unknown query/API error shape. */
function getReadableErrorMessage(error: unknown): string {
  if (error == null) return i18n.t('execution_log.unknown_error');
  if (typeof error === 'string') return error;
  if (error instanceof Error) return error.message;
  if (typeof error === 'object' && error !== null && 'message' in error) {
    const m = (error as { message?: unknown }).message;
    if (typeof m === 'string') return m;
  }
  try {
    return String(error);
  } catch {
    return i18n.t('execution_log.unknown_error');
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

function shouldShowPayloadLine(payload: unknown): boolean {
  if (payload == null) return false;
  if (typeof payload !== 'object') return true;
  if (Array.isArray(payload)) return true;
  return Object.keys(payload as object).length > 0;
}

function safePayloadString(payload: unknown): string {
  if (payload == null) return '';
  if (typeof payload === 'object') {
    try {
      return JSON.stringify(payload);
    } catch {
      return i18n.t('execution_log.payload_unreadable');
    }
  }
  try {
    return JSON.stringify(payload);
  } catch {
    return String(payload);
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
  const id =
    item.reference_id ?? item.frame_ref ?? item.role ?? i18n.t('execution_log.attachment_id_fallback');
  const filename = item.filename ?? i18n.t('execution_log.unknown_file');
  const mime = item.mime_type ? ` (${item.mime_type})` : '';
  const resolved =
    item.role === 'visual_reference' && item.resolved === false
      ? i18n.t('execution_log.not_resolved_suffix')
      : '';
  return `${id}: ${filename}${mime}${resolved}`;
}

function shortJobLabel(id: string): string {
  const s = id.trim();
  if (s.length <= 14) return s;
  return `${s.slice(0, 8)}…${s.slice(-4)}`;
}

function isAisleAggregateLog(log: ExecutionLogPanelLog): log is AisleExecutionLogResponse {
  return 'jobs' in log && Array.isArray((log as AisleExecutionLogResponse).jobs);
}

function jobMenuItemLabel(jid: string, log: ExecutionLogPanelLog): string {
  if (isAisleAggregateLog(log)) {
    const row = log.jobs.find((j) => j.job_id === jid);
    if (row) {
      const head = [row.provider_name, row.model_name]
        .filter((x) => x != null && String(x).trim() !== '')
        .join(' · ');
      if (head) return `${head} · ${shortJobLabel(jid)}`;
    }
  }
  return shortJobLabel(jid);
}

function timelineRowKey(evt: ExecutionLogEvent, index: number): string {
  return [
    evt.ts,
    evt.stage,
    evt.level,
    evt.message,
    evt.event_job_id ?? '',
    evt.event_attempt ?? '',
    evt.event_execution_id ?? '',
    String(index),
  ].join('|');
}

interface ExecutionLogPanelProps {
  log?: ExecutionLogPanelLog | null;
  events?: ExecutionLogEvent[];
  isLoading?: boolean;
  error?: unknown;
  emptyMessage?: string;
}

export default function ExecutionLogPanel({
  log,
  events: eventsProp,
  isLoading,
  error,
  emptyMessage: emptyMessageProp,
}: ExecutionLogPanelProps) {
  const { t } = useTranslation();
  const emptyMessage = emptyMessageProp ?? t('execution_log.empty_default');
  const allEvents = useMemo(() => log?.events ?? eventsProp ?? [], [log?.events, eventsProp]);
  const haveEnvelope = Boolean(log);
  const aisleMode = Boolean(log && isAisleAggregateLog(log));

  const hasPayloadJobIds = useMemo(
    () => allEvents.some((e) => e.event_job_id != null && String(e.event_job_id).trim() !== ''),
    [allEvents]
  );

  const showJobFilter = Boolean(
    haveEnvelope && log && hasPayloadJobIds && log.available_job_ids.length > 1
  );

  const [jobFilter, setJobFilter] = useState<string>(JOB_FILTER_REQUESTED);
  const [attemptKey, setAttemptKey] = useState<string>('all');
  const [executionKey, setExecutionKey] = useState<string>('all');

  const defaultJobFilter = log && isAisleAggregateLog(log) ? JOB_FILTER_ALL : JOB_FILTER_REQUESTED;

  const resolvedJobFilter = useMemo(() => {
    if (haveEnvelope && log && isAisleAggregateLog(log) && jobFilter === JOB_FILTER_REQUESTED) {
      return JOB_FILTER_ALL;
    }
    if (jobFilter !== JOB_FILTER_REQUESTED && jobFilter !== JOB_FILTER_ALL) {
      if (!haveEnvelope || !log || !hasPayloadJobIds || !log.available_job_ids.includes(jobFilter)) {
        return defaultJobFilter;
      }
    }
    return jobFilter;
  }, [haveEnvelope, log, jobFilter, hasPayloadJobIds, defaultJobFilter]);

  const eventsAfterJobFilter = useMemo(() => {
    if (!haveEnvelope || !log) return allEvents;
    if (!hasPayloadJobIds) return allEvents;
    if (!showJobFilter) return allEvents;
    if (resolvedJobFilter === JOB_FILTER_REQUESTED) {
      if (log && isAisleAggregateLog(log)) return allEvents;
      return allEvents.filter((e) => e.is_requested_job_event === true);
    }
    if (resolvedJobFilter === JOB_FILTER_ALL) {
      return allEvents;
    }
    return allEvents.filter((e) => e.event_job_id === resolvedJobFilter);
  }, [allEvents, haveEnvelope, log, hasPayloadJobIds, showJobFilter, resolvedJobFilter]);

  const { contextualAttempts, contextualExecutionIds } = useMemo(() => {
    const att = new Set<number>();
    const ex = new Set<string>();
    for (const e of eventsAfterJobFilter) {
      if (e.event_attempt != null) att.add(e.event_attempt);
      if (e.event_execution_id != null && String(e.event_execution_id).trim() !== '') {
        ex.add(String(e.event_execution_id));
      }
    }
    return {
      contextualAttempts: [...att].sort((a, b) => a - b),
      contextualExecutionIds: [...ex].sort(),
    };
  }, [eventsAfterJobFilter]);

  const resolvedAttemptKey =
    attemptKey !== 'all' && !contextualAttempts.includes(Number(attemptKey)) ? 'all' : attemptKey;
  const resolvedExecutionKey =
    executionKey !== 'all' && !contextualExecutionIds.includes(executionKey) ? 'all' : executionKey;

  const filteredEvents = useMemo(() => {
    let rows = eventsAfterJobFilter;
    if (resolvedAttemptKey !== 'all') {
      const n = Number(resolvedAttemptKey);
      rows = rows.filter((e) => e.event_attempt === n);
    }
    if (resolvedExecutionKey !== 'all') {
      rows = rows.filter((e) => e.event_execution_id === resolvedExecutionKey);
    }
    return rows;
  }, [eventsAfterJobFilter, resolvedAttemptKey, resolvedExecutionKey]);

  const attemptSelectDisabled = contextualAttempts.length <= 1;
  const showExecutionFilter = contextualExecutionIds.length > 1;

  const handleJobFilterChange = (value: string) => {
    setJobFilter(value);
    setAttemptKey('all');
    setExecutionKey('all');
  };

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
        {t('execution_log.load_failed', { message: getReadableErrorMessage(error) })}
      </Typography>
    );
  }
  const jobIdsForMenu =
    haveEnvelope && log
      ? aisleMode
        ? log.available_job_ids
        : log.available_job_ids.filter((jid) => jid !== log.requested_job_id)
      : [];

  if (!allEvents.length) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ p: 1 }}>
        {emptyMessage}
      </Typography>
    );
  }

  const parsedEvents = filteredEvents.map((evt) => ({
    event: evt,
    geminiRequest: parseGeminiRequestPayload(evt),
  }));
  const geminiRequests = parsedEvents.filter(
    (entry): entry is { event: ExecutionLogEvent; geminiRequest: GeminiRequestPayload } =>
      entry.geminiRequest != null
  );
  const timelineEvents = parsedEvents
    .filter((entry) => entry.geminiRequest == null)
    .map((entry) => entry.event);

  const summaryParts: string[] = [];
  summaryParts.push(
    t('execution_log.summary_visible', { visible: filteredEvents.length, total: allEvents.length }),
  );
  if (haveEnvelope && log) {
    if (isAisleAggregateLog(log)) {
      const nJobs = log.jobs?.length ?? 0;
      const provs = new Set(
        (log.jobs ?? []).map((j) => j.provider_name).filter((p): p is string => Boolean(p && String(p).trim()))
      );
      summaryParts.push(t('execution_log.summary_aisle', { jobs: nJobs, providers: provs.size }));
    } else {
      summaryParts.push(t('execution_log.summary_requested', { id: shortJobLabel(log.requested_job_id) }));
    }
    if (hasPayloadJobIds) {
      if (resolvedJobFilter === JOB_FILTER_REQUESTED) summaryParts.push(t('execution_log.filter_requested'));
      else if (resolvedJobFilter === JOB_FILTER_ALL) summaryParts.push(t('execution_log.filter_all'));
      else summaryParts.push(t('execution_log.filter_job', { label: jobMenuItemLabel(resolvedJobFilter, log) }));
    }
    if (resolvedAttemptKey !== 'all')
      summaryParts.push(t('execution_log.attempt_summary', { attempt: resolvedAttemptKey }));
    if (resolvedExecutionKey !== 'all')
      summaryParts.push(t('execution_log.execution_summary', { id: shortJobLabel(resolvedExecutionKey) }));
  }

  const requestedJobId = log && !isAisleAggregateLog(log) ? log.requested_job_id : null;
  const logSourceIssues =
    aisleMode && log && isAisleAggregateLog(log)
      ? log.log_sources.filter((s) => s.status !== 'ok')
      : [];

  return (
    <Box sx={{ display: 'grid', gap: 2 }}>
      {haveEnvelope && log ? (
        <>
          {!hasPayloadJobIds ? (
            <Alert severity="info" variant="outlined" sx={{ py: 0.5 }}>
              {t('execution_log.job_metadata_unavailable')}
            </Alert>
          ) : null}
          {logSourceIssues.length ? (
            <Alert severity="warning" variant="outlined" sx={{ py: 0.5 }}>
              {t('execution_log.log_sources_warning', { count: logSourceIssues.length })}
            </Alert>
          ) : null}
          <Box
            sx={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 1.5,
              alignItems: 'flex-end',
            }}
          >
            {showJobFilter ? (
              <FormControl size="small" sx={{ minWidth: 200 }}>
                <InputLabel id="exec-log-job-filter-label">{t('execution_log.pick_job')}</InputLabel>
                <Select
                  labelId="exec-log-job-filter-label"
                  label={t('execution_log.pick_job')}
                  value={
                    resolvedJobFilter === JOB_FILTER_REQUESTED || resolvedJobFilter === JOB_FILTER_ALL
                      ? resolvedJobFilter
                      : log.available_job_ids.includes(resolvedJobFilter)
                        ? resolvedJobFilter
                        : aisleMode
                          ? JOB_FILTER_ALL
                          : JOB_FILTER_REQUESTED
                  }
                  onChange={(e) => handleJobFilterChange(e.target.value)}
                >
                  {!aisleMode ? <MenuItem value={JOB_FILTER_REQUESTED}>{t('execution_log.requested_job')}</MenuItem> : null}
                  <MenuItem value={JOB_FILTER_ALL}>{t('execution_log.all_jobs')}</MenuItem>
                  {jobIdsForMenu.map((jid) => (
                    <MenuItem key={jid} value={jid}>
                      {jobMenuItemLabel(jid, log)}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            ) : null}
            <FormControl size="small" sx={{ minWidth: 160 }} disabled={attemptSelectDisabled}>
              <InputLabel id="exec-log-attempt-label">{t('execution_log.attempt')}</InputLabel>
              <Select
                labelId="exec-log-attempt-label"
                label={t('execution_log.attempt')}
                value={attemptSelectDisabled ? 'all' : resolvedAttemptKey}
                onChange={(e) => setAttemptKey(e.target.value)}
              >
                <MenuItem value="all">{t('execution_log.all_attempts')}</MenuItem>
                {contextualAttempts.map((a) => (
                  <MenuItem key={a} value={String(a)}>
                    {a}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            {showExecutionFilter ? (
              <FormControl size="small" sx={{ minWidth: 200 }}>
                <InputLabel id="exec-log-exec-label">{t('execution_log.execution_id')}</InputLabel>
                <Select
                  labelId="exec-log-exec-label"
                  label={t('execution_log.execution_id')}
                  value={resolvedExecutionKey}
                  onChange={(e) => setExecutionKey(e.target.value)}
                >
                  <MenuItem value="all">{t('results.filters.all')}</MenuItem>
                  {contextualExecutionIds.map((id) => (
                    <MenuItem key={id} value={id}>
                      {shortJobLabel(id)}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            ) : null}
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
            {summaryParts.join(' · ')}
          </Typography>
        </>
      ) : null}

      {geminiRequests.map(({ event, geminiRequest }, requestIndex) => (
        <Paper
          key={`g|${event.ts}|${event.stage}|${requestIndex}|${event.message.slice(0, 64)}`}
          variant="outlined"
          sx={{ p: 2, display: 'grid', gap: 1.5 }}
        >
          <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap' }}>
            <Typography variant="subtitle2">
              {geminiRequests.length > 1
                ? t('execution_log.gemini_request_n', { n: requestIndex + 1 })
                : t('execution_log.gemini_request')}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {formatTs(event.ts)}
            </Typography>
          </Box>

          <Box>
            <Typography variant="subtitle2">{t('execution_log.prompt_heading')}</Typography>
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
              {geminiRequest.prompt_text ?? t('execution_log.prompt_missing')}
            </Box>
          </Box>

          {geminiRequest.context_instruction ? (
            <Box>
              <Typography variant="subtitle2">{t('execution_log.reference_guidance')}</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, whiteSpace: 'pre-wrap' }}>
                {geminiRequest.context_instruction}
              </Typography>
            </Box>
          ) : null}

          <Divider />

          <Box sx={{ display: 'grid', gap: 1.25 }}>
            <Typography variant="subtitle2">{t('execution_log.attached_files')}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t('execution_log.attachment_counts', {
                primary: geminiRequest.attachment_summary?.primary_evidence_count ?? 0,
                refs: geminiRequest.attachment_summary?.visual_reference_count ?? 0,
                total: geminiRequest.attachment_summary?.total_count ?? 0,
              })}
            </Typography>

            <Box>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {t('execution_log.primary_evidence')}
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
                  {t('execution_log.no_primary_evidence')}
                </Typography>
              )}
            </Box>

            <Box>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {t('execution_log.reference_images')}
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
                  {t('execution_log.no_reference_images')}
                </Typography>
              )}
            </Box>
          </Box>
        </Paper>
      ))}

      <List dense disablePadding sx={{ maxHeight: 360, overflow: 'auto' }}>
        {timelineEvents.map((evt, i) => {
          const ej = evt.event_job_id;
          const showJobBadge = hasPayloadJobIds && Boolean(ej);
          const definitiveRequestedRow =
            !aisleMode &&
            hasPayloadJobIds &&
            requestedJobId != null &&
            ej != null &&
            String(ej) === String(requestedJobId);
          const showThisJobChip = definitiveRequestedRow;
          const emphasizeRow = definitiveRequestedRow;

          return (
            <ListItem
              key={timelineRowKey(evt, i)}
              alignItems="flex-start"
              disableGutters
              sx={{
                py: 0.5,
                pl: 0.5,
                borderLeft: emphasizeRow ? 3 : 0,
                borderColor: emphasizeRow ? 'primary.main' : 'transparent',
              }}
            >
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
                    <Chip label={evt.level} size="small" color={levelColor(evt.level)} sx={{ fontSize: '0.65rem' }} />
                    {showJobBadge ? (
                      <Chip
                        label={t('execution_log.chip_job', { id: shortJobLabel(String(ej)) })}
                        size="small"
                        variant="outlined"
                        color={definitiveRequestedRow ? 'primary' : 'default'}
                        sx={{ fontSize: '0.65rem' }}
                      />
                    ) : null}
                    {evt.event_attempt != null ? (
                      <Chip
                        label={t('execution_log.chip_att', { n: evt.event_attempt })}
                        size="small"
                        variant="outlined"
                        sx={{ fontSize: '0.65rem' }}
                      />
                    ) : null}
                    {evt.event_execution_id ? (
                      <Chip
                        label={t('execution_log.chip_exec', { id: shortJobLabel(evt.event_execution_id) })}
                        size="small"
                        variant="outlined"
                        sx={{ fontSize: '0.65rem' }}
                      />
                    ) : null}
                    {showThisJobChip ? (
                      <Chip label={t('jobs.this_job')} size="small" color="primary" sx={{ fontSize: '0.6rem' }} />
                    ) : null}
                  </Box>
                }
                secondary={
                  <>
                    <Typography variant="body2" component="span" sx={{ display: 'block', mt: 0.25 }}>
                      {evt.message}
                    </Typography>
                    {shouldShowPayloadLine(evt.payload) ? (
                      <Typography
                        variant="caption"
                        component="span"
                        sx={{ display: 'block', color: 'text.secondary', fontFamily: 'monospace' }}
                      >
                        {safePayloadString(evt.payload)}
                      </Typography>
                    ) : null}
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
          );
        })}
      </List>
    </Box>
  );
}
