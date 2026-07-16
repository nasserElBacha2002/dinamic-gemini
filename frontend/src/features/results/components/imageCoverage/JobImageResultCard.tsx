/**
 * One compact row of the job image coverage view: order, filename, status, counts, badges, actions.
 * "Agregar resultado" is only offered when the image has no result at all (`!has_result`).
 */

import { useTranslation } from 'react-i18next';
import { Box, Button, Card, Chip, Stack, Typography } from '@mui/material';
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutline';
import StatusBadge from '../../../../components/ui/StatusBadge';
import type { JobImageResultItem } from '../../../../api/types';
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

export default function JobImageResultCard({
  item,
  onAddResult,
  addResultDisabled,
}: JobImageResultCardProps) {
  const { t } = useTranslation();
  const filename = item.original_filename?.trim() || t('results.imageCoverage.card.noFilename');
  const canAddResult = !item.has_result;
  const orderLabel = `#${item.position_order + 1}`;

  return (
    <Card
      variant="outlined"
      data-testid="job-image-result-card"
      data-has-result={item.has_result ? 'true' : 'false'}
      sx={{ px: 2, py: 1.25 }}
    >
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1.5}
        alignItems={{ xs: 'stretch', sm: 'center' }}
        justifyContent="space-between"
      >
        <Stack
          direction="row"
          spacing={1}
          alignItems="center"
          flexWrap="wrap"
          useFlexGap
          sx={{ minWidth: 0, flex: 1 }}
        >
          <Typography
            variant="body2"
            fontWeight={700}
            color="text.secondary"
            data-testid="job-image-position-order"
            sx={{ flexShrink: 0, minWidth: '2.5ch' }}
          >
            {orderLabel}
          </Typography>
          <Typography variant="subtitle2" fontWeight={600} noWrap title={filename} sx={{ maxWidth: 280 }}>
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
          {item.result_count > 0 ? (
            <Chip
              size="small"
              variant="outlined"
              label={t('results.imageCoverage.card.resultCounts', {
                automatic: item.automatic_result_count,
                manual: item.manual_result_count,
              })}
              data-testid="job-image-result-counts"
            />
          ) : null}
          {item.automatic_result_count > 0 ? (
            <Chip
              size="small"
              variant="outlined"
              label={t('results.imageCoverage.card.automaticBadge')}
              data-testid="job-image-result-creation-source-automatic"
            />
          ) : null}
          {item.has_manual_result ? (
            <Chip
              size="small"
              variant="outlined"
              color="info"
              label={t('results.imageCoverage.card.manualBadge')}
              data-testid="job-image-result-creation-source-manual"
            />
          ) : null}
        </Stack>

        {canAddResult ? (
          <Box sx={{ flexShrink: 0 }}>
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
          </Box>
        ) : null}
      </Stack>
    </Card>
  );
}
