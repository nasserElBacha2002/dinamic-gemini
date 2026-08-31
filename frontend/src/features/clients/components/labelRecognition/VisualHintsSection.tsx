import { Alert, Box, Checkbox, FormControlLabel, MenuItem, Stack, TextField } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { ExtractionProfileConfiguration } from '../../../../api/types';
import { SectionCard } from '../../../../components/ui';

interface Props {
  configuration: ExtractionProfileConfiguration;
  visualNotes: string;
  onConfigurationChange: (configuration: ExtractionProfileConfiguration) => void;
  onVisualNotesChange: (notes: string) => void;
}

export default function VisualHintsSection({
  configuration,
  visualNotes,
  onConfigurationChange,
  onVisualNotesChange,
}: Props) {
  const { t } = useTranslation();
  const hints = configuration.label_detection_rules ?? {};
  const updateHints = (patch: Record<string, unknown>) =>
    onConfigurationChange({ ...configuration, label_detection_rules: { ...hints, ...patch } });

  const asCsv = (values: unknown): string =>
    Array.isArray(values) ? values.map(String).join(', ') : '';

  const parseCsv = (value: string): string[] =>
    value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);

  return (
    <SectionCard title={t('clients.extraction_profile.section_visual_ai_help')} variant="outlined">
      <Stack spacing={1.5}>
        <Alert severity="info">{t('clients.extraction_profile.visual_hints_not_validation')}</Alert>
        <TextField
          select
          size="small"
          label={t('clients.extraction_profile.label_background')}
          value={hints.expected_background ?? 'VARIABLE'}
          onChange={(e) => updateHints({ expected_background: e.target.value })}
        >
          {['LIGHT', 'DARK', 'VARIABLE', 'DISABLED'].map((value) => (
            <MenuItem key={value} value={value}>
              {t(`clients.extraction_profile.bg_${value.toLowerCase()}`)}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label={t('clients.extraction_profile.label_shape')}
          value={hints.expected_shape ?? 'APPROXIMATELY_RECTANGULAR'}
          onChange={(e) => updateHints({ expected_shape: e.target.value })}
        >
          <MenuItem value="RECTANGULAR">{t('clients.extraction_profile.shape_rectangular')}</MenuItem>
          <MenuItem value="APPROXIMATELY_RECTANGULAR">{t('clients.extraction_profile.shape_approx')}</MenuItem>
          <MenuItem value="VARIABLE">{t('clients.extraction_profile.shape_variable')}</MenuItem>
        </TextField>
        <TextField
          select
          size="small"
          label={t('clients.extraction_profile.label_orientation')}
          value={hints.expected_orientation ?? 'ANY'}
          onChange={(e) => updateHints({ expected_orientation: e.target.value })}
        >
          <MenuItem value="ANY">{t('clients.extraction_profile.orient_any')}</MenuItem>
          <MenuItem value="HORIZONTAL">{t('clients.extraction_profile.orient_horizontal')}</MenuItem>
          <MenuItem value="VERTICAL">{t('clients.extraction_profile.orient_vertical')}</MenuItem>
          <MenuItem value="SQUARE_OR_VERTICAL">{t('clients.extraction_profile.orient_square')}</MenuItem>
        </TextField>
        <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', md: '1fr 1fr 1fr' } }}>
          <TextField
            size="small"
            type="number"
            label={t('clients.extraction_profile.approx_width_mm')}
            value={hints.approx_width_mm ?? ''}
            onChange={(e) =>
              updateHints({ approx_width_mm: e.target.value ? Number(e.target.value) : null })
            }
            helperText={t('clients.extraction_profile.size_hint_help')}
          />
          <TextField
            size="small"
            type="number"
            label={t('clients.extraction_profile.approx_height_mm')}
            value={hints.approx_height_mm ?? ''}
            onChange={(e) =>
              updateHints({ approx_height_mm: e.target.value ? Number(e.target.value) : null })
            }
          />
          <TextField
            size="small"
            type="number"
            label={t('clients.extraction_profile.size_tolerance_percent')}
            value={hints.size_tolerance_percent ?? ''}
            onChange={(e) =>
              updateHints({
                size_tolerance_percent: e.target.value ? Number(e.target.value) : null,
              })
            }
          />
        </Box>
        <TextField
          size="small"
          fullWidth
          label={t('clients.extraction_profile.label_primary_anchors')}
          value={asCsv(hints.primary_anchors)}
          onChange={(e) => updateHints({ primary_anchors: parseCsv(e.target.value) })}
          helperText={t('clients.extraction_profile.visual_anchors_hint')}
        />
        <TextField
          size="small"
          fullWidth
          label={t('clients.extraction_profile.label_secondary_anchors')}
          value={asCsv(hints.secondary_anchors)}
          onChange={(e) => updateHints({ secondary_anchors: parseCsv(e.target.value) })}
        />
        <FormControlLabel
          control={
            <Checkbox
              checked={Boolean(hints.allow_rotation ?? true)}
              onChange={(e) => updateHints({ allow_rotation: e.target.checked })}
            />
          }
          label={t('clients.extraction_profile.label_allow_rotation')}
        />
        <FormControlLabel
          control={
            <Checkbox
              checked={Boolean(hints.allow_perspective_correction ?? true)}
              onChange={(e) => updateHints({ allow_perspective_correction: e.target.checked })}
            />
          }
          label={t('clients.extraction_profile.label_allow_perspective')}
        />
        <TextField
          multiline
          minRows={3}
          fullWidth
          label={t('clients.extraction_profile.visual_notes_label')}
          value={visualNotes}
          onChange={(e) => onVisualNotesChange(e.target.value)}
        />
      </Stack>
    </SectionCard>
  );
}
