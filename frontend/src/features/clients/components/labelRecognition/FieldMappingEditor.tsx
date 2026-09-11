import { Box, IconButton, MenuItem, TextField } from '@mui/material';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import { useTranslation } from 'react-i18next';
import type { DeterministicFieldMapping, LabelKind } from '../../../../api/types';

const ITEM_TARGETS = ['label_id', 'sku', 'quantity', 'lot', 'serial', 'expiry_date'];
const POSITION_TARGETS = ['position_id', 'pallet', 'side', 'level'];
const GS1_AIS = ['00', '01', '02', '10', '17', '21', '37'];

interface Props {
  value: DeterministicFieldMapping;
  labelKind: LabelKind;
  index: number;
  expectedSegmentCount?: number | null;
  onChange: (value: DeterministicFieldMapping) => void;
  onRemove: () => void;
}

export default function FieldMappingEditor({
  value,
  labelKind,
  index,
  expectedSegmentCount,
  onChange,
  onRemove,
}: Props) {
  const { t } = useTranslation();
  const targets = labelKind === 'ITEM' ? ITEM_TARGETS : POSITION_TARGETS;
  const segmentIndexMissing =
    value.source === 'SEGMENT' &&
    (value.segment_index == null || Number.isNaN(Number(value.segment_index)));
  const segmentIndexInvalid =
    value.source === 'SEGMENT' &&
    value.segment_index != null &&
    (!Number.isInteger(value.segment_index) || value.segment_index < 0);
  const segmentIndexOutOfRange =
    value.source === 'SEGMENT' &&
    typeof value.segment_index === 'number' &&
    Number.isInteger(value.segment_index) &&
    typeof expectedSegmentCount === 'number' &&
    expectedSegmentCount > 0 &&
    value.segment_index >= expectedSegmentCount;
  const segmentIndexError = segmentIndexMissing
    ? t('clients.extraction_profile.segment_index_required')
    : segmentIndexInvalid
      ? t('clients.extraction_profile.segment_index_invalid')
      : segmentIndexOutOfRange
        ? t('clients.extraction_profile.segment_index_out_of_range')
        : '';
  return (
    <Box sx={{ display: 'grid', gap: 1, gridTemplateColumns: { xs: '1fr', md: '1fr 1fr 1fr auto' } }}>
      <TextField
        select
        size="small"
        label={t('clients.extraction_profile.mapping_target')}
        value={value.target}
        onChange={(event) => onChange({ ...value, target: event.target.value })}
      >
        {targets.map((target) => <MenuItem key={target} value={target}>{target}</MenuItem>)}
      </TextField>
      <TextField
        select
        size="small"
        label={t('clients.extraction_profile.mapping_source')}
        value={value.source}
        onChange={(event) => {
          const source = event.target.value as DeterministicFieldMapping['source'];
          onChange({
            ...value,
            source,
            // Suggest an index when the user chooses SEGMENT; never repair on save.
            segment_index: source === 'SEGMENT' ? (value.segment_index ?? index) : null,
            application_identifier:
              source === 'APPLICATION_IDENTIFIER' ? value.application_identifier : null,
          });
        }}
      >
        {['WHOLE', 'SEGMENT', 'APPLICATION_IDENTIFIER'].map((source) => (
          <MenuItem key={source} value={source}>{t(`clients.extraction_profile.mapping_${source.toLowerCase()}`)}</MenuItem>
        ))}
      </TextField>
      {value.source === 'SEGMENT' ? (
        <TextField
          size="small"
          type="number"
          inputProps={{ min: 0, step: 1 }}
          label={t('clients.extraction_profile.segment_index')}
          value={value.segment_index ?? ''}
          error={Boolean(segmentIndexError)}
          helperText={segmentIndexError || ' '}
          onChange={(event) => {
            const raw = event.target.value;
            if (raw === '') {
              onChange({ ...value, segment_index: null });
              return;
            }
            const parsed = Number(raw);
            onChange({
              ...value,
              segment_index: Number.isFinite(parsed) ? parsed : null,
            });
          }}
        />
      ) : value.source === 'APPLICATION_IDENTIFIER' ? (
        <TextField
          select
          size="small"
          label={t('clients.extraction_profile.application_identifier')}
          value={value.application_identifier ?? ''}
          onChange={(event) => onChange({ ...value, application_identifier: event.target.value })}
        >
          {GS1_AIS.map((ai) => <MenuItem key={ai} value={ai}>{ai}</MenuItem>)}
        </TextField>
      ) : <Box />}
      <IconButton aria-label={t('common.delete')} color="error" onClick={onRemove}>
        <DeleteOutlineIcon />
      </IconButton>
    </Box>
  );
}
