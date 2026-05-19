import { Box, Paper, Typography } from '@mui/material';
import type { CompareExecutiveSummaryModel } from '../compareBenchmarkViewModel';

type CompareExecutiveSummaryProps = {
  model: CompareExecutiveSummaryModel;
  compact?: boolean;
};

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" display="block">
        {label}
      </Typography>
      <Typography variant="body2" fontWeight={600}>
        {value}
      </Typography>
    </Box>
  );
}

export default function CompareExecutiveSummary({ model, compact = false }: CompareExecutiveSummaryProps) {
  return (
    <Paper variant="outlined" sx={{ p: compact ? 1.5 : 2 }} data-testid="compare-benchmark-executive-summary">
      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
        {model.title}
      </Typography>
      <Box
        sx={{
          display: 'grid',
          gap: 1.5,
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))', md: 'repeat(3, minmax(0, 1fr))' },
        }}
      >
        <SummaryItem label={model.baselineLabel} value={model.baselineValue} />
        <SummaryItem label={model.comparedRunsLabel} value={model.comparedRunsValue} />
        <SummaryItem label={model.selectedRunsCostLabel} value={model.selectedRunsCostValue} />
        <SummaryItem label={model.costRangeLabel} value={model.costRangeValue} />
        <SummaryItem label={model.timeRangeLabel} value={model.timeRangeValue} />
        <SummaryItem label={model.quantityRangeLabel} value={model.quantityRangeValue} />
        <SummaryItem label={model.jobsWithCostLabel} value={model.jobsWithCostValue} />
        <SummaryItem label={model.jobsWithoutCostLabel} value={model.jobsWithoutCostValue} />
      </Box>
    </Paper>
  );
}
