import { useMemo } from 'react';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Stack,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { DataTable, type DataTableColumn } from '../../../components/ui';
import type { CodeScanDetection } from '../../../api/types/codeScans';
import { formatDate } from '../../../utils/formatDate';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { formatCodeScanCodeType, formatCodeScanMatchType } from '../formatters';
import CodeScanAssetPreviewButton from './CodeScanAssetPreviewButton';
import CopyCodeValueButton from './CopyCodeValueButton';
import { usePositionCodeScanEvidence } from '../hooks/usePositionCodeScanEvidence';

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

  const columns = useMemo((): DataTableColumn<CodeScanDetection>[] => [
    {
      id: 'type',
      label: t('aisleCodeScans.evidence.type'),
      cell: (d) => formatCodeScanCodeType(t, d.code_type),
    },
    {
      id: 'value',
      label: t('aisleCodeScans.evidence.value'),
      cell: (d) => (
        <Stack direction="row" spacing={0.5} alignItems="flex-start" sx={{ maxWidth: 220 }}>
          <Typography variant="body2" sx={{ wordBreak: 'break-all', flex: 1 }} component="span">
            {d.code_value}
          </Typography>
          <CopyCodeValueButton value={d.code_value} />
        </Stack>
      ),
    },
    {
      id: 'match',
      label: t('aisleCodeScans.evidence.match'),
      cell: (d) =>
        d.match_type
          ? formatCodeScanMatchType(t, d.match_type)
          : t('aisleCodeScans.matching.not_evaluated'),
    },
    {
      id: 'source_asset',
      label: t('aisleCodeScans.evidence.sourceAsset'),
      cell: (d) =>
        d.asset_id ? (
          <CodeScanAssetPreviewButton
            inventoryId={inventoryId}
            aisleId={aisleId}
            assetId={d.asset_id}
            jobIdForPreview={jobIdForPreview}
          />
        ) : (
          t('common.em_dash')
        ),
    },
    {
      id: 'detected_at',
      label: t('aisleCodeScans.evidence.detectedAt'),
      cell: (d) => formatDate(d.created_at),
    },
  ], [aisleId, inventoryId, jobIdForPreview, t]);

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
        <DataTable
          rows={detections}
          rowKey={(d) => d.id}
          columns={columns}
          stickyHeader={false}
          rowHover={false}
          mobile={{
            mode: 'card',
            title: (d) => d.code_value,
            subtitle: (d) => formatCodeScanCodeType(t, d.code_type),
            ariaLabel: (d) => d.code_value,
            fields: [
              {
                id: 'match',
                label: t('aisleCodeScans.evidence.match'),
                value: (d) =>
                  d.match_type
                    ? formatCodeScanMatchType(t, d.match_type)
                    : t('aisleCodeScans.matching.not_evaluated'),
              },
              {
                id: 'detected_at',
                label: t('aisleCodeScans.evidence.detectedAt'),
                value: (d) => formatDate(d.created_at),
              },
            ],
            primaryAction: (d) =>
              d.asset_id ? (
                <CodeScanAssetPreviewButton
                  inventoryId={inventoryId}
                  aisleId={aisleId}
                  assetId={d.asset_id}
                  jobIdForPreview={jobIdForPreview}
                />
              ) : null,
          }}
        />
      ) : null}
    </Box>
  );
}
