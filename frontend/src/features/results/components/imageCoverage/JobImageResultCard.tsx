/**
 * Compact unmatched-image row: order, filename, status, add-result action.
 * This view only lists images without results — no thumbnails, counts, or origin badges.
 */

import { useTranslation } from 'react-i18next';
import { Box, Button, Card, Chip, Stack, Typography } from '@mui/material';
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutline';
import type { JobImageResultItem } from '../../../../api/types';
import { isFailedProcessingStatus } from '../../utils/jobImageProcessingStatus';

export interface JobImageResultCardProps {
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
  const orderLabel = `#${item.position_order + 1}`;
  const failed = isFailedProcessingStatus(item.processing_status);
  const statusLabel = failed
    ? t('results.imageCoverage.card.processingStatus.failed')
    : t('results.imageCoverage.card.withoutResultBadge');

  return (
    <Card
      variant="outlined"
      data-testid="job-image-result-card"
      data-has-result="false"
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
          <Typography variant="subtitle2" fontWeight={600} noWrap title={filename} sx={{ maxWidth: 360 }}>
            {filename}
          </Typography>
          <Chip
            size="small"
            variant="outlined"
            color={failed ? 'error' : 'warning'}
            label={statusLabel}
            data-testid={failed ? 'job-image-failed-badge' : 'job-image-without-result-badge'}
          />
        </Stack>

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
      </Stack>
    </Card>
  );
}
