import { Alert, Box, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { ExtractionProfileConfiguration, LabelKind } from '../../../../api/types';
import { SectionCard } from '../../../../components/ui';
import { BASIC_CHARSET_OPTIONS } from '../../utils/defaultExtractionProfileConfiguration';

interface Props {
  configuration: ExtractionProfileConfiguration;
  labelKind: LabelKind;
  onChange: (configuration: ExtractionProfileConfiguration) => void;
}

const ITEM_TARGETS = [
  { value: 'label_id', labelKey: 'clients.extraction_profile.identity_target_label_id' },
  { value: 'sku', labelKey: 'clients.extraction_profile.identity_target_sku' },
] as const;

const POSITION_TARGETS = [
  { value: 'position_id', labelKey: 'clients.extraction_profile.identity_target_position_id' },
] as const;

export default function BasicIdentitySection({ configuration, labelKind, onChange }: Props) {
  const { t } = useTranslation();
  const rules = configuration.deterministic!;
  const mappings = rules.field_mappings ?? [];
  const primaryTarget =
    mappings[0]?.target ??
    (labelKind === 'POSITION' ? 'position_id' : 'label_id');

  const updateRules = (patch: Partial<typeof rules>) =>
    onChange({
      ...configuration,
      recognition_mode: configuration.recognition_mode ?? 'MINIMAL',
      deterministic: { ...rules, ...patch },
    });

  const setPrimaryTarget = (target: string) => {
    const rest = mappings.slice(1).filter((m) => m.target !== target);
    onChange({
      ...configuration,
      recognition_mode: 'MINIMAL',
      required_fields: [target],
      deterministic: {
        ...rules,
        field_mappings: [{ target, source: 'WHOLE' }, ...rest],
      },
    });
  };

  const targets = labelKind === 'POSITION' ? POSITION_TARGETS : ITEM_TARGETS;

  return (
    <SectionCard title={t('clients.extraction_profile.section_basic_identity')} variant="outlined">
      <Stack spacing={1.5}>
        <Alert severity="info">{t('clients.extraction_profile.basic_identity_help')}</Alert>
        <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' } }}>
          <TextField
            select
            size="small"
            label={t('clients.extraction_profile.identity_target')}
            value={primaryTarget}
            onChange={(e) => setPrimaryTarget(e.target.value)}
          >
            {targets.map((item) => (
              <MenuItem key={item.value} value={item.value}>
                {t(item.labelKey)}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            size="small"
            label={t('clients.extraction_profile.expected_prefix')}
            value={rules.expected_prefix ?? ''}
            onChange={(e) => updateRules({ expected_prefix: e.target.value || null })}
            helperText={t('clients.extraction_profile.expected_prefix_help')}
          />
          <TextField
            size="small"
            type="number"
            label={t('clients.extraction_profile.exact_length')}
            value={rules.exact_length ?? ''}
            onChange={(e) =>
              updateRules({
                exact_length: e.target.value ? Number(e.target.value) : null,
                min_length: null,
                max_length: null,
              })
            }
            helperText={t('clients.extraction_profile.exact_length_help')}
          />
          <TextField
            select
            size="small"
            label={t('clients.extraction_profile.character_set')}
            value={rules.character_set}
            onChange={(e) => updateRules({ character_set: e.target.value as typeof rules.character_set })}
          >
            {BASIC_CHARSET_OPTIONS.map((item) => (
              <MenuItem key={item.value} value={item.value}>
                {t(item.labelKey)}
              </MenuItem>
            ))}
          </TextField>
        </Box>
        <Typography variant="caption" color="text.secondary">
          {t('clients.extraction_profile.recognition_required_vs_enrichment')}
        </Typography>
      </Stack>
    </SectionCard>
  );
}
