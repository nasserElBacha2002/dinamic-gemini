import { Alert, Checkbox, FormControlLabel, MenuItem, Stack, TextField } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { ExtractionProfileConfiguration } from '../../../../api/types';
import { SectionCard } from '../../../../components/ui';

interface Props {
  configuration: ExtractionProfileConfiguration;
  onChange: (configuration: ExtractionProfileConfiguration) => void;
}

export default function QuantityRulesSection({ configuration, onChange }: Props) {
  const { t } = useTranslation();
  const rules = configuration.quantity_rules;
  const update = (patch: Partial<typeof rules>) =>
    onChange({ ...configuration, quantity_rules: { ...rules, ...patch } });

  return (
    <SectionCard title={t('clients.extraction_profile.section_quantity_v2')} variant="outlined">
      <Stack spacing={1.5}>
        <Alert severity="info">{t('clients.extraction_profile.quantity_no_default_warning')}</Alert>
        <TextField
          size="small"
          fullWidth
          label={t('clients.extraction_profile.quantity_aliases')}
          value={(rules.aliases ?? []).join(', ')}
          onChange={(e) =>
            update({
              aliases: e.target.value
                .split(',')
                .map((value) => value.trim())
                .filter(Boolean),
            })
          }
          helperText={t('clients.extraction_profile.comma_separated_hint')}
        />
        <TextField
          select
          size="small"
          label={t('clients.extraction_profile.quantity_expected_presence')}
          value={rules.expected_presence ?? 'ALWAYS'}
          onChange={(e) => update({ expected_presence: e.target.value as typeof rules.expected_presence })}
        >
          <MenuItem value="ALWAYS">{t('clients.extraction_profile.presence_always')}</MenuItem>
          <MenuItem value="OPTIONAL">{t('clients.extraction_profile.presence_optional')}</MenuItem>
          <MenuItem value="UNKNOWN">{t('clients.extraction_profile.presence_unknown')}</MenuItem>
        </TextField>
        <TextField
          select
          size="small"
          label={t('clients.extraction_profile.quantity_missing_action')}
          value={rules.missing_quantity_action ?? 'PENDING_MANUAL_REVIEW'}
          onChange={(e) =>
            update({ missing_quantity_action: e.target.value as typeof rules.missing_quantity_action })
          }
        >
          <MenuItem value="PENDING_MANUAL_REVIEW">{t('clients.extraction_profile.missing_action_manual')}</MenuItem>
          <MenuItem value="EXTERNAL_FALLBACK">{t('clients.extraction_profile.missing_action_external')}</MenuItem>
          <MenuItem value="UNRECOGNIZED">{t('clients.extraction_profile.missing_action_unrecognized')}</MenuItem>
        </TextField>
        <FormControlLabel
          control={
            <Checkbox
              checked={Boolean(rules.required)}
              onChange={(e) => update({ required: e.target.checked })}
            />
          }
          label={t('clients.extraction_profile.quantity_required_auto')}
        />
        <FormControlLabel
          control={
            <Checkbox
              checked={Boolean(rules.allow_decimals)}
              onChange={(e) => update({ allow_decimals: e.target.checked })}
            />
          }
          label={t('clients.extraction_profile.quantity_allow_decimals')}
        />
      </Stack>
    </SectionCard>
  );
}
