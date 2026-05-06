import { Box, Chip, Paper, Typography } from '@mui/material';

type CompareManyJobCardItem = {
  job_id: string;
  status: string;
  provider_name?: string | null;
  model_name?: string | null;
  execution_time_human?: string | null;
  execution_time_seconds?: number | null;
  metrics: {
    total_quantity: number;
    needs_review_count: number;
    unknown_internal_code_count: number;
    consolidated_positions: number;
  };
};

type CompareManyJobCardsGridProps = {
  orderedJobIds: string[];
  jobsById: Map<string, CompareManyJobCardItem>;
  baselineJobId: string;
  baselineChipLabel: string;
  statusChipLabel: (status: string) => string;
  metricsLabel: (values: { qty: number; review: number; unknown: number; consolidated: number }) => string;
  executionTimeLabel: (value: string) => string;
  executionTimeValue: (job: CompareManyJobCardItem) => string;
  emDash: string;
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
  emDash,
}: CompareManyJobCardsGridProps) {
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
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
              <Typography variant="subtitle2" sx={{ fontFamily: 'monospace' }}>
                {job.job_id}
              </Typography>
              <Box sx={{ display: 'flex', gap: 0.75 }}>
                {isBaseline ? <Chip size="small" color="primary" label={baselineChipLabel} /> : null}
                <Chip size="small" color={job.status === 'succeeded' ? 'default' : 'warning'} label={statusChipLabel(job.status)} />
              </Box>
            </Box>
            <Typography variant="caption" color="text.secondary" display="block">
              {job.provider_name ?? emDash} · {job.model_name ?? emDash}
            </Typography>
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
