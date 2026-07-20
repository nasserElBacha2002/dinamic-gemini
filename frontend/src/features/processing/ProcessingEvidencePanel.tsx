import { useTranslation } from 'react-i18next';
import { Alert, Box, Paper, Typography } from '@mui/material';
import { ResultEvidenceViewer } from '../results/components/detail';
import type { AssetProcessingSummary } from '../../api/types/processing';

export interface ProcessingEvidencePanelProps {
  asset: AssetProcessingSummary;
  inventoryId: string;
  aisleId: string;
  jobId: string;
  canViewSensitiveEvidence: boolean;
  active?: boolean;
}

function sanitizeRecord(value: Record<string, unknown> | null | undefined): Record<string, unknown> | null {
  if (!value) return null;
  const next: Record<string, unknown> = {};
  for (const [key, raw] of Object.entries(value)) {
    if (/secret|token|password|api_key|credential/i.test(key)) continue;
    next[key] = raw;
  }
  return next;
}

export default function ProcessingEvidencePanel({
  asset,
  inventoryId,
  aisleId,
  jobId,
  canViewSensitiveEvidence,
  active = true,
}: ProcessingEvidencePanelProps) {
  const { t } = useTranslation();

  return (
    <Box data-testid="processing-evidence-panel">
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {t('processing.evidence.title')}
      </Typography>

      {!canViewSensitiveEvidence ? (
        <Alert severity="info" sx={{ mb: 1.5 }}>
          {t('processing.evidence.limitedNotice')}
        </Alert>
      ) : null}

      <ResultEvidenceViewer
        inventoryId={inventoryId}
        aisleId={aisleId}
        assetId={asset.asset_id}
        jobId={jobId}
        filename={asset.file_name}
        enabled={active}
        variant="manual-result"
      />

      {asset.warnings.length > 0 ? (
        <Paper variant="outlined" sx={{ p: 1.25, mt: 1.5 }}>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
            {t('processing.evidence.warnings')}
          </Typography>
          {asset.warnings.map((warning, index) => (
            <Typography key={`${warning}-${index}`} variant="body2">
              {warning}
            </Typography>
          ))}
        </Paper>
      ) : null}

      {canViewSensitiveEvidence ? null : (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          {t('processing.evidence.sanitizedNote')}
        </Typography>
      )}
    </Box>
  );
}

/** Exported for tests — strips known secret-like keys from metadata blobs. */
export { sanitizeRecord as sanitizeProcessingEvidenceRecord };
