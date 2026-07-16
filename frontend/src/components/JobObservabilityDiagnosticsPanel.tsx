/**
 * Observability diagnostics: independent panels (retry, artifacts, timeline, logs, errors, hybrid).
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
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
  getJobArtifactPreview,
  getJobArtifacts,
  getJobErrors,
  getJobHybridReport,
  getJobRetryChain,
  getJobTimeline,
} from '../api/jobsApi';
import type {
  ArtifactPreview,
  ExecutionLogEvent,
  JobArtifact,
  JobErrorItem,
  JobRetryChain,
  JobTimelineEvent,
} from '../api/types';
import { ApiError } from '../api/types';
import { resolveApiErrorMessage } from '../utils/apiErrors';
import { ErrorAlert, useAppSnackbar } from './ui';

type PanelState<T> = {
  data: T | null;
  loading: boolean;
  error: unknown;
};

function idle<T>(): PanelState<T> {
  return { data: null, loading: false, error: null };
}

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
  const requestGen = useRef(0);

  const [chain, setChain] = useState<PanelState<JobRetryChain>>(idle());
  const [artifacts, setArtifacts] = useState<PanelState<JobArtifact[]>>(idle());
  const [artifactCursor, setArtifactCursor] = useState<string | null>(null);
  const [artifactHasMore, setArtifactHasMore] = useState(false);
  const [legacyInputs, setLegacyInputs] = useState(false);
  const [timeline, setTimeline] = useState<PanelState<JobTimelineEvent[]>>(idle());
  const [timelineHasMore, setTimelineHasMore] = useState(false);
  const [logs, setLogs] = useState<PanelState<ExecutionLogEvent[]>>(idle());
  const [logCursor, setLogCursor] = useState<string | null>(null);
  const [logHasMore, setLogHasMore] = useState(false);
  const [logMode, setLogMode] = useState<string | null>(null);
  const [errors, setErrors] = useState<PanelState<JobErrorItem[]>>(idle());
  const [errorHasMore, setErrorHasMore] = useState(false);
  const [hybrid, setHybrid] = useState<PanelState<Record<string, unknown>>>(idle());
  const [preview, setPreview] = useState<ArtifactPreview | null>(null);

  const resetPanels = useCallback(() => {
    setChain(idle());
    setArtifacts(idle());
    setArtifactCursor(null);
    setArtifactHasMore(false);
    setLegacyInputs(false);
    setTimeline(idle());
    setTimelineHasMore(false);
    setLogs(idle());
    setLogCursor(null);
    setLogHasMore(false);
    setLogMode(null);
    setErrors(idle());
    setErrorHasMore(false);
    setHybrid(idle());
    setPreview(null);
  }, []);

  useEffect(() => {
    if (!active || !jobId) {
      resetPanels();
      return;
    }
    const gen = ++requestGen.current;
    resetPanels();

    const stillCurrent = () => gen === requestGen.current;

    setChain((s) => ({ ...s, loading: true, error: null }));
    void getJobRetryChain(inventoryId, aisleId, jobId)
      .then((data) => {
        if (!stillCurrent()) return;
        setChain({ data, loading: false, error: null });
      })
      .catch((error) => {
        if (!stillCurrent()) return;
        setChain({ data: null, loading: false, error });
      });

    setArtifacts((s) => ({ ...s, loading: true, error: null }));
    void getJobArtifacts(inventoryId, aisleId, jobId, { limit: 50 })
      .then((page) => {
        if (!stillCurrent()) return;
        setArtifacts({ data: page.items, loading: false, error: null });
        setArtifactCursor(page.page.next_cursor ?? null);
        setArtifactHasMore(Boolean(page.page.has_more));
        setLegacyInputs(Boolean((page as { inputs_legacy_unverified?: boolean }).inputs_legacy_unverified));
      })
      .catch((error) => {
        if (!stillCurrent()) return;
        setArtifacts({ data: null, loading: false, error });
      });

    setTimeline((s) => ({ ...s, loading: true, error: null }));
    void getJobTimeline(inventoryId, aisleId, jobId, { limit: 50 })
      .then((page) => {
        if (!stillCurrent()) return;
        setTimeline({ data: page.items, loading: false, error: null });
        setTimelineHasMore(Boolean(page.page.has_more));
      })
      .catch((error) => {
        if (!stillCurrent()) return;
        setTimeline({ data: null, loading: false, error });
      });

    setLogs((s) => ({ ...s, loading: true, error: null }));
    void getExecutionLogPage(inventoryId, aisleId, jobId, { limit: 50, sort_order: 'asc' })
      .then((page) => {
        if (!stillCurrent()) return;
        setLogs({ data: page.items, loading: false, error: null });
        setLogCursor(page.page.next_cursor ?? null);
        setLogHasMore(Boolean(page.page.has_more));
        setLogMode(page.pagination_mode ?? null);
      })
      .catch((error) => {
        if (!stillCurrent()) return;
        setLogs({ data: null, loading: false, error });
      });

    setErrors((s) => ({ ...s, loading: true, error: null }));
    void getJobErrors(inventoryId, aisleId, jobId, { limit: 50 })
      .then((page) => {
        if (!stillCurrent()) return;
        setErrors({ data: page.items, loading: false, error: null });
        setErrorHasMore(Boolean(page.page.has_more));
      })
      .catch((error) => {
        if (!stillCurrent()) return;
        setErrors({ data: null, loading: false, error });
      });

    setHybrid((s) => ({ ...s, loading: true, error: null }));
    void getJobHybridReport(inventoryId, aisleId, jobId)
      .then((data) => {
        if (!stillCurrent()) return;
        setHybrid({ data, loading: false, error: null });
      })
      .catch((error) => {
        if (!stillCurrent()) return;
        setHybrid({ data: null, loading: false, error });
      });

    return () => {
      requestGen.current += 1;
    };
  }, [active, aisleId, inventoryId, jobId, resetPanels]);

  const loadMoreLogs = async () => {
    if (!logCursor || !jobId) return;
    const gen = requestGen.current;
    try {
      const page = await getExecutionLogPage(inventoryId, aisleId, jobId, {
        cursor: logCursor,
        limit: 50,
      });
      if (gen !== requestGen.current) return;
      setLogs((prev) => ({
        data: [...(prev.data ?? []), ...page.items],
        loading: false,
        error: null,
      }));
      setLogCursor(page.page.next_cursor ?? null);
      setLogHasMore(Boolean(page.page.has_more));
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      showSnackbar(resolveApiErrorMessage(err, 'errors.load_execution_log'), 'error');
    }
  };

  const loadMoreArtifacts = async () => {
    if (!artifactCursor || !jobId) return;
    const gen = requestGen.current;
    try {
      const page = await getJobArtifacts(inventoryId, aisleId, jobId, {
        cursor: artifactCursor,
        limit: 50,
      });
      if (gen !== requestGen.current) return;
      setArtifacts((prev) => ({
        data: [...(prev.data ?? []), ...page.items],
        loading: false,
        error: null,
      }));
      setArtifactCursor(page.page.next_cursor ?? null);
      setArtifactHasMore(Boolean(page.page.has_more));
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      showSnackbar(resolveApiErrorMessage(err, 'errors.load_job_details'), 'error');
    }
  };

  const openPreview = async (artifactId: string) => {
    try {
      const data = await getJobArtifactPreview(inventoryId, aisleId, jobId, artifactId);
      setPreview(data);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      showSnackbar(resolveApiErrorMessage(err, 'errors.load_job_details'), 'error');
    }
  };

  if (!jobId) {
    return (
      <Typography variant="body2" color="text.secondary">
        {t('jobs.obs_choose_job_for_log')}
      </Typography>
    );
  }

  const renderPanel = (title: string, state: PanelState<unknown>, body: ReactNode) => (
    <Box>
      <Typography variant="subtitle2" gutterBottom>
        {title}
      </Typography>
      {state.loading ? (
        <Box sx={{ py: 1 }}>
          <CircularProgress size={22} />
        </Box>
      ) : null}
      {state.error ? (
        <ErrorAlert message={resolveApiErrorMessage(state.error, 'errors.load_job_details')} />
      ) : null}
      {!state.loading && !state.error ? body : null}
    </Box>
  );

  return (
    <Stack spacing={2}>
      {renderPanel(
        t('jobs.obs_tab_retry_chain'),
        chain,
        !chain.data || chain.data.attempts.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {t('jobs.obs_retry_chain_empty')}
          </Typography>
        ) : (
          <Stack spacing={1}>
            <Typography variant="caption" color="text.secondary">
              {t('jobs.obs_retry_integrity', { value: chain.data.integrity ?? 'VALID' })}
            </Typography>
            <Stack direction="row" flexWrap="wrap" gap={1}>
              {chain.data.attempts.map((a) => (
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
          </Stack>
        ),
      )}

      <Divider />

      {renderPanel(
        t('jobs.obs_tab_artifacts'),
        artifacts,
        <>
          {legacyInputs ? (
            <Typography variant="caption" color="warning.main" display="block" sx={{ mb: 1 }}>
              {t('jobs.obs_inputs_legacy_unverified')}
            </Typography>
          ) : null}
          {(artifacts.data ?? []).length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {t('jobs.obs_artifacts_empty')}
            </Typography>
          ) : (
            <Stack spacing={0.75}>
              {(artifacts.data ?? []).map((a) => (
                <Box
                  key={a.id}
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: '1fr', sm: '1fr auto auto' },
                    gap: 0.5,
                    alignItems: 'center',
                  }}
                >
                  <Typography variant="body2">
                    {a.display_name}{' '}
                    <Typography component="span" variant="caption" color="text.secondary">
                      ({a.category} · {a.kind} · {a.status}
                      {a.is_current ? ` · ${t('jobs.obs_artifact_current')}` : ''})
                    </Typography>
                  </Typography>
                  <Button size="small" onClick={() => void openPreview(a.id)} disabled={!a.is_previewable}>
                    {t('jobs.obs_preview')}
                  </Button>
                  <Button
                    size="small"
                    disabled={!a.is_downloadable || a.status !== 'AVAILABLE'}
                    onClick={() => {
                      void downloadJobArtifact(
                        inventoryId,
                        aisleId,
                        jobId,
                        a.id,
                        a.original_filename || a.kind
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
              {artifactHasMore ? (
                <Button size="small" onClick={() => void loadMoreArtifacts()}>
                  {t('jobs.obs_load_more_logs')}
                </Button>
              ) : null}
            </Stack>
          )}
          {preview ? (
            <Box sx={{ mt: 1, p: 1, border: 1, borderColor: 'divider', borderRadius: 1 }}>
              <Typography variant="caption" display="block">
                {t('jobs.obs_preview_truncated', { truncated: String(preview.truncated) })}
              </Typography>
              <Typography
                component="pre"
                variant="caption"
                sx={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto', m: 0 }}
              >
                {preview.content ?? JSON.stringify(preview, null, 2)}
              </Typography>
            </Box>
          ) : null}
        </>,
      )}

      <Divider />

      {renderPanel(
        t('jobs.obs_tab_hybrid'),
        hybrid,
        hybrid.data ? (
          <Box>
            <Typography variant="caption" color="success.main" display="block" sx={{ mb: 1 }}>
              {t('jobs.obs_hybrid_report_available')}
            </Typography>
            <Typography
              component="pre"
              variant="caption"
              sx={{ whiteSpace: 'pre-wrap', maxHeight: 260, overflow: 'auto', m: 0 }}
            >
              {JSON.stringify(hybrid.data, null, 2).slice(0, 8000)}
            </Typography>
          </Box>
        ) : (
          <Typography variant="body2" color="text.secondary">
            {t('jobs.obs_hybrid_report_missing')}
          </Typography>
        ),
      )}

      <Divider />

      {renderPanel(
        t('jobs.obs_tab_timeline'),
        timeline,
        (timeline.data ?? []).length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {t('jobs.obs_timeline_empty')}
          </Typography>
        ) : (
          <Stack spacing={0.5} sx={{ maxHeight: 240, overflow: 'auto' }}>
            {(timeline.data ?? []).map((ev) => (
              <Typography key={ev.id} variant="caption" component="div">
                [{ev.timestamp ?? '—'}] {ev.event_type} · {ev.stage ?? '—'} · {ev.message ?? ''}
              </Typography>
            ))}
            {timelineHasMore ? (
              <Typography variant="caption" color="text.secondary">
                {t('jobs.obs_has_more')}
              </Typography>
            ) : null}
          </Stack>
        ),
      )}

      <Divider />

      {renderPanel(
        t('jobs.obs_tab_paged_logs'),
        logs,
        <>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
            {t('jobs.obs_paged_logs_hint', { count: (logs.data ?? []).length })}
            {logMode ? ` · ${logMode}` : ''}
            {logMode === 'legacy_capped' ? ` · ${t('jobs.obs_log_legacy_capped')}` : ''}
          </Typography>
          <Stack spacing={0.5} sx={{ maxHeight: 220, overflow: 'auto' }}>
            {(logs.data ?? []).map((ev, idx) => (
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
        </>,
      )}

      <Divider />

      {renderPanel(
        t('jobs.obs_tab_errors'),
        errors,
        (errors.data ?? []).length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {t('jobs.obs_errors_empty')}
          </Typography>
        ) : (
          <Stack spacing={0.75}>
            {(errors.data ?? []).map((e) => (
              <Typography key={e.error_id} variant="body2">
                {e.error_code ?? 'ERROR'} · {e.stage ?? '—'} · {e.message ?? e.sanitized_detail ?? ''}
              </Typography>
            ))}
            {errorHasMore ? (
              <Typography variant="caption" color="text.secondary">
                {t('jobs.obs_has_more')}
              </Typography>
            ) : null}
          </Stack>
        ),
      )}
    </Stack>
  );
}
