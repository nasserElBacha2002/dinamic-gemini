import { Box, Button, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';

export interface CodeScanEmptyStateProps {
  variant: 'no_run' | 'no_detections';
  onRunScan?: () => void;
  runDisabled?: boolean;
  runLabel?: string;
}

export default function CodeScanEmptyState({
  variant,
  onRunScan,
  runDisabled = false,
  runLabel,
}: CodeScanEmptyStateProps) {
  const { t } = useTranslation();
  const titleKey =
    variant === 'no_run' ? 'aisleCodeScans.states.noRun' : 'aisleCodeScans.states.noDetections';
  const helperKey =
    variant === 'no_run' ? 'aisleCodeScans.states.noRunHelper' : 'aisleCodeScans.states.noDetectionsHelper';

  return (
    <Box sx={{ py: 3, textAlign: 'center' }}>
      <Typography variant="subtitle1" gutterBottom>
        {t(titleKey)}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {t(helperKey)}
      </Typography>
      {variant === 'no_run' && onRunScan ? (
        <Button variant="contained" onClick={onRunScan} disabled={runDisabled}>
          {runLabel ?? t('aisleCodeScans.actions.run')}
        </Button>
      ) : null}
    </Box>
  );
}
