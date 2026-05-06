import { Alert } from '@mui/material';
import { useTranslation } from 'react-i18next';

export interface AisleResultsNoJobsAlertProps {
  visible: boolean;
}

export default function AisleResultsNoJobsAlert({ visible }: AisleResultsNoJobsAlertProps) {
  const { t } = useTranslation();

  if (!visible) return null;

  return (
    <Alert severity="info" sx={{ mb: 2 }}>
      {t('positions.no_runs_for_aisle')}
    </Alert>
  );
}
