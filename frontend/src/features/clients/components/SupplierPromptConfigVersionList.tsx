import { Box, Button, Chip, Divider, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { SupplierPromptConfig } from '../../../api/types';
import { formatDate } from '../../../utils/formatDate';

export interface SupplierPromptConfigVersionListProps {
  items: SupplierPromptConfig[];
  onActivate: (configId: string) => Promise<void>;
  isActivating?: boolean;
}

function modelLabel(
  modelName: string | null | undefined,
  t: (key: string) => string
): string {
  return (modelName ?? '').trim() || t('clients.suppliers.prompt_configs.default_model_label');
}

function providerLabel(
  providerName: string | null | undefined,
  t: (key: string) => string
): string {
  return (providerName ?? '').trim() || t('clients.suppliers.prompt_configs.all_providers_label');
}

export default function SupplierPromptConfigVersionList({
  items,
  onActivate,
  isActivating = false,
}: SupplierPromptConfigVersionListProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        {t('clients.suppliers.prompt_configs.no_configs_description')}
      </Typography>
    );
  }

  return (
    <Stack spacing={1.5}>
      {items.map((item, index) => (
        <Box key={item.id} sx={{ p: 1.5, borderRadius: 1, border: 1, borderColor: 'divider' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
            <Typography variant="subtitle2">
              {t('clients.suppliers.prompt_configs.version_label', { version: item.version })}
            </Typography>
            {item.is_active ? (
              <Chip
                color="success"
                size="small"
                label={t('clients.suppliers.prompt_configs.active_badge')}
              />
            ) : null}
          </Box>
          <Typography variant="caption" color="text.secondary">
            {providerLabel(item.provider_name, t)} · {modelLabel(item.model_name, t)} ·{' '}
            {formatDate(item.updated_at)}
          </Typography>
          <Typography
            variant="body2"
            sx={{
              mt: 1,
              mb: 1,
              whiteSpace: 'pre-wrap',
              display: '-webkit-box',
              overflow: 'hidden',
              WebkitLineClamp: 3,
              WebkitBoxOrient: 'vertical',
            }}
          >
            {item.instructions_text}
          </Typography>
          {!item.is_active ? (
            <Button
              size="small"
              variant="outlined"
              disabled={isActivating}
              onClick={() => void onActivate(item.id)}
            >
              {t('clients.suppliers.prompt_configs.activate_version')}
            </Button>
          ) : null}
          {index < items.length - 1 ? <Divider sx={{ mt: 1.5 }} /> : null}
        </Box>
      ))}
    </Stack>
  );
}

