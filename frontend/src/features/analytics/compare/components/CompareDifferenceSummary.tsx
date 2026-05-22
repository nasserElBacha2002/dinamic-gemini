import WarningAmberOutlinedIcon from '@mui/icons-material/WarningAmberOutlined';
import { Alert, Box, Typography } from '@mui/material';
import type { CompareDifferenceSummaryModel } from '../compareBenchmarkViewModel';

type CompareDifferenceSummaryProps = {
  model: CompareDifferenceSummaryModel;
};

function DiffStat({ label, value }: { label: string; value: string }) {
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

export default function CompareDifferenceSummary({ model }: CompareDifferenceSummaryProps) {
  return (
    <Box data-testid="compare-difference-summary" sx={{ mb: 1.5 }}>
      <Typography variant="subtitle2" fontWeight={600} gutterBottom>
        {model.title}
      </Typography>
      <Box
        sx={{
          display: 'grid',
          gap: 1,
          gridTemplateColumns: { xs: '1fr 1fr', sm: 'repeat(3, minmax(0, 1fr))' },
          mb: 1,
        }}
      >
        <DiffStat label={model.skuDiffLabel} value={model.skuDiffValue} />
        <DiffStat label={model.quantityDiffLabel} value={model.quantityDiffValue} />
        <DiffStat label={model.positionDiffLabel} value={model.positionDiffValue} />
        <DiffStat label={model.onlyBaselineLabel} value={model.onlyBaselineValue} />
        <DiffStat label={model.onlyTargetLabel} value={model.onlyTargetValue} />
      </Box>
      {model.expandHint ? (
        <Typography variant="caption" color="text.secondary" display="block">
          {model.expandHint}
        </Typography>
      ) : null}
      {model.truncatedWarning ? (
        <Alert severity="warning" icon={<WarningAmberOutlinedIcon fontSize="small" />} sx={{ mt: 1 }}>
          {model.truncatedWarning}
        </Alert>
      ) : null}
    </Box>
  );
}
