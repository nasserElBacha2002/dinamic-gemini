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
import {
  confirmDinamicScannerTxtImport,
  isTxtImportFile,
  isZipImportFile,
  previewDinamicScannerTxtImport,
} from '../../../api/dinamicScannerTxtImportsApi';
import type {
  DinamicScannerTxtImportResponse,
  ImportInventorySuccess,
  LocalInventoryPackageResponse,
} from '../../../api/types';
import { ApiError } from '../../../api/types';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import BaseDialog from '../../../components/ui/BaseDialog';

export interface ImportLocalInventoryPackageDialogProps {
  open: boolean;
  inventoryId: string;
  /** Optional map of aisle_id → display label (usually aisle code). */
  aisleLabelById?: Record<string, string>;
  onClose: () => void;
  onSuccess?: (result: ImportInventorySuccess) => void;
}

type ConflictPolicy = 'SKIP' | 'REJECT';

type ImportPreview =
  | { kind: 'zip'; data: LocalInventoryPackageResponse }
  | { kind: 'txt'; data: DinamicScannerTxtImportResponse };

function invalidImportFile(file: File): boolean {
  return !isZipImportFile(file) && !isTxtImportFile(file);
}

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
  const [preview, setPreview] = useState<ImportPreview | null>(null);
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
    if (invalidImportFile(file)) {
      setError(t('inventory.import_package.invalid_file_type'));
      return;
    }
    setError(null);
    setBusy('preview');
    try {
      if (isTxtImportFile(file)) {
        const result = await previewDinamicScannerTxtImport(inventoryId, file);
        setPreview({ kind: 'txt', data: result });
      } else {
        const result = await previewLocalInventoryPackage(inventoryId, file);
        setPreview({ kind: 'zip', data: result });
      }
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
      if (preview.kind === 'txt') {
        const result = await confirmDinamicScannerTxtImport(inventoryId, {
          export_id: preview.data.csv_import.export_id,
          conflict_policy: conflictPolicy,
        });
        onSuccess?.({ kind: 'txt', data: result });
      } else {
        const result = await confirmLocalInventoryPackage(inventoryId, {
          export_id: preview.data.export_id,
          conflict_policy: conflictPolicy,
        });
        onSuccess?.({ kind: 'zip', data: result });
      }
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

  const csv =
    preview?.kind === 'zip'
      ? preview.data.csv_import
      : preview?.kind === 'txt'
        ? preview.data.csv_import
        : null;
  const rejectedSample =
    csv?.rows.filter((r) => r.status === 'REJECTED').slice(0, 5) ?? [];
  const exportId =
    preview?.kind === 'zip' ? preview.data.export_id : preview?.data.csv_import.export_id;
  const aisleId =
    preview?.kind === 'zip'
      ? preview.data.aisle_id
      : preview?.kind === 'txt'
        ? preview.data.aisle_id
        : null;
  const aisleLabel =
    preview?.kind === 'txt'
      ? preview.data.aisle_code
      : aisleId
        ? aisleLabelById?.[aisleId] ?? aisleId
        : null;

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
            accept=".zip,.txt,application/zip,text/plain"
            onChange={(e) => {
              const next = e.target.files?.[0] ?? null;
              setFile(next);
              setPreview(null);
              setError(
                next && invalidImportFile(next)
                  ? t('inventory.import_package.invalid_file_type')
                  : null
              );
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
              {preview.kind === 'zip' ? (
                t('inventory.import_package.preview_ready', {
                  exportId,
                  photos: preview.data.included_photo_count,
                  valid: csv?.valid_rows ?? 0,
                  total: csv?.total_rows ?? 0,
                  rejected: csv?.rejected_rows ?? 0,
                })
              ) : (
                t('inventory.import_package.preview_ready_txt', {
                  exportId,
                  aisle: preview.data.aisle_code,
                  positions: preview.data.positions_imported,
                  products: preview.data.products_imported,
                  omitted: preview.data.omitted_records,
                  valid: csv?.valid_rows ?? 0,
                  total: csv?.total_rows ?? 0,
                  rejected: csv?.rejected_rows ?? 0,
                })
              )}
              {aisleLabel ? (
                <Typography component="div" variant="body2" sx={{ mt: 0.75 }}>
                  {preview.kind === 'txt' && preview.data.aisle_will_be_created
                    ? t('inventory.import_package.preview_aisle_created', { aisle: aisleLabel })
                    : t('inventory.import_package.preview_aisle', { aisle: aisleLabel })}
                </Typography>
              ) : null}
            </Alert>
            {preview.kind === 'txt' && preview.data.parse_warnings.length > 0 ? (
              <Alert severity="warning" sx={{ mb: 1.5 }}>
                {t('inventory.import_package.txt_warnings_hint')}
                <Box component="ul" sx={{ m: 0, pl: 2 }}>
                  {preview.data.parse_warnings.slice(0, 5).map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </Box>
              </Alert>
            ) : null}
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
