/**
 * Manual coverage for one image without a result — operator-entered SKU/qty (Job image coverage).
 * Validation + double-submit guard mirror `QuickReviewDrawer`'s review action pattern.
 */

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
import { DrawerHeader, useAppSnackbar } from '../../../../components/ui';
import { ApiError } from '../../../../api/types';
import type { JobImageResultItem, PositionSummary } from '../../../../api/types';
import { useCreateManualImageResult } from '../../../../hooks';
import { getVisibleErrorMessage } from '../../../../utils/apiErrors';
import JobImageThumbnail from './JobImageThumbnail';

export interface ManualImageResultDrawerProps {
  open: boolean;
  item: JobImageResultItem | null;
  inventoryId: string;
  aisleId: string;
  jobId: string;
  onClose: () => void;
  onSuccess?: (position: PositionSummary) => void;
  /** Called on 409 (a manual result already exists) so the caller can refresh the image list. */
  onConflict?: () => void;
}

function isConflictError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409;
}

export default function ManualImageResultDrawer({
  open,
  item,
  inventoryId,
  aisleId,
  jobId,
  onClose,
  onSuccess,
  onConflict,
}: ManualImageResultDrawerProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const [sku, setSku] = useState('');
  const [quantity, setQuantity] = useState('');
  const [description, setDescription] = useState('');
  const [positionCode, setPositionCode] = useState('');
  const [skuError, setSkuError] = useState('');
  const [quantityError, setQuantityError] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const submitInFlightRef = useRef(false);

  const mutation = useCreateManualImageResult(inventoryId, aisleId, item?.source_asset_id ?? '');

  useEffect(() => {
    if (!open) return;
    setSku('');
    setQuantity('');
    setDescription('');
    setPositionCode('');
    setSkuError('');
    setQuantityError('');
    setSubmitError(null);
  }, [open, item?.image_id]);

  const validate = (): boolean => {
    let ok = true;
    const trimmedSku = sku.trim();
    if (!trimmedSku) {
      setSkuError(t('results.imageCoverage.drawer.errorSkuRequired'));
      ok = false;
    } else {
      setSkuError('');
    }

    const trimmedQty = quantity.trim();
    if (!trimmedQty) {
      setQuantityError(t('results.imageCoverage.drawer.errorQuantityRequired'));
      ok = false;
    } else if (!/^\d+$/.test(trimmedQty) || Number.parseInt(trimmedQty, 10) < 0) {
      setQuantityError(t('results.imageCoverage.drawer.errorQuantityInvalid'));
      ok = false;
    } else {
      setQuantityError('');
    }

    return ok;
  };

  const handleClose = () => {
    if (mutation.isPending) return;
    onClose();
  };

  const handleSubmit = async () => {
    if (!item) return;
    if (submitInFlightRef.current || mutation.isPending) return;
    if (!validate()) return;

    submitInFlightRef.current = true;
    setSubmitError(null);
    try {
      const result = await mutation.mutateAsync({
        job_id: jobId,
        sku: sku.trim(),
        quantity: Number.parseInt(quantity.trim(), 10),
        description: description.trim() || undefined,
        position_code: positionCode.trim() || undefined,
      });
      showSnackbar(t('results.imageCoverage.drawer.successSnackbar'), 'success');
      onSuccess?.(result.position);
      onClose();
    } catch (e) {
      const message = getVisibleErrorMessage(e, 'results');
      setSubmitError(message);
      if (isConflictError(e)) {
        showSnackbar(message, 'error');
        onConflict?.();
      }
    } finally {
      submitInFlightRef.current = false;
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={handleClose}
      PaperProps={{
        sx: {
          width: { xs: '100%', sm: 'min(480px, 96vw)' },
          maxWidth: '100vw',
          display: 'flex',
          flexDirection: 'column',
          p: 0,
        },
      }}
    >
      <DrawerHeader
        sx={{ py: 2 }}
        closeLabel={t('common.close')}
        onClose={handleClose}
        closeDisabled={mutation.isPending}
        title={
          <Typography component="h1" variant="h6" sx={{ fontWeight: 700 }}>
            {t('results.imageCoverage.drawer.title')}
          </Typography>
        }
        subtitle={
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
            {t('results.imageCoverage.drawer.subtitle')}
          </Typography>
        }
      />

      <Box sx={{ flex: 1, overflow: 'auto', px: 2.5, py: 2.5 }}>
        {item ? (
          <Stack spacing={2.5}>
            <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center' }}>
              <JobImageThumbnail
                inventoryId={inventoryId}
                aisleId={aisleId}
                sourceAssetId={item.source_asset_id}
                jobId={item.job_id}
                alt={item.original_filename ?? ''}
                size={64}
              />
              <Typography variant="body2" fontWeight={600} noWrap sx={{ minWidth: 0 }}>
                {item.original_filename?.trim() || t('results.imageCoverage.card.noFilename')}
              </Typography>
            </Box>

            {submitError ? (
              <Alert severity="error" onClose={() => setSubmitError(null)}>
                {submitError}
              </Alert>
            ) : null}

            <TextField
              label={t('results.imageCoverage.drawer.skuLabel')}
              placeholder={t('results.imageCoverage.drawer.skuPlaceholder')}
              value={sku}
              onChange={(e) => {
                setSku(e.target.value);
                if (skuError) setSkuError('');
              }}
              error={Boolean(skuError)}
              helperText={skuError || undefined}
              disabled={mutation.isPending}
              fullWidth
              autoFocus
              inputProps={{ 'data-testid': 'manual-image-result-sku' }}
            />

            <TextField
              label={t('results.imageCoverage.drawer.quantityLabel')}
              placeholder={t('results.imageCoverage.drawer.quantityPlaceholder')}
              value={quantity}
              onChange={(e) => {
                setQuantity(e.target.value);
                if (quantityError) setQuantityError('');
              }}
              error={Boolean(quantityError)}
              helperText={quantityError || undefined}
              disabled={mutation.isPending}
              fullWidth
              type="number"
              inputProps={{ min: 0, step: 1, 'data-testid': 'manual-image-result-quantity' }}
            />

            <TextField
              label={t('results.imageCoverage.drawer.descriptionLabel')}
              placeholder={t('results.imageCoverage.drawer.descriptionPlaceholder')}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={mutation.isPending}
              fullWidth
              multiline
              minRows={2}
              inputProps={{ 'data-testid': 'manual-image-result-description' }}
            />

            <TextField
              label={t('results.imageCoverage.drawer.positionCodeLabel')}
              placeholder={t('results.imageCoverage.drawer.positionCodePlaceholder')}
              value={positionCode}
              onChange={(e) => setPositionCode(e.target.value)}
              disabled={mutation.isPending}
              fullWidth
              inputProps={{ 'data-testid': 'manual-image-result-position-code' }}
            />

            <Stack direction="row" spacing={1.5} justifyContent="flex-end">
              <Button onClick={handleClose} disabled={mutation.isPending}>
                {t('results.imageCoverage.drawer.cancel')}
              </Button>
              <Button
                variant="contained"
                onClick={() => void handleSubmit()}
                disabled={mutation.isPending}
                data-testid="manual-image-result-save"
              >
                {mutation.isPending ? (
                  <CircularProgress size={18} color="inherit" />
                ) : (
                  t('results.imageCoverage.drawer.save')
                )}
              </Button>
            </Stack>
          </Stack>
        ) : null}
      </Box>
    </Drawer>
  );
}
