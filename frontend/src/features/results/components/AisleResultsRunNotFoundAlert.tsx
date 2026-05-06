import { Alert, Button } from '@mui/material';
import { useTranslation } from 'react-i18next';

export interface AisleResultsRunNotFoundAlertProps {
  visible: boolean;
  canClear: boolean;
  onClear: () => void;
}

export default function AisleResultsRunNotFoundAlert({ visible, canClear, onClear }: AisleResultsRunNotFoundAlertProps) {
  const { t } = useTranslation();

  if (!visible) return null;

  return (
    <Alert
      severity="error"
      sx={{ mb: 2 }}
      action={
        <Button color="inherit" size="small" disabled={!canClear} onClick={onClear}>
          {t('positions.clear_run_filter')}
        </Button>
      }
    >
      {t('positions.no_data_for_run')}
    </Alert>
  );
}
