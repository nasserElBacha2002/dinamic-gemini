import { useState } from 'react';
import { Alert, Button, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { testSupplierLabelRecognitionCode } from '../../../../api/clientSuppliersApi';
import type { ExtractionProfileConfiguration, LabelKind, TestLabelRecognitionCodeResponse } from '../../../../api/types';
import { SectionCard } from '../../../../components/ui';

interface Props {
  clientId: string;
  supplierId: string;
  labelKind: LabelKind;
  configuration: ExtractionProfileConfiguration;
}

export default function LabelRecognitionTester({ clientId, supplierId, labelKind, configuration }: Props) {
  const { t } = useTranslation();
  const [payload, setPayload] = useState('');
  const [symbology, setSymbology] = useState('');
  const [result, setResult] = useState<TestLabelRecognitionCodeResponse | null>(null);
  const [error, setError] = useState(false);
  const [testing, setTesting] = useState(false);

  const handleTest = async () => {
    setTesting(true);
    setError(false);
    try {
      setResult(await testSupplierLabelRecognitionCode(clientId, supplierId, {
        label_kind: labelKind,
        raw_payload: payload,
        symbology: symbology || null,
        configuration,
      }));
    } catch {
      setResult(null);
      setError(true);
    } finally {
      setTesting(false);
    }
  };

  return (
    <SectionCard title={t('clients.extraction_profile.section_tester')} variant="outlined">
      <Stack spacing={1.5}>
        <Alert severity="info">{t('clients.extraction_profile.tester_non_persistent')}</Alert>
        <TextField size="small" fullWidth label={t('clients.extraction_profile.test_payload')} value={payload} onChange={(e) => setPayload(e.target.value)} />
        <TextField select size="small" label={t('clients.extraction_profile.example_symbology')} value={symbology} onChange={(e) => setSymbology(e.target.value)}>
          <MenuItem value="">{t('clients.extraction_profile.symbology_unspecified')}</MenuItem>
          {configuration.accepted_barcode_formats.map((format) => <MenuItem key={format} value={format}>{format}</MenuItem>)}
        </TextField>
        <Button variant="outlined" disabled={!payload.trim() || testing} onClick={() => void handleTest()} sx={{ alignSelf: 'flex-start' }}>{t('clients.extraction_profile.run_test')}</Button>
        {error ? <Alert severity="error">{t('clients.extraction_profile.test_error')}</Alert> : null}
        {result ? (
          <Alert severity={result.validation_status === 'VALID' ? 'success' : 'warning'}>
            <Typography variant="body2">{t('clients.extraction_profile.test_status', { status: result.validation_status })}</Typography>
            <Typography component="pre" variant="caption" sx={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(result.extracted_fields, null, 2)}</Typography>
          </Alert>
        ) : null}
      </Stack>
    </SectionCard>
  );
}
