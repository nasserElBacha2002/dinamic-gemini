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
  onChange: (value: DeterministicFieldMapping) => void;
  onRemove: () => void;
}

export default function FieldMappingEditor({ value, labelKind, index, onChange, onRemove }: Props) {
  const { t } = useTranslation();
  const targets = labelKind === 'ITEM' ? ITEM_TARGETS : POSITION_TARGETS;
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
        onChange={(event) =>
          onChange({
            ...value,
            source: event.target.value as DeterministicFieldMapping['source'],
            segment_index: null,
            application_identifier: null,
          })
        }
      >
        {['WHOLE', 'SEGMENT', 'APPLICATION_IDENTIFIER'].map((source) => (
          <MenuItem key={source} value={source}>{t(`clients.extraction_profile.mapping_${source.toLowerCase()}`)}</MenuItem>
        ))}
      </TextField>
      {value.source === 'SEGMENT' ? (
        <TextField
          size="small"
          type="number"
          inputProps={{ min: 0 }}
          label={t('clients.extraction_profile.segment_index')}
          value={value.segment_index ?? index}
          onChange={(event) => onChange({ ...value, segment_index: Number(event.target.value) })}
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
