import { Accordion, AccordionDetails, AccordionSummary, Alert, Box, Checkbox, FormControlLabel, MenuItem, Stack, TextField, Typography } from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useTranslation } from 'react-i18next';
import type { ExtractionProfileConfiguration } from '../../../../api/types';
import { SectionCard } from '../../../../components/ui';
import { SUPPORTED_BARCODE_FORMATS } from '../../utils/defaultExtractionProfileConfiguration';

interface Props {
  configuration: ExtractionProfileConfiguration;
  onChange: (configuration: ExtractionProfileConfiguration) => void;
  /** When true, render only the advanced length/regex block (basic fields live elsewhere). */
  advancedOnly?: boolean;
}

export default function BarcodeRulesSection({ configuration, onChange, advancedOnly = false }: Props) {
  const { t } = useTranslation();
  const rules = configuration.deterministic!;
  const updateRules = (patch: Partial<typeof rules>) =>
    onChange({
      ...configuration,
      recognition_mode: 'FULL',
      deterministic: { ...rules, ...patch },
    });

  const formatsAndNormalization = (
    <Stack spacing={1.5}>
      <Typography variant="subtitle2">{t('clients.extraction_profile.barcode_formats_hint')}</Typography>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
        {SUPPORTED_BARCODE_FORMATS.map((format) => (
          <FormControlLabel
            key={format}
            control={
              <Checkbox
                size="small"
                checked={configuration.accepted_barcode_formats.includes(format)}
                onChange={(e) =>
                  onChange({
                    ...configuration,
                    accepted_barcode_formats: e.target.checked
                      ? [...configuration.accepted_barcode_formats, format]
                      : configuration.accepted_barcode_formats.filter((value) => value !== format),
                  })
                }
              />
            }
            label={format}
          />
        ))}
      </Box>

      {!advancedOnly ? (
        <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', md: '1fr 1fr 1fr' } }}>
          <TextField
            size="small"
            label={t('clients.extraction_profile.expected_prefix')}
            value={rules.expected_prefix ?? ''}
            onChange={(e) => updateRules({ expected_prefix: e.target.value || null })}
          />
          <TextField
            size="small"
            type="number"
            label={t('clients.extraction_profile.exact_length')}
            value={rules.exact_length ?? ''}
            onChange={(e) => updateRules({ exact_length: e.target.value ? Number(e.target.value) : null })}
          />
          <TextField
            select
            size="small"
            label={t('clients.extraction_profile.character_set')}
            value={rules.character_set}
            onChange={(e) => updateRules({ character_set: e.target.value as typeof rules.character_set })}
          >
            {['ANY', 'NUMERIC', 'ALPHANUMERIC', 'UPPERCASE_ALPHANUMERIC', 'ALPHANUMERIC_WITH_HYPHEN', 'HEX'].map((item) => (
              <MenuItem key={item} value={item}>{item}</MenuItem>
            ))}
          </TextField>
        </Box>
      ) : null}

      <Typography variant="subtitle2">{t('clients.extraction_profile.section_validation_advanced')}</Typography>
      <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', md: '1fr 1fr 1fr' } }}>
        <TextField
          size="small"
          label={t('clients.extraction_profile.expected_suffix')}
          value={rules.expected_suffix ?? ''}
          onChange={(e) => updateRules({ expected_suffix: e.target.value || null })}
        />
        <TextField
          size="small"
          type="number"
          label={t('clients.extraction_profile.min_length')}
          value={rules.min_length ?? ''}
          onChange={(e) => updateRules({ min_length: e.target.value ? Number(e.target.value) : null })}
        />
        <TextField
          size="small"
          type="number"
          label={t('clients.extraction_profile.max_length')}
          value={rules.max_length ?? ''}
          onChange={(e) => updateRules({ max_length: e.target.value ? Number(e.target.value) : null })}
        />
      </Box>

      <Alert severity="info">{t('clients.extraction_profile.normalization_help')}</Alert>
      <TextField
        select
        size="small"
        label={t('clients.extraction_profile.case_normalization')}
        value={rules.normalization.case_normalization}
        onChange={(e) =>
          updateRules({
            normalization: {
              ...rules.normalization,
              case_normalization: e.target.value as typeof rules.normalization.case_normalization,
            },
          })
        }
      >
        {['NONE', 'UPPER', 'LOWER'].map((value) => (
          <MenuItem key={value} value={value}>{value}</MenuItem>
        ))}
      </TextField>
      <FormControlLabel
        control={
          <Checkbox
            checked={rules.normalization.trim_outer_whitespace}
            onChange={(e) =>
              updateRules({
                normalization: { ...rules.normalization, trim_outer_whitespace: e.target.checked },
              })
            }
          />
        }
        label={t('clients.extraction_profile.trim_whitespace')}
      />
      <FormControlLabel
        control={
          <Checkbox
            checked={rules.normalization.remove_internal_spaces}
            onChange={(e) =>
              updateRules({
                normalization: { ...rules.normalization, remove_internal_spaces: e.target.checked },
              })
            }
          />
        }
        label={t('clients.extraction_profile.remove_internal_spaces')}
      />
      <FormControlLabel
        control={
          <Checkbox
            checked={rules.normalization.remove_hyphens}
            onChange={(e) =>
              updateRules({
                normalization: { ...rules.normalization, remove_hyphens: e.target.checked },
              })
            }
          />
        }
        label={t('clients.extraction_profile.remove_hyphens')}
      />

      <Accordion disableGutters elevation={0} sx={{ border: 1, borderColor: 'divider', borderRadius: 1 }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="subtitle2">{t('clients.extraction_profile.section_regex_advanced')}</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Stack spacing={1.5}>
            <FormControlLabel
              control={
                <Checkbox
                  checked={rules.use_advanced_pattern}
                  onChange={(e) => updateRules({ use_advanced_pattern: e.target.checked })}
                />
              }
              label={t('clients.extraction_profile.use_advanced_pattern')}
            />
            <TextField
              size="small"
              fullWidth
              label={t('clients.extraction_profile.custom_payload_pattern')}
              value={configuration.custom_payload_pattern ?? ''}
              onChange={(e) =>
                onChange({
                  ...configuration,
                  recognition_mode: 'FULL',
                  custom_payload_pattern: e.target.value || null,
                })
              }
              helperText={t('clients.extraction_profile.custom_payload_pattern_hint')}
            />
          </Stack>
        </AccordionDetails>
      </Accordion>
    </Stack>
  );

  if (advancedOnly) {
    return formatsAndNormalization;
  }

  return (
    <SectionCard title={t('clients.extraction_profile.section_barcode_rules')} variant="outlined">
      {formatsAndNormalization}
    </SectionCard>
  );
}
