import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  TextField,
  CircularProgress,
  MenuItem,
} from '@mui/material';
import type { CreateAisleRequest } from '../api/types';
import { ApiError } from '../api/types';
import { resolveApiErrorMessage } from '../utils/apiErrors';
import { useCreateAisleAction } from '../features/inventories/hooks/useCreateAisleAction';
import { useClientSuppliers } from '../hooks/useClients';
import BaseDialog from './ui/BaseDialog';

export interface CreateAisleDialogProps {
  open: boolean;
  inventoryId: string;
  inventoryClientId?: string | null;
  onClose: () => void;
  onSuccess: () => void;
  /** Optional. Called with a message when the parent should show an error (e.g. global snackbar). */
  onError?: (message: string | null) => void;
  /** If provided, used instead of direct createAisle (e.g. TanStack Query mutation). */
  createAisleFn?: (body: CreateAisleRequest) => Promise<unknown>;
  /** Optional pre-validation: existing aisle codes in this inventory (from the current list view). */
  existingAisleCodes?: string[];
}

function normalizeApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError(String(error));
}

export default function CreateAisleDialog({
  open,
  inventoryId,
  inventoryClientId,
  onClose,
  onSuccess,
  onError,
  createAisleFn,
  existingAisleCodes,
}: CreateAisleDialogProps) {
  const { t } = useTranslation();
  const [code, setCode] = useState('');
  const [validationError, setValidationError] = useState('');
  const [supplierValidationError, setSupplierValidationError] = useState('');
  const [createdCode, setCreatedCode] = useState<string | null>(null);
  const [selectedSupplierId, setSelectedSupplierId] = useState('');
  const codeInputRef = useRef<HTMLInputElement>(null);
  const { submitCreateAisle, isSubmitting, clearError } = useCreateAisleAction({
    inventoryId,
    createAisleFn,
  });

  const normalizedExistingCodes = useMemo(() => {
    const list = existingAisleCodes ?? [];
    return new Set(list.map((c) => String(c || '').trim().toLowerCase()).filter(Boolean));
  }, [existingAisleCodes]);
  const hasInventoryClient = Boolean(inventoryClientId && inventoryClientId.trim() !== '');
  const clientIdForSuppliers = hasInventoryClient ? inventoryClientId!.trim() : undefined;
  const {
    data: suppliersData,
    isLoading: isSuppliersLoading,
    isError: isSuppliersError,
  } = useClientSuppliers(clientIdForSuppliers, { page: 1, page_size: 200 }, { enabled: hasInventoryClient });
  const suppliers = useMemo(() => suppliersData?.items ?? [], [suppliersData?.items]);
  const selectedSupplierIdTrimmed = selectedSupplierId.trim();

  const reset = () => {
    setCode('');
    setValidationError('');
    setSupplierValidationError('');
    setCreatedCode(null);
    setSelectedSupplierId('');
  };

  useEffect(() => {
    if (!open) return;
    setSelectedSupplierId('');
    setSupplierValidationError('');
  }, [inventoryClientId, open]);

  useEffect(() => {
    if (!open) return;
    if (!selectedSupplierIdTrimmed) return;
    if (!suppliers.some((s) => s.id === selectedSupplierIdTrimmed)) {
      setSelectedSupplierId('');
    }
  }, [open, selectedSupplierIdTrimmed, suppliers]);

  const handleClose = () => {
    if (!isSubmitting) {
      reset();
      onClose();
    }
  };

  const validateForSubmit = (next: string): string => {
    const trimmed = (next || '').trim();
    if (!trimmed) return t('dialogs.aisle.validation_code_required');
    if (trimmed.length > 64) return t('dialogs.aisle.validation_code_max');
    if (!inventoryId) return t('dialogs.aisle.validation_inventory_missing');
    if (normalizedExistingCodes.has(trimmed.toLowerCase())) {
      return t('dialogs.aisle.validation_duplicate');
    }
    return '';
  };

  const validateForTyping = (next: string): string => {
    const trimmed = (next || '').trim();
    // Keep typing experience calm: don't show "required" while user is editing.
    if (!trimmed) return '';
    if (trimmed.length > 64) return t('dialogs.aisle.validation_code_max');
    if (normalizedExistingCodes.has(trimmed.toLowerCase())) {
      return t('dialogs.aisle.validation_duplicate');
    }
    return '';
  };

  const handleSubmit = async () => {
    const trimmed = (code || '').trim();
    const errMsg = validateForSubmit(trimmed);
    if (errMsg) {
      setValidationError(errMsg);
      return;
    }
    if (hasInventoryClient) {
      if (isSuppliersLoading) {
        setSupplierValidationError(t('dialogs.aisle.supplier_loading'));
        return;
      }
      if (isSuppliersError) {
        setSupplierValidationError(t('dialogs.aisle.supplier_load_error'));
        return;
      }
      if (suppliers.length === 0) {
        setSupplierValidationError(t('dialogs.aisle.supplier_empty'));
        return;
      }
      if (!selectedSupplierIdTrimmed) {
        setSupplierValidationError(t('dialogs.aisle.validation_supplier_required'));
        return;
      }
    }
    setValidationError('');
    setSupplierValidationError('');
    clearError();
    try {
      await submitCreateAisle({
        code: trimmed,
        ...(hasInventoryClient && selectedSupplierIdTrimmed
          ? { client_supplier_id: selectedSupplierIdTrimmed }
          : {}),
      });
      onSuccess();
      setCreatedCode(trimmed);
    } catch (e) {
      const err = normalizeApiError(e);
      const msg = resolveApiErrorMessage(err, 'errors.create_aisle');
      if (err.status === 409) {
        setValidationError(typeof msg === 'string' ? msg : t('dialogs.aisle.validation_duplicate'));
      } else {
        const inline = typeof msg === 'string' ? msg : t('errors.create_aisle');
        setValidationError(inline);
        onError?.(inline);
      }
    }
  };

  return (
    <BaseDialog
      open={open}
      onClose={handleClose}
      disableClose={isSubmitting}
      title={t('aisle.create_title')}
      subtitle={t('aisle.create_subtitle')}
      actionsSx={{ px: 3, pb: 2 }}
      actions={
        createdCode ? (
          <>
            <Button
              onClick={() => {
                reset();
                onError?.(null);
                setCreatedCode(null);
                requestAnimationFrame(() => {
                  codeInputRef.current?.focus();
                });
              }}
            >
              {t('dialogs.aisle.create_another')}
            </Button>
            <Button onClick={handleClose} variant="contained">
              {t('common.close')}
            </Button>
          </>
        ) : (
          <>
            <Button onClick={handleClose} disabled={isSubmitting}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={handleSubmit}
              variant="contained"
              disabled={isSubmitting}
              startIcon={isSubmitting ? <CircularProgress size={16} /> : undefined}
            >
              {t('aisle.create')}
            </Button>
          </>
        )
      }
    >
      {createdCode ? (
        <Alert severity="success" sx={{ mb: 2 }}>
          {t('dialogs.aisle.success_created', { code: createdCode ?? '' })}
        </Alert>
      ) : null}

      <Box>
        <TextField
          autoFocus
          margin="dense"
          label={t('aisle.code_label')}
          fullWidth
          variant="outlined"
          value={code}
          onChange={(e) => {
            const next = e.target.value;
            setCode(next);
            if (!validationError) return;
            const nextMsg = validateForTyping(next);
            setValidationError(nextMsg);
            if (!nextMsg) onError?.(null);
          }}
          error={Boolean(validationError)}
          helperText={validationError || ' '}
          disabled={isSubmitting || Boolean(createdCode)}
          inputProps={{ maxLength: 64 }}
          inputRef={codeInputRef}
          onBlur={() => {
            if (createdCode) return;
            const msg = validateForSubmit(code);
            setValidationError(msg);
          }}
        />
        <TextField
          sx={{ mt: 1 }}
          select
          label={t('dialogs.aisle.supplier_label')}
          fullWidth
          value={selectedSupplierId}
          onChange={(e) => {
            setSelectedSupplierId(e.target.value);
            if (supplierValidationError) setSupplierValidationError('');
            onError?.(null);
          }}
          disabled={isSubmitting || Boolean(createdCode) || !hasInventoryClient || isSuppliersLoading}
          error={Boolean(supplierValidationError) || (hasInventoryClient && isSuppliersError)}
          helperText={
            supplierValidationError ||
            (hasInventoryClient
              ? isSuppliersLoading
                ? t('dialogs.aisle.supplier_loading')
                : isSuppliersError
                  ? t('dialogs.aisle.supplier_load_error')
                  : suppliers.length === 0
                    ? t('dialogs.aisle.supplier_empty')
                    : t('dialogs.aisle.supplier_helper')
              : t('dialogs.aisle.supplier_legacy_helper'))
          }
        >
          <MenuItem value="">{t('dialogs.aisle.supplier_none_option')}</MenuItem>
          {suppliers.map((supplier) => (
            <MenuItem key={supplier.id} value={supplier.id}>
              {supplier.name}
            </MenuItem>
          ))}
        </TextField>
      </Box>
    </BaseDialog>
  );
}
