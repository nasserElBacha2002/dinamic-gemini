/**
 * One row of the job image coverage view: photo + processing status + nested results (0..n).
 * "Agregar resultado" is only offered when the image has no result at all (`!has_result`) —
 * per spec, manual coverage targets uncovered images; backend still allows manual results even
 * when automatic ones exist, but the UI action here is scoped to the uncovered case.
 */

import { useTranslation } from 'react-i18next';
import { Box, Button, Card, Chip, Divider, Stack, Typography } from '@mui/material';
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutline';
import StatusBadge from '../../../../components/ui/StatusBadge';
import JobImageThumbnail from './JobImageThumbnail';
import type { JobImageResultItem, PositionSummary } from '../../../../api/types';
import {
  jobImageProcessingStatusLabel,
  jobImageProcessingStatusSemantic,
} from '../../utils/jobImageProcessingStatus';

export interface JobImageResultCardProps {
  inventoryId: string;
  aisleId: string;
  item: JobImageResultItem;
  onAddResult: (item: JobImageResultItem) => void;
  addResultDisabled?: boolean;
}

function positionSku(position: PositionSummary): string {
  const sku = position.product?.sku ?? position.sku ?? '';
  return sku.trim() || '—';
}

function positionQty(position: PositionSummary): number | null {
  const qty = position.quantity?.final ?? position.corrected_quantity ?? position.qty ?? null;
  return qty ?? null;
}

export default function JobImageResultCard({
  inventoryId,
  aisleId,
  item,
  onAddResult,
  addResultDisabled,
}: JobImageResultCardProps) {
  const { t } = useTranslation();
  const filename = item.original_filename?.trim() || t('results.imageCoverage.card.noFilename');
  const canAddResult = !item.has_result;

  return (
    <Card
      variant="outlined"
      data-testid="job-image-result-card"
      data-has-result={item.has_result ? 'true' : 'false'}
      sx={{ p: 2, display: 'flex', gap: 2, alignItems: 'flex-start' }}
    >
      <JobImageThumbnail
        inventoryId={inventoryId}
        aisleId={aisleId}
        sourceAssetId={item.source_asset_id}
        jobId={item.job_id}
        alt={filename}
      />

      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Typography variant="subtitle2" fontWeight={600} noWrap title={filename} sx={{ maxWidth: 320 }}>
            {filename}
          </Typography>
          <StatusBadge
            label={jobImageProcessingStatusLabel(item.processing_status)}
            semantic={jobImageProcessingStatusSemantic(item.processing_status)}
          />
          {item.has_result ? (
            <Chip
              size="small"
              variant="outlined"
              color="success"
              label={`${t('results.imageCoverage.card.withResultBadge')} (${item.result_count})`}
              data-testid="job-image-with-result-badge"
            />
          ) : (
            <Chip
              size="small"
              variant="outlined"
              color="warning"
              label={t('results.imageCoverage.card.withoutResultBadge')}
              data-testid="job-image-without-result-badge"
            />
          )}
        </Stack>

        {item.results.length > 0 ? (
          <Stack spacing={0.75} sx={{ mt: 1.5 }}>
            {item.results.map((position) => (
              <Box
                key={position.id}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  flexWrap: 'wrap',
                  py: 0.5,
                  px: 1,
                  borderRadius: 1,
                  bgcolor: 'action.hover',
                }}
              >
                <Typography variant="body2" fontWeight={600}>
                  {t('results.imageCoverage.card.skuLabel')}: {positionSku(position)}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {t('results.imageCoverage.card.qtyLabel')}: {positionQty(position) ?? t('common.em_dash')}
                </Typography>
                {position.position_code ? (
                  <Typography variant="body2" color="text.secondary">
                    {t('results.imageCoverage.card.positionCodeLabel')}: {position.position_code}
                  </Typography>
                ) : null}
                <Chip
                  size="small"
                  variant="outlined"
                  label={
                    position.creation_source === 'manual'
                      ? t('results.imageCoverage.card.manualBadge')
                      : t('results.imageCoverage.card.automaticBadge')
                  }
                  data-testid={`job-image-result-creation-source-${position.creation_source ?? 'automatic'}`}
                />
              </Box>
            ))}
          </Stack>
        ) : null}

        {canAddResult ? (
          <>
            <Divider sx={{ my: 1.5 }} />
            <Button
              size="small"
              variant="outlined"
              startIcon={<AddCircleOutlineIcon fontSize="small" />}
              onClick={() => onAddResult(item)}
              disabled={addResultDisabled}
              data-testid="job-image-add-manual-result"
            >
              {t('results.imageCoverage.card.addResultAction')}
            </Button>
          </>
        ) : null}
      </Box>
    </Card>
  );
}
