/**
 * Observability extras: retry chain, artifacts, paged timeline/logs/errors for one job.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  Stack,
  Typography,
} from '@mui/material';
import {
  downloadJobArtifact,
  getExecutionLogPage,
  getJobArtifacts,
  getJobErrors,
  getJobHybridReport,
  getJobRetryChain,
  getJobTimeline,
} from '../api/jobsApi';
import type {
  ExecutionLogEvent,
  JobArtifact,
  JobErrorItem,
  JobRetryChain,
  JobTimelineEvent,
} from '../api/types';
import { ApiError } from '../api/types';
import { resolveApiErrorMessage } from '../utils/apiErrors';
import { ErrorAlert, useAppSnackbar } from './ui';

export interface JobObservabilityDiagnosticsPanelProps {
  inventoryId: string;
  aisleId: string;
  jobId: string;
  active: boolean;
  onSelectAttempt?: (jobId: string) => void;
}

export default function JobObservabilityDiagnosticsPanel({
  inventoryId,
  aisleId,
  jobId,
  active,
  onSelectAttempt,
}: JobObservabilityDiagnosticsPanelProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const [chain, setChain] = useState<JobRetryChain | null>(null);
  const [artifacts, setArtifacts] = useState<JobArtifact[]>([]);
  const [timeline, setTimeline] = useState<JobTimelineEvent[]>([]);
  const [logItems, setLogItems] = useState<ExecutionLogEvent[]>([]);
  const [logCursor, setLogCursor] = useState<string | null>(null);
  const [logHasMore, setLogHasMore] = useState(false);
  const [errors, setErrors] = useState<JobErrorItem[]>([]);
  const [hybridOk, setHybridOk] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const loadCore = useCallback(async () => {
    if (!active || !jobId) return;
    setLoading(true);
    setError(null);
    try {
      const [chainRes, artRes, tlRes, errRes, logRes] = await Promise.all([
        getJobRetryChain(inventoryId, aisleId, jobId),
        getJobArtifacts(inventoryId, aisleId, jobId, { limit: 100 }),
        getJobTimeline(inventoryId, aisleId, jobId, { limit: 100 }),
        getJobErrors(inventoryId, aisleId, jobId, { limit: 50 }),
        getExecutionLogPage(inventoryId, aisleId, jobId, { limit: 100, sort_order: 'asc' }),
      ]);
      setChain(chainRes);
      setArtifacts(artRes.items);
      setTimeline(tlRes.items);
      setErrors(errRes.items);
      setLogItems(logRes.items);
      setLogCursor(logRes.page.next_cursor ?? null);
      setLogHasMore(Boolean(logRes.page.has_more));
      try {
        await getJobHybridReport(inventoryId, aisleId, jobId);
        setHybridOk(true);
      } catch {
        setHybridOk(false);
      }
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [active, aisleId, inventoryId, jobId]);

  useEffect(() => {
    void loadCore();
  }, [loadCore]);

  const loadMoreLogs = async () => {
    if (!logCursor) return;
    try {
      const page = await getExecutionLogPage(inventoryId, aisleId, jobId, {
        cursor: logCursor,
        limit: 100,
      });
      setLogItems((prev) => [...prev, ...page.items]);
      setLogCursor(page.page.next_cursor ?? null);
      setLogHasMore(Boolean(page.page.has_more));
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      showSnackbar(resolveApiErrorMessage(err, 'errors.load_execution_log'), 'error');
    }
  };

  if (!jobId) {
    return (
      <Typography variant="body2" color="text.secondary">
        {t('jobs.obs_choose_job_for_log')}
      </Typography>
    );
  }

  if (loading) {
    return (
      <Box sx={{ py: 3, display: 'flex', justifyContent: 'center' }}>
        <CircularProgress size={28} />
      </Box>
    );
  }

  if (error) {
    return (
      <ErrorAlert
        message={resolveApiErrorMessage(error, 'errors.load_job_details')}
        onRetry={() => {
          void loadCore();
        }}
      />
    );
  }

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="subtitle2" gutterBottom>
          {t('jobs.obs_tab_retry_chain')}
        </Typography>
        {!chain || chain.attempts.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {t('jobs.obs_retry_chain_empty')}
          </Typography>
        ) : (
          <Stack direction="row" flexWrap="wrap" gap={1}>
            {chain.attempts.map((a) => (
              <Chip
                key={a.job_id}
                size="small"
                color={a.is_current ? 'success' : a.is_selected ? 'primary' : 'default'}
                variant={a.is_selected ? 'filled' : 'outlined'}
                label={`${t('jobs.obs_attempt_chip', { n: a.attempt_number })} · ${a.status}`}
                onClick={() => onSelectAttempt?.(a.job_id)}
              />
            ))}
          </Stack>
        )}
      </Box>

      <Divider />

      <Box>
        <Typography variant="subtitle2" gutterBottom>
          {t('jobs.obs_tab_artifacts')}
        </Typography>
        {hybridOk === true ? (
          <Typography variant="caption" color="success.main" display="block" sx={{ mb: 1 }}>
            {t('jobs.obs_hybrid_report_available')}
          </Typography>
        ) : hybridOk === false ? (
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
            {t('jobs.obs_hybrid_report_missing')}
          </Typography>
        ) : null}
        {artifacts.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {t('jobs.obs_artifacts_empty')}
          </Typography>
        ) : (
          <Stack spacing={0.75}>
            {artifacts.map((a) => (
              <Box
                key={a.id}
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', sm: '1fr auto' },
                  gap: 0.5,
                  alignItems: 'center',
                }}
              >
                <Box>
                  <Typography variant="body2">
                    {a.display_name}{' '}
                    <Typography component="span" variant="caption" color="text.secondary">
                      ({a.category} · {a.kind} · {a.status})
                    </Typography>
                  </Typography>
                  {a.size_bytes != null ? (
                    <Typography variant="caption" color="text.secondary">
                      {a.size_bytes} B
                    </Typography>
                  ) : null}
                </Box>
                <Button
                  size="small"
                  disabled={!a.is_downloadable || a.status !== 'AVAILABLE'}
                  onClick={() => {
                    void downloadJobArtifact(
                      inventoryId,
                      aisleId,
                      jobId,
                      a.id,
                      a.original_filename || `${a.kind}.bin`
                    ).catch((e) => {
                      const err = e instanceof ApiError ? e : new ApiError(String(e));
                      showSnackbar(resolveApiErrorMessage(err, 'errors.download_job_log'), 'error');
                    });
                  }}
                >
                  {t('common.download')}
                </Button>
              </Box>
            ))}
          </Stack>
        )}
      </Box>

      <Divider />

      <Box>
        <Typography variant="subtitle2" gutterBottom>
          {t('jobs.obs_tab_timeline')}
        </Typography>
        {timeline.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {t('jobs.obs_timeline_empty')}
          </Typography>
        ) : (
          <Stack spacing={0.5} sx={{ maxHeight: 240, overflow: 'auto' }}>
            {timeline.map((ev) => (
              <Typography key={ev.id} variant="caption" component="div">
                [{ev.timestamp ?? '—'}] {ev.event_type} · {ev.stage ?? '—'} · {ev.message ?? ''}
              </Typography>
            ))}
          </Stack>
        )}
      </Box>

      <Divider />

      <Box>
        <Typography variant="subtitle2" gutterBottom>
          {t('jobs.obs_tab_paged_logs')}
        </Typography>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
          {t('jobs.obs_paged_logs_hint', { count: logItems.length })}
        </Typography>
        <Stack spacing={0.5} sx={{ maxHeight: 220, overflow: 'auto' }}>
          {logItems.map((ev, idx) => (
            <Typography key={`${ev.ts}-${idx}`} variant="caption" component="div">
              [{ev.ts}] {ev.level} · {ev.stage} · {ev.message}
            </Typography>
          ))}
        </Stack>
        {logHasMore ? (
          <Button size="small" sx={{ mt: 1 }} onClick={() => void loadMoreLogs()}>
            {t('jobs.obs_load_more_logs')}
          </Button>
        ) : null}
      </Box>

      <Divider />

      <Box>
        <Typography variant="subtitle2" gutterBottom>
          {t('jobs.obs_tab_errors')}
        </Typography>
        {errors.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {t('jobs.obs_errors_empty')}
          </Typography>
        ) : (
          <Stack spacing={0.75}>
            {errors.map((e) => (
              <Typography key={e.error_id} variant="body2">
                {e.error_code ?? 'ERROR'} · {e.stage ?? '—'} · {e.message ?? e.sanitized_detail ?? ''}
              </Typography>
            ))}
          </Stack>
        )}
      </Box>
    </Stack>
  );
}
