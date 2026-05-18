import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { Alert } from '@mui/material';
import { CompareManyRunsWorkspace } from '../../features/analytics/compare/CompareManyRunsWorkspace';

export default function CompareManyRunsPage() {
  const { t } = useTranslation();
  const { inventoryId } = useParams<{ inventoryId: string }>();

  if (!inventoryId) {
    return <Alert severity="warning">{t('compare_many.missing_inventory')}</Alert>;
  }

  return <CompareManyRunsWorkspace mode="route" inventoryId={inventoryId} />;
}
