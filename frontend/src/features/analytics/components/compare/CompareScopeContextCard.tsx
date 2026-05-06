import { Paper, Typography } from '@mui/material';

type CompareScopeContextCardProps = {
  contextLabel: string;
  inventoryLabel: string;
  inventoryValue: string;
  aisleValue: string;
  runsLabel?: string;
};

export default function CompareScopeContextCard({
  contextLabel,
  inventoryLabel,
  inventoryValue,
  aisleValue,
  runsLabel,
}: CompareScopeContextCardProps) {
  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
      <Typography variant="overline" color="text.secondary" display="block">
        {contextLabel}
      </Typography>
      <Typography variant="body1" sx={{ fontWeight: 600 }}>
        {inventoryLabel}: {inventoryValue}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {aisleValue}
      </Typography>
      {runsLabel ? (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1, fontFamily: 'monospace' }}>
          {runsLabel}
        </Typography>
      ) : null}
    </Paper>
  );
}
