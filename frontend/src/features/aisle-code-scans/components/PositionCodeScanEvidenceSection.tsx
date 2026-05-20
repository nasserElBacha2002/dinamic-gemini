import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { formatCodeScanCodeType, formatCodeScanMatchType } from '../formatters';
import { usePositionCodeScanEvidence } from '../hooks/usePositionCodeScanEvidence';
import CodeScanAssetPreviewButton from './CodeScanAssetPreviewButton';
import CopyCodeValueButton from './CopyCodeValueButton';

export interface PositionCodeScanEvidenceSectionProps {
  inventoryId: string;
  aisleId: string;
  positionId: string;
  enabled: boolean;
  jobIdForPreview?: string | null;
  onOpenCodeScan?: () => void;
}

export default function PositionCodeScanEvidenceSection({
  inventoryId,
  aisleId,
  positionId,
  enabled,
  jobIdForPreview,
  onOpenCodeScan,
}: PositionCodeScanEvidenceSectionProps) {
  const { t } = useTranslation();
  const { data, isLoading, isError, error } = usePositionCodeScanEvidence(
    inventoryId,
    aisleId,
    positionId,
    { enabled }
  );

  const title = t('aisleCodeScans.evidence.title');

  if (isLoading) {
    return (
      <Box data-testid="position-code-scan-evidence">
        <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
          {title}
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          <CircularProgress size={20} />
          <Typography variant="body2" color="text.secondary">
            {t('aisleCodeScans.evidence.loading')}
          </Typography>
        </Stack>
      </Box>
    );
  }

  if (isError) {
    return (
      <Box data-testid="position-code-scan-evidence">
        <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
          {title}
        </Typography>
        <Alert severity="warning">
          {resolveApiErrorMessage(error, 'aisleCodeScans.evidence.loadError')}
        </Alert>
      </Box>
    );
  }

  const latestRun = data?.latest_run ?? null;
  const detections = data?.detections ?? [];

  return (
    <Box data-testid="position-code-scan-evidence">
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 0.5 }}>
        {title}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
        {t('aisleCodeScans.evidence.description')}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
        {t('aisleCodeScans.evidence.noMutationNotice')}
      </Typography>

      {!latestRun ? (
        <Stack spacing={1}>
          <Typography variant="body2" color="text.secondary">
            {t('aisleCodeScans.evidence.noRun')}
          </Typography>
          {onOpenCodeScan ? (
            <Button size="small" variant="outlined" onClick={onOpenCodeScan}>
              {t('aisleCodeScans.actions.open')}
            </Button>
          ) : null}
        </Stack>
      ) : null}

      {latestRun && detections.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {t('aisleCodeScans.evidence.empty')}
        </Typography>
      ) : null}

      {latestRun && detections.length > 0 ? (
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('aisleCodeScans.evidence.type')}</TableCell>
                <TableCell>{t('aisleCodeScans.evidence.value')}</TableCell>
                <TableCell>{t('aisleCodeScans.evidence.match')}</TableCell>
                <TableCell>{t('aisleCodeScans.evidence.sourceAsset')}</TableCell>
                <TableCell>{t('aisleCodeScans.evidence.detectedAt')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {detections.map((d) => (
                <TableRow key={d.id}>
                  <TableCell>{formatCodeScanCodeType(t, d.code_type)}</TableCell>
                  <TableCell sx={{ maxWidth: 220 }}>
                    <Stack direction="row" spacing={0.5} alignItems="flex-start">
                      <Typography
                        variant="body2"
                        sx={{ wordBreak: 'break-all', flex: 1 }}
                        component="span"
                      >
                        {d.code_value}
                      </Typography>
                      <CopyCodeValueButton value={d.code_value} />
                    </Stack>
                  </TableCell>
                  <TableCell>
                    {d.match_type
                      ? formatCodeScanMatchType(t, d.match_type)
                      : t('aisleCodeScans.matching.not_evaluated')}
                  </TableCell>
                  <TableCell>
                    {d.asset_id ? (
                      <CodeScanAssetPreviewButton
                        inventoryId={inventoryId}
                        aisleId={aisleId}
                        assetId={d.asset_id}
                        jobIdForPreview={jobIdForPreview}
                      />
                    ) : (
                      t('common.em_dash')
                    )}
                  </TableCell>
                  <TableCell>
                    {new Date(d.created_at).toLocaleString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      ) : null}
    </Box>
  );
}
