import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardMedia,
  CircularProgress,
  FormLabel,
  IconButton,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import type { CreateInventoryRequest, Inventory, InventoryProcessingMode } from '../api/types';
import { resolveApiErrorMessage } from '../utils/apiErrors';
import { useCreateInventoryFlow } from '../features/inventories/hooks/useCreateInventoryFlow';
import WizardModal from './ui/WizardModal';

type PendingVisualReferenceFile = { file: File; previewUrl: string };
type UploadState = 'idle' | 'uploading' | 'failed';

export interface CreateInventoryDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (created: Inventory) => void;
  onError: (message: string | null) => void;
  /** If provided, used instead of direct createInventory (e.g. TanStack Query mutation). */
  createInventoryFn?: (body: CreateInventoryRequest) => Promise<Inventory>;
}

export default function CreateInventoryDialog({
  open,
  onClose,
  onSuccess,
  onError,
  createInventoryFn,
}: CreateInventoryDialogProps) {
  const { t } = useTranslation();
  const {
    submitCreateInventory,
    submitUploadInventoryReferences,
    isCreating,
    isUploadingReferences,
    clearError,
  } = useCreateInventoryFlow({ createInventoryFn });
  const submitting = isCreating || isUploadingReferences;

  const maxFiles = 3;
  const allowedTypes = useMemo(
    () => new Set(['image/jpeg', 'image/png', 'image/webp', 'image/jpg']),
    [],
  );

  const [activeStep, setActiveStep] = useState<0 | 1>(0);
  const [name, setName] = useState('');
  const [validationError, setValidationError] = useState('');
  const [filesError, setFilesError] = useState('');
  const [pendingFiles, setPendingFiles] = useState<PendingVisualReferenceFile[]>([]);
  const [createdInventory, setCreatedInventory] = useState<Inventory | null>(null);
  const [uploadError, setUploadError] = useState('');
  const [uploadState, setUploadState] = useState<UploadState>('idle');
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const [processingMode, setProcessingMode] = useState<InventoryProcessingMode>('production');
  const dragDepthRef = useRef(0);
  const dropzoneHelpId = useId();

  const pendingFilesRef = useRef<PendingVisualReferenceFile[]>([]);
  useEffect(() => {
    pendingFilesRef.current = pendingFiles;
  }, [pendingFiles]);

  const revokeAllPreviews = (files: PendingVisualReferenceFile[]) => {
    files.forEach((p) => {
      try {
        URL.revokeObjectURL(p.previewUrl);
      } catch {
        // ignore
      }
    });
  };

  // Cleanup previews when dialog unmounts or closes (avoid stale closure by using a ref).
  useEffect(() => {
    if (!open) return;
    return () => revokeAllPreviews(pendingFilesRef.current);
  }, [open]);

  const reset = () => {
    revokeAllPreviews(pendingFiles);
    pendingFilesRef.current = [];
    setActiveStep(0);
    setName('');
    setValidationError('');
    setFilesError('');
    setPendingFiles([]);
    setCreatedInventory(null);
    setUploadError('');
    setUploadState('idle');
    setProcessingMode('production');
  };

  const handleClose = () => {
    if (submitting) return;
    reset();
    onClose();
  };

  const validateStep1 = (): boolean => {
    const trimmed = (name || '').trim();
    if (!trimmed) {
      setValidationError(t('dialogs.inventory.validation_name_required'));
      return false;
    }
    if (trimmed.length > 255) {
      setValidationError(t('dialogs.inventory.validation_name_max'));
      return false;
    }
    return true;
  };

  const handleContinueToStep2 = () => {
    if (!validateStep1()) return;
    setValidationError('');
    setActiveStep(1);
  };

  const handleAddFiles = (files: FileList | null) => {
    setFilesError('');
    if (!files || files.length === 0) return;
    const incoming = Array.from(files);
    const invalid = incoming.find((f) => !allowedTypes.has((f.type || '').toLowerCase()));
    if (invalid) {
      setFilesError(t('dialogs.inventory.files_type_error'));
      return;
    }
    if (pendingFiles.length + incoming.length > maxFiles) {
      setFilesError(t('dialogs.inventory.max_files_error', { max: maxFiles }));
      return;
    }
    const next = incoming.map((file) => ({ file, previewUrl: URL.createObjectURL(file) }));
    setPendingFiles((prev) => [...prev, ...next]);
    // If the user changes the selection after a failed upload, treat it as a fresh retry.
    setUploadError('');
    setUploadState('idle');
  };

  const handleDropFiles = (files: FileList | null) => {
    dragDepthRef.current = 0;
    setIsDraggingOver(false);
    handleAddFiles(files);
  };

  const handleRemoveFile = (idx: number) => {
    setPendingFiles((prev) => {
      const item = prev[idx];
      if (item) {
        try {
          URL.revokeObjectURL(item.previewUrl);
        } catch {
          // ignore
        }
      }
      return prev.filter((_, i) => i !== idx);
    });
  };

  const createInventoryOnce = async (): Promise<Inventory> => {
    if (createdInventory) return createdInventory;
    const trimmed = (name || '').trim();
    const created = await submitCreateInventory({
      name: trimmed,
      processing_mode: processingMode,
    } satisfies CreateInventoryRequest);
    setCreatedInventory(created);
    return created;
  };

  const uploadReferencesForInventory = async (inventoryId: string): Promise<void> => {
    if (pendingFiles.length === 0) return;
    setUploadState('uploading');
    await submitUploadInventoryReferences(inventoryId, pendingFiles.map((p) => p.file));
    setUploadState('idle');
  };

  const handleCreateOnly = async () => {
    if (!validateStep1()) {
      setActiveStep(0);
      return;
    }
    setValidationError('');
    setUploadError('');
    setUploadState('idle');
    clearError();
    onError(null);
    try {
      const created = await createInventoryOnce();
      onSuccess(created);
      handleClose();
    } catch (e) {
      const err = e as unknown;
      const msg = resolveApiErrorMessage(err, 'errors.create_inventory');
      setValidationError(typeof msg === 'string' ? msg : JSON.stringify(msg));
      onError(msg);
    }
  };

  const handleCreateThenUpload = async () => {
    if (!validateStep1()) {
      setActiveStep(0);
      return;
    }
    if (pendingFiles.length === 0) {
      await handleCreateOnly();
      return;
    }
    setValidationError('');
    setUploadError('');
    clearError();
    onError(null);
    try {
      const created = await createInventoryOnce();
      try {
        await uploadReferencesForInventory(created.id);
        onSuccess(created);
        handleClose();
      } catch (e) {
        // Important: inventory exists now. Do not call onError (parent would show "create failed").
        // Keep the dialog open in "retry upload" mode.
        const err = e as unknown;
        const msg = resolveApiErrorMessage(err, 'errors.reference_upload_failed');
        setUploadState('failed');
        setUploadError(
          typeof msg === 'string'
            ? t('dialogs.inventory.partial_failure_detail', { message: msg })
            : t('dialogs.inventory.partial_failure_generic'),
        );
      }
    } catch (e) {
      const err = e as unknown;
      const msg = resolveApiErrorMessage(err, 'errors.create_inventory');
      setValidationError(typeof msg === 'string' ? msg : JSON.stringify(msg));
      onError(msg);
    }
  };

  const handleRetryUploadOnly = async () => {
    if (!createdInventory) return;
    if (pendingFiles.length === 0) return;
    setUploadError('');
    clearError();
    try {
      await uploadReferencesForInventory(createdInventory.id);
      onSuccess(createdInventory);
      handleClose();
    } catch (e) {
      const err = e as unknown;
      const msg = resolveApiErrorMessage(err, 'errors.reference_upload_failed');
      setUploadState('failed');
      setUploadError(
        typeof msg === 'string'
          ? t('dialogs.inventory.partial_failure_detail', { message: msg })
          : t('dialogs.inventory.partial_failure_generic'),
      );
    }
  };

  const handleContinueToInventory = () => {
    if (!createdInventory) return;
    onSuccess(createdInventory);
    handleClose();
  };

  const primaryCtaLabel = useMemo(() => {
    if (createdInventory) {
      if (pendingFiles.length === 0) return t('dialogs.inventory.continue_to_inventory');
      if (uploadState === 'failed') return t('dialogs.inventory.retry_upload');
      return t('dialogs.inventory.upload_references');
    }
    if (pendingFiles.length > 0) return t('dialogs.inventory.create_and_upload');
    return t('dialogs.inventory.create_inventory_action');
  }, [createdInventory, pendingFiles.length, uploadState, t]);

  return (
    <WizardModal
      open={open}
      onClose={handleClose}
      title={t('dialogs.inventory.wizard_title')}
      stepLabels={t('dialogs.inventory.step_labels').split('|')}
      activeStep={activeStep}
      actions={
        activeStep === 0 ? (
          <>
            <Button onClick={handleClose} disabled={submitting}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleContinueToStep2} variant="contained" disabled={submitting}>
              {t('common.continue')}
            </Button>
          </>
        ) : (
          <>
            <Button onClick={handleClose} disabled={submitting}>
              {t('common.cancel')}
            </Button>
            <Button onClick={() => setActiveStep(0)} disabled={submitting || createdInventory != null}>
              {t('common.back')}
            </Button>
            {createdInventory ? (
              <Button onClick={handleContinueToInventory} disabled={submitting}>
                {t('dialogs.inventory.continue_without_refs')}
              </Button>
            ) : (
              <Button onClick={handleCreateOnly} disabled={submitting}>
                {t('dialogs.inventory.create_without_refs')}
              </Button>
            )}
            <Button
              onClick={() => {
                if (createdInventory) {
                  if (pendingFiles.length === 0) return handleContinueToInventory();
                  return handleRetryUploadOnly();
                }
                return handleCreateThenUpload();
              }}
              variant="contained"
              disabled={submitting}
            >
              {submitting ? <CircularProgress size={24} /> : primaryCtaLabel}
            </Button>
          </>
        )
      }
      maxWidth="sm"
      fullWidth
    >
      {activeStep === 0 ? (
        <Stack spacing={2}>
          <TextField
            autoFocus
            margin="dense"
            label={t('dialogs.inventory.inventory_name')}
            fullWidth
            variant="outlined"
            value={name}
            onChange={(e) => setName(e.target.value)}
            error={Boolean(validationError)}
            helperText={validationError}
            disabled={submitting || createdInventory != null}
            inputProps={{ maxLength: 255 }}
          />
          <Box>
            <FormLabel component="legend">{t('dialogs.inventory.processing_mode_label')}</FormLabel>
            <ToggleButtonGroup
              exclusive
              value={processingMode}
              onChange={(_, v: InventoryProcessingMode | null) => {
                if (v != null) setProcessingMode(v);
              }}
              size="small"
              sx={{ mt: 1 }}
              disabled={submitting || createdInventory != null}
            >
              <ToggleButton value="production">{t('dialogs.inventory.processing_mode_real')}</ToggleButton>
              <ToggleButton value="test">{t('dialogs.inventory.processing_mode_test')}</ToggleButton>
            </ToggleButtonGroup>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
              {processingMode === 'production'
                ? t('dialogs.inventory.processing_mode_real_help')
                : t('dialogs.inventory.processing_mode_test_help')}
            </Typography>
          </Box>
        </Stack>
      ) : (
        <Box>
          <Typography variant="h6" sx={{ mb: 1 }}>
            {t('dialogs.inventory.reference_step_title')}
          </Typography>
          <Typography variant="body2" sx={{ mb: 2, color: 'text.secondary' }}>
            {t('dialogs.inventory.reference_step_body')}
          </Typography>

          {filesError ? (
            <Alert severity="error" sx={{ mb: 2 }}>
              {filesError}
            </Alert>
          ) : null}
          {uploadError ? (
            <Alert severity="warning" sx={{ mb: 2 }}>
              {uploadError}
            </Alert>
          ) : null}

          <Box
            onDragEnter={(e) => {
              e.preventDefault();
              e.stopPropagation();
              dragDepthRef.current += 1;
              setIsDraggingOver(true);
            }}
            onDragOver={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setIsDraggingOver(true);
            }}
            onDragLeave={(e) => {
              e.preventDefault();
              e.stopPropagation();
              // Avoid flicker when moving across children inside the dropzone.
              const nextTarget = e.relatedTarget as Node | null;
              if (nextTarget && e.currentTarget.contains(nextTarget)) return;
              dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
              if (dragDepthRef.current === 0) setIsDraggingOver(false);
            }}
            onDrop={(e) => {
              e.preventDefault();
              e.stopPropagation();
              handleDropFiles(e.dataTransfer?.files ?? null);
            }}
            role="region"
            aria-label={t('dialogs.inventory.reference_dropzone')}
            aria-describedby={dropzoneHelpId}
            sx={{
              mb: 2,
              p: 2,
              borderRadius: 1,
              border: '1px dashed',
              borderColor: isDraggingOver ? 'primary.main' : 'divider',
              bgcolor: isDraggingOver ? 'action.hover' : 'transparent',
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 1.5,
            }}
          >
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {t('dialogs.inventory.dropzone_primary')}
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block">
                {t('dialogs.inventory.selected_ratio', { count: pendingFiles.length, max: maxFiles })}
              </Typography>
              <Typography id={dropzoneHelpId} variant="caption" color="text.secondary" display="block">
                {t('dialogs.inventory.dropzone_formats_line', { max: maxFiles })}
              </Typography>
            </Box>
            <Button
              component="label"
              variant="outlined"
              disabled={submitting || pendingFiles.length >= maxFiles}
              size="small"
            >
              {t('dialogs.inventory.select_files')}
              <input
                hidden
                type="file"
                multiple
                accept="image/jpeg,image/png,image/webp"
                onChange={(e) => {
                  handleAddFiles(e.target.files);
                  e.currentTarget.value = '';
                }}
                aria-label={t('dialogs.inventory.select_files')}
              />
            </Button>
          </Box>

          <Typography variant="caption" display="block" sx={{ mb: 1, color: 'text.secondary' }}>
            {t('dialogs.inventory.footer_formats', { max: maxFiles })}
          </Typography>

          {pendingFiles.length > 0 ? (
            <Stack spacing={1}>
              {pendingFiles.map((p, idx) => (
                <Card key={`${p.file.name}-${idx}`} variant="outlined">
                  <Box sx={{ display: 'flex', alignItems: 'stretch' }}>
                    <CardMedia
                      component="img"
                      image={p.previewUrl}
                      alt={p.file.name}
                      sx={{ width: 96, height: 96, objectFit: 'cover' }}
                    />
                    <CardContent sx={{ flex: 1, py: 1.5 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <Box sx={{ pr: 1, minWidth: 0 }}>
                          <Typography variant="subtitle2" noWrap>
                            {p.file.name}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {(p.file.size / 1024).toFixed(1)} KB
                          </Typography>
                        </Box>
                        <IconButton
                          aria-label={t('dialogs.inventory.remove_file_a11y', { name: p.file.name })}
                          onClick={() => handleRemoveFile(idx)}
                          disabled={submitting}
                        >
                          <CloseRoundedIcon fontSize="small" />
                        </IconButton>
                      </Box>
                    </CardContent>
                  </Box>
                </Card>
              ))}
            </Stack>
          ) : null}

          {createdInventory && uploadError ? (
            <Alert severity="info" sx={{ mt: 2 }}>
              {t('dialogs.inventory.partial_info', { name: createdInventory.name })}
            </Alert>
          ) : null}
        </Box>
      )}
    </WizardModal>
  );
}
