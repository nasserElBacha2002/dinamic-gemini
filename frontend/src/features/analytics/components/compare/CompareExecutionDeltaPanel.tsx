import { Paper, Typography } from '@mui/material';

type CompareExecutionDeltaPanelProps = {
  value: string;
  hint: string;
  tone: 'error.main' | 'success.main' | 'text.primary';
};

export default function CompareExecutionDeltaPanel({ value, hint, tone }: CompareExecutionDeltaPanelProps) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Typography variant="body2" sx={{ color: tone }}>
        {value}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
        {hint}
      </Typography>
    </Paper>
  );
}
