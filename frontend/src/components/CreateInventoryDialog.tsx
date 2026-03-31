import { useEffect, useId, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardMedia,
  CircularProgress,
  IconButton,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import { createInventory, uploadInventoryVisualReferences } from '../api/client';
import type { CreateInventoryRequest, Inventory } from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';
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
  const doCreate = createInventoryFn ?? createInventory;

  const maxFiles = 3;
  const allowedTypes = useMemo(
    () => new Set(['image/jpeg', 'image/png', 'image/webp', 'image/jpg']),
    [],
  );

  const [activeStep, setActiveStep] = useState<0 | 1>(0);
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [validationError, setValidationError] = useState('');
  const [filesError, setFilesError] = useState('');
  const [pendingFiles, setPendingFiles] = useState<PendingVisualReferenceFile[]>([]);
  const [createdInventory, setCreatedInventory] = useState<Inventory | null>(null);
  const [uploadError, setUploadError] = useState('');
  const [uploadState, setUploadState] = useState<UploadState>('idle');
  const [isDraggingOver, setIsDraggingOver] = useState(false);
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
    setActiveStep(0);
    setName('');
    setValidationError('');
    setFilesError('');
    setPendingFiles([]);
    setCreatedInventory(null);
    setUploadError('');
    setUploadState('idle');
  };

  const handleClose = () => {
    if (submitting) return;
    reset();
    onClose();
  };

  const validateStep1 = (): boolean => {
    const trimmed = (name || '').trim();
    if (!trimmed) {
      setValidationError('Name is required');
      return false;
    }
    if (trimmed.length > 255) {
      setValidationError('Name must be at most 255 characters');
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
      setFilesError('Only JPG/JPEG, PNG, and WEBP files are allowed.');
      return;
    }
    if (pendingFiles.length + incoming.length > maxFiles) {
      setFilesError(`You can upload up to ${maxFiles} images.`);
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
    const created = await doCreate({ name: trimmed } as CreateInventoryRequest);
    setCreatedInventory(created);
    return created;
  };

  const uploadReferencesForInventory = async (inventoryId: string): Promise<void> => {
    if (pendingFiles.length === 0) return;
    setUploadState('uploading');
    await uploadInventoryVisualReferences(inventoryId, pendingFiles.map((p) => p.file));
    setUploadState('idle');
  };

  const handleCreateOnly = async () => {
    if (!validateStep1()) {
      setActiveStep(0);
      return;
    }
    setSubmitting(true);
    setValidationError('');
    setUploadError('');
    setUploadState('idle');
    onError(null);
    try {
      const created = await createInventoryOnce();
      onSuccess(created);
      handleClose();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      const msg = getApiErrorMessage(err, 'Failed to create inventory');
      setValidationError(typeof msg === 'string' ? msg : JSON.stringify(msg));
      onError(msg);
    } finally {
      setSubmitting(false);
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
    setSubmitting(true);
    setValidationError('');
    setUploadError('');
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
        const err = e instanceof ApiError ? e : new ApiError(String(e));
        const msg = getApiErrorMessage(err, 'Visual reference upload failed');
        setUploadState('failed');
        setUploadError(
          typeof msg === 'string'
            ? `Inventory created, but reference image upload failed: ${msg}`
            : 'Inventory created, but reference image upload failed.',
        );
      }
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      const msg = getApiErrorMessage(err, 'Failed to create inventory');
      setValidationError(typeof msg === 'string' ? msg : JSON.stringify(msg));
      onError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleRetryUploadOnly = async () => {
    if (!createdInventory) return;
    if (pendingFiles.length === 0) return;
    setSubmitting(true);
    setUploadError('');
    try {
      await uploadReferencesForInventory(createdInventory.id);
      onSuccess(createdInventory);
      handleClose();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      const msg = getApiErrorMessage(err, 'Visual reference upload failed');
      setUploadState('failed');
      setUploadError(
        typeof msg === 'string'
          ? `Inventory created, but reference image upload failed: ${msg}`
          : 'Inventory created, but reference image upload failed.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleContinueToInventory = () => {
    if (!createdInventory) return;
    onSuccess(createdInventory);
    handleClose();
  };

  const primaryCtaLabel = useMemo(() => {
    if (createdInventory) {
      if (pendingFiles.length === 0) return 'Continue to inventory';
      if (uploadState === 'failed') return 'Retry upload';
      return 'Upload references';
    }
    if (pendingFiles.length > 0) return 'Create inventory and upload references';
    return 'Create inventory';
  }, [createdInventory, pendingFiles.length, uploadState]);

  return (
    <WizardModal
      open={open}
      onClose={handleClose}
      title="Create inventory"
      stepLabels={['Inventory details', 'Visual references (optional)']}
      activeStep={activeStep}
      actions={
        activeStep === 0 ? (
          <>
            <Button onClick={handleClose} disabled={submitting}>
              Cancel
            </Button>
            <Button onClick={handleContinueToStep2} variant="contained" disabled={submitting}>
              Continue
            </Button>
          </>
        ) : (
          <>
            <Button onClick={handleClose} disabled={submitting}>
              Cancel
            </Button>
            <Button onClick={() => setActiveStep(0)} disabled={submitting || createdInventory != null}>
              Back
            </Button>
            {createdInventory ? (
              <Button onClick={handleContinueToInventory} disabled={submitting}>
                Continue without references
              </Button>
            ) : (
              <Button onClick={handleCreateOnly} disabled={submitting}>
                Create without references
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
        <TextField
          autoFocus
          margin="dense"
          label="Inventory name"
          fullWidth
          variant="outlined"
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={Boolean(validationError)}
          helperText={validationError}
          disabled={submitting || createdInventory != null}
          inputProps={{ maxLength: 255 }}
        />
      ) : (
        <Box>
          <Typography variant="h6" sx={{ mb: 1 }}>
            Reference images (optional)
          </Typography>
          <Typography variant="body2" sx={{ mb: 2, color: 'text.secondary' }}>
            These images help the system better understand what valid labels, pallets, or expected visual standards look like for this inventory.
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
            aria-label="Reference images dropzone"
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
                Drag & drop images here
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block">
                {pendingFiles.length}/{maxFiles} selected
              </Typography>
              <Typography id={dropzoneHelpId} variant="caption" color="text.secondary" display="block">
                JPG/PNG/WEBP • max {maxFiles} • or use “Select images”
              </Typography>
            </Box>
            <Button
              component="label"
              variant="outlined"
              disabled={submitting || pendingFiles.length >= maxFiles}
              size="small"
            >
              Select images
              <input
                hidden
                type="file"
                multiple
                accept="image/jpeg,image/png,image/webp"
                onChange={(e) => {
                  handleAddFiles(e.target.files);
                  e.currentTarget.value = '';
                }}
                aria-label="Select reference images"
              />
            </Button>
          </Box>

          <Typography variant="caption" display="block" sx={{ mb: 1, color: 'text.secondary' }}>
            Up to {maxFiles} images (JPG/JPEG, PNG, WEBP).
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
                        <IconButton aria-label={`Remove ${p.file.name}`} onClick={() => handleRemoveFile(idx)} disabled={submitting}>
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
              Inventory <strong>{createdInventory.name}</strong> was created. You can continue now and retry uploading references later.
            </Alert>
          ) : null}
        </Box>
      )}
    </WizardModal>
  );
}
