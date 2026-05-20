import { useTranslation } from 'react-i18next';
import { Box, Typography } from '@mui/material';
import type { CodeScanRunSummary as CodeScanRunSummaryType } from '../../../api/types/codeScans';
import { formatDate } from '../../../utils/formatDate';
import { formatCodeScanRunStatus } from '../formatters';

export interface CodeScanRunSummaryProps {
  run: CodeScanRunSummaryType;
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: 'flex', gap: 1, py: 0.25 }}>
      <Typography variant="body2" color="text.secondary" sx={{ minWidth: 160 }}>
        {label}
      </Typography>
      <Typography variant="body2" sx={{ wordBreak: 'break-word' }}>
        {value}
      </Typography>
    </Box>
  );
}

export default function CodeScanRunSummary({ run }: CodeScanRunSummaryProps) {
  const { t } = useTranslation();
  const finished = run.finished_at ? formatDate(run.finished_at) : t('common.em_dash');

  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {t('aisleCodeScans.summary.sectionTitle')}
      </Typography>
      <SummaryRow label={t('aisleCodeScans.summary.status')} value={formatCodeScanRunStatus(t, run.status)} />
      <SummaryRow
        label={t('aisleCodeScans.summary.processedAssets')}
        value={`${run.processed_assets} / ${run.total_assets}`}
      />
      <SummaryRow
        label={t('aisleCodeScans.summary.failedAssets')}
        value={String(run.failed_assets)}
      />
      <SummaryRow label={t('aisleCodeScans.summary.totalCodes')} value={String(run.total_codes_found)} />
      <SummaryRow label={t('aisleCodeScans.summary.qr')} value={String(run.total_qr_found)} />
      <SummaryRow label={t('aisleCodeScans.summary.barcodes')} value={String(run.total_barcodes_found)} />
      <SummaryRow label={t('aisleCodeScans.summary.engine')} value={run.scanner_engine} />
      <SummaryRow label={t('aisleCodeScans.summary.lastRun')} value={finished} />
    </Box>
  );
}
