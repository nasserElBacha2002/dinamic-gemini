import { Box, Chip, Paper, Tooltip, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { BenchmarkRunCompareSide } from '../../../../api/types';
import { getRunCostCardLine, getRunModelLabel } from '../../adapters/compareRunLabels';

type CompareManyJobCardsGridProps = {
  orderedJobIds: string[];
  jobsById: Map<string, BenchmarkRunCompareSide>;
  baselineJobId: string;
  baselineChipLabel: string;
  statusChipLabel: (status: string) => string;
  metricsLabel: (values: { qty: number; review: number; unknown: number; consolidated: number }) => string;
  executionTimeLabel: (value: string) => string;
  executionTimeValue: (job: BenchmarkRunCompareSide) => string;
};

export default function CompareManyJobCardsGrid({
  orderedJobIds,
  jobsById,
  baselineJobId,
  baselineChipLabel,
  statusChipLabel,
  metricsLabel,
  executionTimeLabel,
  executionTimeValue,
}: CompareManyJobCardsGridProps) {
  const { t } = useTranslation();

  return (
    <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(3, minmax(0, 1fr))' } }}>
      {orderedJobIds.map((jobId) => {
        const job = jobsById.get(jobId);
        if (!job) return null;
        const isBaseline = jobId === baselineJobId;
        return (
          <Paper
            key={jobId}
            variant="outlined"
            sx={{ p: 2, borderColor: isBaseline ? 'primary.main' : 'divider' }}
            data-testid={isBaseline ? 'compare-many-baseline-card' : undefined}
          >
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1, gap: 1 }}>
              <Typography variant="subtitle1" sx={{ wordBreak: 'break-word', pr: 1 }}>
                {getRunModelLabel(job, t)}
              </Typography>
              <Box sx={{ display: 'flex', gap: 0.75, flexShrink: 0 }}>
                {isBaseline ? <Chip size="small" color="primary" label={baselineChipLabel} /> : null}
                <Chip size="small" color={job.status === 'succeeded' ? 'default' : 'warning'} label={statusChipLabel(job.status)} />
              </Box>
            </Box>
            <Typography variant="body2" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
              {getRunCostCardLine(job, t)}
            </Typography>
            <Tooltip title={job.job_id}>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5, fontFamily: 'monospace' }}>
                {t('compare_many.job_line', { id: `${job.job_id.slice(0, 8)}…` })}
              </Typography>
            </Tooltip>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
              {executionTimeLabel(executionTimeValue(job))}
            </Typography>
            <Typography variant="body2" sx={{ mt: 1 }}>
              {metricsLabel({
                qty: job.metrics.total_quantity,
                review: job.metrics.needs_review_count,
                unknown: job.metrics.unknown_internal_code_count,
                consolidated: job.metrics.consolidated_positions,
              })}
            </Typography>
          </Paper>
        );
      })}
    </Box>
  );
}
