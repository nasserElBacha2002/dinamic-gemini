import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import {
  confirmLocalInventoryPackage,
  previewLocalInventoryPackage,
} from '../../../api/localInventoryPackagesApi';
import type { LocalInventoryPackageResponse } from '../../../api/types';
import { ApiError } from '../../../api/types';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import BaseDialog from '../../../components/ui/BaseDialog';

export interface ImportLocalInventoryPackageDialogProps {
  open: boolean;
  inventoryId: string;
  /** Optional map of aisle_id → display label (usually aisle code). */
  aisleLabelById?: Record<string, string>;
  onClose: () => void;
  onSuccess?: (result: LocalInventoryPackageResponse) => void;
}

type ConflictPolicy = 'SKIP' | 'REJECT';

export default function ImportLocalInventoryPackageDialog({
  open,
  inventoryId,
  aisleLabelById,
  onClose,
  onSuccess,
}: ImportLocalInventoryPackageDialogProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<LocalInventoryPackageResponse | null>(null);
  const [conflictPolicy, setConflictPolicy] = useState<ConflictPolicy>('SKIP');
  const [busy, setBusy] = useState<'preview' | 'confirm' | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setFile(null);
    setPreview(null);
    setConflictPolicy('SKIP');
    setBusy(null);
    setError(null);
    if (inputRef.current) inputRef.current.value = '';
  }, [open]);

  const handleClose = () => {
    if (busy) return;
    onClose();
  };

  const handlePreview = async () => {
    if (!file) {
      setError(t('inventory.import_package.file_required'));
      return;
    }
    setError(null);
    setBusy('preview');
    try {
      const result = await previewLocalInventoryPackage(inventoryId, file);
      setPreview(result);
    } catch (e) {
      setPreview(null);
      setError(
        resolveApiErrorMessage(
          e instanceof ApiError ? e : new ApiError(String(e)),
          'inventory.import_package.preview_error'
        )
      );
    } finally {
      setBusy(null);
    }
  };

  const handleConfirm = async () => {
    if (!preview) return;
    setError(null);
    setBusy('confirm');
    try {
      const result = await confirmLocalInventoryPackage(inventoryId, {
        export_id: preview.export_id,
        conflict_policy: conflictPolicy,
      });
      onSuccess?.(result);
      onClose();
    } catch (e) {
      setError(
        resolveApiErrorMessage(
          e instanceof ApiError ? e : new ApiError(String(e)),
          'inventory.import_package.confirm_error'
        )
      );
    } finally {
      setBusy(null);
    }
  };

  const csv = preview?.csv_import;
  const rejectedSample =
    csv?.rows.filter((r) => r.status === 'REJECTED').slice(0, 5) ?? [];

  return (
    <BaseDialog
      open={open}
      onClose={handleClose}
      title={t('inventory.import_package.title')}
      description={t('inventory.import_package.subtitle')}
      maxWidth="sm"
      actions={
        <>
          <Button onClick={handleClose} disabled={Boolean(busy)}>
            {t('common.cancel')}
          </Button>
          {!preview ? (
            <Button
              variant="contained"
              onClick={() => void handlePreview()}
              disabled={!file || busy === 'preview'}
              data-testid="import-package-preview"
              startIcon={busy === 'preview' ? <CircularProgress size={16} color="inherit" /> : undefined}
            >
              {busy === 'preview'
                ? t('inventory.import_package.previewing')
                : t('inventory.import_package.preview')}
            </Button>
          ) : (
            <Button
              variant="contained"
              onClick={() => void handleConfirm()}
              disabled={busy === 'confirm'}
              data-testid="import-package-confirm"
              startIcon={busy === 'confirm' ? <CircularProgress size={16} color="inherit" /> : undefined}
            >
              {busy === 'confirm'
                ? t('inventory.import_package.confirming')
                : t('inventory.import_package.confirm')}
            </Button>
          )}
        </>
      }
    >
      <Stack spacing={2}>
        <Typography variant="body2" color="text.secondary">
          {t('inventory.import_package.help')}
        </Typography>
        <Button variant="outlined" component="label" disabled={Boolean(busy)} data-testid="import-package-pick-file">
          {file ? file.name : t('inventory.import_package.choose_file')}
          <input
            ref={inputRef}
            hidden
            type="file"
            accept=".zip,application/zip"
            onChange={(e) => {
              const next = e.target.files?.[0] ?? null;
              setFile(next);
              setPreview(null);
              setError(null);
            }}
          />
        </Button>

        {error ? (
          <Alert severity="error" data-testid="import-package-error">
            {error}
          </Alert>
        ) : null}

        {preview ? (
          <Box data-testid="import-package-preview-summary">
            <Alert severity="info" sx={{ mb: 1.5 }}>
              {t('inventory.import_package.preview_ready', {
                exportId: preview.export_id,
                photos: preview.included_photo_count,
                valid: csv?.valid_rows ?? 0,
                total: csv?.total_rows ?? 0,
                rejected: csv?.rejected_rows ?? 0,
              })}
              {preview.aisle_id ? (
                <Typography component="div" variant="body2" sx={{ mt: 0.75 }}>
                  {t('inventory.import_package.preview_aisle', {
                    aisle:
                      aisleLabelById?.[preview.aisle_id] ?? preview.aisle_id,
                  })}
                </Typography>
              ) : null}
            </Alert>
            <FormControl fullWidth size="small" sx={{ mb: 1.5 }}>
              <InputLabel id="import-conflict-policy">
                {t('inventory.import_package.conflict_policy')}
              </InputLabel>
              <Select
                labelId="import-conflict-policy"
                label={t('inventory.import_package.conflict_policy')}
                value={conflictPolicy}
                onChange={(e) => setConflictPolicy(e.target.value as ConflictPolicy)}
                disabled={Boolean(busy)}
              >
                <MenuItem value="SKIP">{t('inventory.import_package.conflict_skip')}</MenuItem>
                <MenuItem value="REJECT">{t('inventory.import_package.conflict_reject')}</MenuItem>
              </Select>
            </FormControl>
            {rejectedSample.length > 0 ? (
              <Alert severity="warning">
                {t('inventory.import_package.rejected_hint')}
                <Box component="ul" sx={{ m: 0, pl: 2 }}>
                  {rejectedSample.map((row) => (
                    <li key={row.row_number}>
                      #{row.row_number}: {row.validation_errors.join(', ') || row.status}
                    </li>
                  ))}
                </Box>
              </Alert>
            ) : null}
            <Button
              size="small"
              onClick={() => {
                setPreview(null);
                setError(null);
              }}
              disabled={Boolean(busy)}
            >
              {t('inventory.import_package.choose_other')}
            </Button>
          </Box>
        ) : null}
      </Stack>
    </BaseDialog>
  );
}
