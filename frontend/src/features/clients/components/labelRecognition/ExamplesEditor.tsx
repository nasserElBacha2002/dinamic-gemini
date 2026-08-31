import { Box, Button, IconButton, Stack, TextField, Typography } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import { useTranslation } from 'react-i18next';
import type { PayloadExample } from '../../../../api/types';
import { SectionCard } from '../../../../components/ui';

interface Props {
  validExamples: PayloadExample[];
  invalidExamples: PayloadExample[];
  onChange: (validExamples: PayloadExample[], invalidExamples: PayloadExample[]) => void;
}

function ExampleList({ title, values, onChange }: { title: string; values: PayloadExample[]; onChange: (values: PayloadExample[]) => void }) {
  const { t } = useTranslation();
  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2">{title}</Typography>
      {values.map((example, index) => (
        <Box key={index} sx={{ display: 'grid', gap: 1, gridTemplateColumns: { xs: '1fr', md: '2fr 1fr 2fr auto' } }}>
          <TextField size="small" label={t('clients.extraction_profile.example_payload')} value={example.raw_payload} onChange={(e) => onChange(values.map((item, i) => i === index ? { ...item, raw_payload: e.target.value } : item))} />
          <TextField size="small" label={t('clients.extraction_profile.example_symbology')} value={example.symbology ?? ''} onChange={(e) => onChange(values.map((item, i) => i === index ? { ...item, symbology: e.target.value || null } : item))} />
          <TextField size="small" label={t('clients.extraction_profile.example_description')} value={example.description ?? ''} onChange={(e) => onChange(values.map((item, i) => i === index ? { ...item, description: e.target.value || null } : item))} />
          <IconButton color="error" aria-label={t('common.delete')} onClick={() => onChange(values.filter((_, i) => i !== index))}><DeleteOutlineIcon /></IconButton>
        </Box>
      ))}
      <Button size="small" startIcon={<AddIcon />} sx={{ alignSelf: 'flex-start' }} onClick={() => onChange([...values, { raw_payload: '' }])}>{t('clients.extraction_profile.add_example')}</Button>
    </Stack>
  );
}

export default function ExamplesEditor({ validExamples, invalidExamples, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <SectionCard title={t('clients.extraction_profile.section_examples')} variant="outlined">
      <Stack spacing={2}>
        <ExampleList title={t('clients.extraction_profile.valid_examples')} values={validExamples} onChange={(values) => onChange(values, invalidExamples)} />
        <ExampleList title={t('clients.extraction_profile.invalid_examples')} values={invalidExamples} onChange={(values) => onChange(validExamples, values)} />
      </Stack>
    </SectionCard>
  );
}
