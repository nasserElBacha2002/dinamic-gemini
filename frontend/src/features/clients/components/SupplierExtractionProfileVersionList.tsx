import { Box, Button, Chip, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { SupplierExtractionProfile } from '../../../api/types';
import { formatDate } from '../../../utils/formatDate';

export interface SupplierExtractionProfileVersionListProps {
  items: SupplierExtractionProfile[];
  onActivate: (profileId: string, expectedRowVersion: number) => Promise<void>;
  isActivating?: boolean;
}

function statusChipColor(status: string): 'success' | 'default' | 'warning' | 'info' {
  if (status === 'ACTIVE') return 'success';
  if (status === 'DRAFT') return 'info';
  if (status === 'SUPERSEDED') return 'default';
  return 'warning';
}

export default function SupplierExtractionProfileVersionList({
  items,
  onActivate,
  isActivating = false,
}: SupplierExtractionProfileVersionListProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        {t('clients.extraction_profile.no_versions_description')}
      </Typography>
    );
  }

  return (
    <Stack spacing={1.5}>
      {items.map((item) => (
        <Box key={item.id} sx={{ p: 1.5, borderRadius: 1, border: 1, borderColor: 'divider' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap' }}>
            <Typography variant="subtitle2">
              {t('clients.extraction_profile.version_label', { version: item.version })}
            </Typography>
            <Chip
              size="small"
              color={statusChipColor(String(item.status))}
              label={t(`clients.extraction_profile.status.${String(item.status).toLowerCase()}`, {
                defaultValue: String(item.status),
              })}
            />
          </Box>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
            {t('clients.extraction_profile.version_meta', {
              created: formatDate(item.created_at),
              updated: formatDate(item.updated_at ?? item.created_at),
            })}
          </Typography>
          {item.visual_notes ? (
            <Typography
              variant="body2"
              sx={{
                mt: 1,
                whiteSpace: 'pre-wrap',
                display: '-webkit-box',
                overflow: 'hidden',
                WebkitLineClamp: +2,
                WebkitBoxOrient: 'vertical',
              }}
            >
              {item.visual_notes}
            </Typography>
          ) : null}
          {String(item.status) !== 'ACTIVE' ? (
            <Button
              size="small"
              variant="outlined"
              sx={{ mt: 1 }}
              disabled={isActivating}
              onClick={() => void onActivate(item.id, item.row_version)}
            >
              {t('clients.extraction_profile.activate_version')}
            </Button>
          ) : null}
        </Box>
      ))}
    </Stack>
  );
}
