import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Drawer,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { DrawerHeader, useAppSnackbar } from '../../components/ui';
import { useCreateManualImageResult } from '../../hooks';
import { getVisibleErrorMessage } from '../../utils/apiErrors';
import { ResultEvidenceViewer } from '../results/components/detail';

export interface ManualResultFormProps {
  open: boolean;
  onClose: () => void;
  inventoryId: string;
  aisleId: string;
  jobId: string;
  assetId: string;
  fileName?: string | null;
  onSuccess?: () => void;
}

export default function ManualResultForm({
  open,
  onClose,
  inventoryId,
  aisleId,
  jobId,
  assetId,
  fileName,
  onSuccess,
}: ManualResultFormProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const [sku, setSku] = useState('');
  const [quantity, setQuantity] = useState('');
  const [description, setDescription] = useState('');
  const [positionCode, setPositionCode] = useState('');
  const [skuError, setSkuError] = useState('');
  const [quantityError, setQuantityError] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [evidenceState, setEvidenceState] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle');
  const submitInFlightRef = useRef(false);

  const mutation = useCreateManualImageResult(inventoryId, aisleId, assetId);
  const saveDisabled = mutation.isPending || evidenceState !== 'loaded';

  useEffect(() => {
    if (!open) return;
    setSku('');
    setQuantity('');
    setDescription('');
    setPositionCode('');
    setSkuError('');
    setQuantityError('');
    setSubmitError(null);
    setEvidenceState('idle');
  }, [open, assetId]);

  const validate = (): boolean => {
    let ok = true;
    if (!sku.trim()) {
      setSkuError(t('results.imageCoverage.drawer.errorSkuRequired'));
      ok = false;
    } else {
      setSkuError('');
    }
    const trimmedQty = quantity.trim();
    if (!trimmedQty || !/^\d+$/.test(trimmedQty) || Number.parseInt(trimmedQty, 10) <= 0) {
      setQuantityError(t('results.imageCoverage.drawer.errorQuantityInvalid'));
      ok = false;
    } else {
      setQuantityError('');
    }
    return ok;
  };

  const handleSubmit = async () => {
    if (submitInFlightRef.current || mutation.isPending || !validate()) return;
    submitInFlightRef.current = true;
    setSubmitError(null);
    try {
      await mutation.mutateAsync({
        job_id: jobId,
        sku: sku.trim(),
        quantity: Number.parseInt(quantity.trim(), 10),
        description: description.trim() || undefined,
        position_code: positionCode.trim() || undefined,
      });
      showSnackbar(t('processing.manual.success'), 'success');
      onSuccess?.();
      onClose();
    } catch (e) {
      setSubmitError(getVisibleErrorMessage(e, 'default'));
      showSnackbar(t('processing.manual.failed'), 'error');
    } finally {
      submitInFlightRef.current = false;
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={() => {
        if (!mutation.isPending) onClose();
      }}
      PaperProps={{ sx: { width: { xs: '100%', sm: 420 } } }}
    >
      <DrawerHeader
        title={
          <Typography variant="h6" component="h2">
            {t('processing.manual.title')}
          </Typography>
        }
        subtitle={
          fileName ? (
            <Typography variant="body2" color="text.secondary">
              {fileName}
            </Typography>
          ) : undefined
        }
        onClose={onClose}
        closeLabel={t('common.close')}
        closeDisabled={mutation.isPending}
      />
      <Box sx={{ p: 2.5, overflow: 'auto' }}>
        <Stack spacing={2}>
          <ResultEvidenceViewer
            inventoryId={inventoryId}
            aisleId={aisleId}
            assetId={assetId}
            jobId={jobId}
            filename={fileName}
            enabled={open}
            onAssetLoadStateChange={setEvidenceState}
          />
          <TextField
            label={t('results.imageCoverage.drawer.skuLabel')}
            value={sku}
            onChange={(e) => setSku(e.target.value)}
            error={Boolean(skuError)}
            helperText={skuError || undefined}
            fullWidth
            size="small"
          />
          <TextField
            label={t('results.imageCoverage.drawer.quantityLabel')}
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            error={Boolean(quantityError)}
            helperText={quantityError || undefined}
            fullWidth
            size="small"
          />
          <TextField
            label={t('results.imageCoverage.drawer.descriptionLabel')}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            fullWidth
            size="small"
            multiline
            minRows={2}
          />
          <TextField
            label={t('results.imageCoverage.drawer.positionCodeLabel')}
            value={positionCode}
            onChange={(e) => setPositionCode(e.target.value)}
            fullWidth
            size="small"
          />
          {submitError ? <Alert severity="error">{submitError}</Alert> : null}
          <Button
            variant="contained"
            onClick={() => void handleSubmit()}
            disabled={saveDisabled}
            startIcon={mutation.isPending ? <CircularProgress size={16} color="inherit" /> : undefined}
          >
            {mutation.isPending ? t('common.saving') : t('processing.manual.save')}
          </Button>
        </Stack>
      </Box>
    </Drawer>
  );
}
