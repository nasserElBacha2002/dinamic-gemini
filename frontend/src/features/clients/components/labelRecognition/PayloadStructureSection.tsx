import { Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { useTranslation } from 'react-i18next';
import type { DeterministicFieldMapping, ExtractionProfileConfiguration, LabelKind, PayloadStructure } from '../../../../api/types';
import { SectionCard } from '../../../../components/ui';
import FieldMappingEditor from './FieldMappingEditor';

const GS1_AIS = [
  { ai: '00', labelKey: 'clients.extraction_profile.gs1_ai_00' },
  { ai: '01', labelKey: 'clients.extraction_profile.gs1_ai_01' },
  { ai: '02', labelKey: 'clients.extraction_profile.gs1_ai_02' },
  { ai: '10', labelKey: 'clients.extraction_profile.gs1_ai_10' },
  { ai: '17', labelKey: 'clients.extraction_profile.gs1_ai_17' },
  { ai: '21', labelKey: 'clients.extraction_profile.gs1_ai_21' },
  { ai: '37', labelKey: 'clients.extraction_profile.gs1_ai_37' },
] as const;

interface Props {
  configuration: ExtractionProfileConfiguration;
  labelKind: LabelKind;
  onChange: (configuration: ExtractionProfileConfiguration) => void;
}

export default function PayloadStructureSection({ configuration, labelKind, onChange }: Props) {
  const { t } = useTranslation();
  const rules = configuration.deterministic!;
  const updateRules = (patch: Partial<typeof rules>) =>
    onChange({ ...configuration, deterministic: { ...rules, ...patch } });
  const setMappings = (field_mappings: DeterministicFieldMapping[]) => updateRules({ field_mappings });

  return (
    <SectionCard title={t('clients.extraction_profile.section_payload_structure')} variant="outlined">
      <Stack spacing={1.5}>
        <ToggleButtonGroup
          exclusive
          size="small"
          value={rules.payload_structure}
          onChange={(_, value: PayloadStructure | null) => value && updateRules({ payload_structure: value })}
        >
          <ToggleButton value="SIMPLE">{t('clients.extraction_profile.structure_simple')}</ToggleButton>
          <ToggleButton value="SEGMENTED">{t('clients.extraction_profile.structure_segmented')}</ToggleButton>
          <ToggleButton value="GS1">{t('clients.extraction_profile.structure_gs1')}</ToggleButton>
        </ToggleButtonGroup>
        {rules.payload_structure === 'SIMPLE' ? (
          <Alert severity="info">{t('clients.extraction_profile.simple_mapping_hint')}</Alert>
        ) : null}
        {rules.payload_structure === 'SEGMENTED' ? (
          <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' } }}>
            <TextField size="small" label={t('clients.extraction_profile.delimiter')} value={rules.delimiter ?? ''} onChange={(e) => updateRules({ delimiter: e.target.value || null })} />
            <TextField size="small" type="number" label={t('clients.extraction_profile.expected_segment_count')} value={rules.expected_segment_count ?? ''} onChange={(e) => updateRules({ expected_segment_count: e.target.value ? Number(e.target.value) : null })} />
          </Box>
        ) : null}
        {rules.payload_structure === 'GS1' ? (
          <Stack spacing={1.5}>
            <Alert severity="info">{t('clients.extraction_profile.gs1_ai_hint')}</Alert>
            <TextField select size="small" label={t('clients.extraction_profile.checksum_policy')} value={rules.checksum_policy} onChange={(e) => updateRules({ checksum_policy: e.target.value as typeof rules.checksum_policy })}>
              <MenuItem value="NONE">NONE</MenuItem>
              <MenuItem value="EAN_GTIN">EAN_GTIN</MenuItem>
            </TextField>
            <Typography variant="subtitle2">{t('clients.extraction_profile.required_application_identifiers')}</Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
              {GS1_AIS.map(({ ai, labelKey }) => (
                <FormControlLabel
                  key={`required-${ai}`}
                  control={
                    <Checkbox
                      size="small"
                      checked={rules.required_application_identifiers.includes(ai)}
                      onChange={(e) =>
                        updateRules({
                          required_application_identifiers: e.target.checked
                            ? [...rules.required_application_identifiers, ai]
                            : rules.required_application_identifiers.filter((value) => value !== ai),
                        })
                      }
                    />
                  }
                  label={t(labelKey)}
                />
              ))}
            </Box>
            <Typography variant="subtitle2">{t('clients.extraction_profile.optional_application_identifiers')}</Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
              {GS1_AIS.map(({ ai, labelKey }) => (
                <FormControlLabel
                  key={`optional-${ai}`}
                  control={
                    <Checkbox
                      size="small"
                      checked={rules.optional_application_identifiers.includes(ai)}
                      onChange={(e) =>
                        updateRules({
                          optional_application_identifiers: e.target.checked
                            ? [...rules.optional_application_identifiers, ai]
                            : rules.optional_application_identifiers.filter((value) => value !== ai),
                        })
                      }
                    />
                  }
                  label={t(labelKey)}
                />
              ))}
            </Box>
          </Stack>
        ) : null}
        <Typography variant="subtitle2">{t('clients.extraction_profile.field_mappings')}</Typography>
        {rules.field_mappings.map((mapping, index) => (
          <FieldMappingEditor
            key={`${mapping.target}-${index}`}
            value={mapping}
            labelKind={labelKind}
            index={index}
            onChange={(next) => setMappings(rules.field_mappings.map((item, itemIndex) => itemIndex === index ? next : item))}
            onRemove={() => setMappings(rules.field_mappings.filter((_, itemIndex) => itemIndex !== index))}
          />
        ))}
        <Button size="small" startIcon={<AddIcon />} sx={{ alignSelf: 'flex-start' }} onClick={() => setMappings([...rules.field_mappings, { target: labelKind === 'ITEM' ? 'sku' : 'position_id', source: rules.payload_structure === 'GS1' ? 'APPLICATION_IDENTIFIER' : rules.payload_structure === 'SEGMENTED' ? 'SEGMENT' : 'WHOLE' }])}>
          {t('clients.extraction_profile.add_mapping')}
        </Button>
        <Alert severity="info">
          {t('clients.extraction_profile.mapping_preview', { structure: rules.payload_structure, count: rules.field_mappings.length })}
        </Alert>
      </Stack>
    </SectionCard>
  );
}
