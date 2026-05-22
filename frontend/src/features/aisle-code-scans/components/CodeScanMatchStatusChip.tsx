import { Chip } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { formatCodeScanMatchStatus } from '../formatters';

export interface CodeScanMatchStatusChipProps {
  status: string | null | undefined;
}

function chipColor(status: string | null | undefined): 'default' | 'info' | 'warning' {
  if (status === 'matched') return 'info';
  if (status === 'multiple_candidates' || status === 'conflict' || status === 'mixed') {
    return 'warning';
  }
  return 'default';
}

export default function CodeScanMatchStatusChip({ status }: CodeScanMatchStatusChipProps) {
  const { t } = useTranslation();
  return (
    <Chip
      size="small"
      variant="outlined"
      color={chipColor(status)}
      label={formatCodeScanMatchStatus(t, status)}
    />
  );
}
