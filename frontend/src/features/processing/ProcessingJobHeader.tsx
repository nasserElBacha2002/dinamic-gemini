import { useTranslation } from 'react-i18next';
import { Box, Paper, Typography } from '@mui/material';
import type { JobSummary } from '../../api/types';
import type { ProcessingJobProgressSummary } from '../../api/types/processing';
import {
  buildJobExecutionPresentation,
  strategyLabelKey,
} from './mappers/processingExecutionPresentation';

export interface ProcessingJobHeaderProps {
  job: JobSummary | null;
  summary?: ProcessingJobProgressSummary | null;
  isLoading?: boolean;
}

function formatOptional(value: string | null | undefined, dash: string): string {
  const trimmed = String(value ?? '').trim();
  return trimmed || dash;
}

function formatIdentity(
  provider: string | null | undefined,
  model: string | null | undefined,
  promptKey: string | null | undefined,
  dash: string,
): string {
  return [provider, model, promptKey].filter(Boolean).join(' · ') || dash;
}

export default function ProcessingJobHeader({ job, summary, isLoading }: ProcessingJobHeaderProps) {
  const { t } = useTranslation();
  const dash = t('common.em_dash');

  if (isLoading) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="processing-job-header-loading">
        {t('processing.header.loading')}
      </Typography>
    );
  }

  if (!job) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="processing-job-header-empty">
        {t('processing.header.selectJob')}
      </Typography>
    );
  }

  const progress = summary ?? job.asset_progress ?? null;
  const presentation = buildJobExecutionPresentation({
    identification_mode: job.identification_mode,
    execution_strategy: job.execution_strategy,
    current_stage: job.current_stage,
    provider_name: job.provider_name,
    model_name: job.model_name,
    prompt_key: job.prompt_key,
    prompt_version: job.prompt_version,
    identification_execution: job.identification_execution ?? null,
    fallback_asset_summaries: job.fallback_asset_summaries ?? null,
    result_json: (job as { result_json?: Record<string, unknown> | null }).result_json ?? null,
    external_execution_used:
      Number(job.fallback_progress?.resolved_external || 0) > 0 ||
      Number(job.fallback_progress?.fallback_requested || 0) > 0,
  });

  return (
    <Paper variant="outlined" sx={{ p: 1.5 }} data-testid="processing-job-header">
      <Box sx={{ display: 'grid', gap: 0.75 }}>
        <Typography variant="subtitle2">{t('processing.header.title')}</Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '140px 1fr' }, gap: 0.5 }}>
          <Typography variant="caption" color="text.secondary">
            {t('processing.header.mode')}
          </Typography>
          <Typography variant="caption">{formatOptional(job.identification_mode, dash)}</Typography>

          <Typography variant="caption" color="text.secondary">
            {t('processing.header.strategy')}
          </Typography>
          <Typography variant="caption">
            {job.execution_strategy
              ? t(strategyLabelKey(job.execution_strategy), {
                  defaultValue: String(job.execution_strategy),
                })
              : dash}
          </Typography>

          <Typography variant="caption" color="text.secondary">
            {t('aisle.obs_external_provider_used')}
          </Typography>
          <Typography variant="caption" data-testid="processing-job-external-provider-used">
            {presentation.externalProviderUsedLabel === 'yes'
              ? t('aisle.obs_external_provider_yes')
              : t('aisle.obs_external_provider_no')}
          </Typography>

          {presentation.showFallbackConfiguredRows ? (
            <>
              <Typography variant="caption" color="text.secondary">
                {t('processing.header.fallbackConfigured')}
              </Typography>
              <Typography variant="caption" data-testid="processing-job-fallback-configured">
                {formatIdentity(
                  presentation.configured.provider,
                  presentation.configured.model,
                  presentation.configured.promptKey,
                  dash,
                )}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {t('processing.header.fallbackExecuted')}
              </Typography>
              <Typography variant="caption" data-testid="processing-job-fallback-executed">
                {!presentation.fallbackUsed
                  ? t('processing.header.fallbackNotExecuted')
                  : presentation.executed?.evidencePresent
                    ? formatIdentity(
                        presentation.executed.provider,
                        presentation.executed.executedModel ??
                          presentation.executed.requestedModel,
                        presentation.executed.promptKey,
                        t('processing.header.unknown', { defaultValue: 'Unknown' }),
                      )
                    : t('processing.header.unknown', { defaultValue: 'Unknown' })}
              </Typography>
            </>
          ) : null}

          {presentation.showProviderModelRows ? (
            <>
              <Typography variant="caption" color="text.secondary">
                {t('processing.header.profile')}
              </Typography>
              <Typography variant="caption" data-testid="processing-job-legacy-profile">
                {formatIdentity(
                  presentation.displayProvider,
                  presentation.displayModel,
                  presentation.displayPromptKey,
                  dash,
                )}
              </Typography>
            </>
          ) : null}

          {presentation.historicalMetadataWarning ? (
            <>
              <Typography variant="caption" color="text.secondary">
                {t('processing.header.metadataWarning')}
              </Typography>
              <Typography
                variant="caption"
                color="warning.main"
                data-testid="processing-job-historical-metadata-warning"
              >
                {t('processing.header.historicalMetadataInconsistent')}
                {presentation.metadataInconsistencyReasons.length
                  ? ` (${presentation.metadataInconsistencyReasons.join(', ')})`
                  : ''}
              </Typography>
            </>
          ) : null}

          {progress ? (
            <>
              <Typography variant="caption" color="text.secondary">
                {t('processing.header.progress')}
              </Typography>
              <Typography variant="caption" data-testid="processing-job-progress">
                {t('processing.header.progressValue', {
                  total: progress.total,
                  resolved: progress.resolved,
                  failed: progress.failed,
                  pending: progress.pending,
                  processing: progress.processing,
                  manual_review: progress.manual_review,
                  unrecognized: progress.unrecognized ?? 0,
                })}
              </Typography>
            </>
          ) : null}
        </Box>
      </Box>
    </Paper>
  );
}
