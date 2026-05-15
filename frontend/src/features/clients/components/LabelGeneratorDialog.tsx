import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Box,
  Button,
  FormHelperText,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import type { ClientSupplier } from '../../../api/types';
import BaseDialog from '../../../components/ui/BaseDialog';
import LabelPrintSheet, { LabelPrintPortal } from './LabelPrintSheet';
import {
  clampLabelCopies,
  LABEL_COPIES_MAX,
  LABEL_COPIES_MIN,
  type LabelSheetData,
} from './labelPrintUtils';

export interface LabelGeneratorDialogProps {
  open: boolean;
  onClose: () => void;
  clientId: string;
  clientName: string;
  suppliers: ClientSupplier[];
  suppliersLoading?: boolean;
}

const EMPTY_SUPPLIER_VALUE = '';

function buildSheetData(
  clientName: string,
  supplierName: string | null,
  countedBy: string,
  code: string,
  quantity: string,
  lot: string,
  expiry: string,
  description: string,
  observations: string,
  copies: number
): LabelSheetData {
  return {
    clientName: clientName.trim() || '—',
    supplierName: supplierName?.trim() ? supplierName.trim() : null,
    countedBy: countedBy.trim() || null,
    code: code.trim(),
    quantity: quantity.trim(),
    lot: lot.trim() || null,
    expiry: expiry.trim() || null,
    description: description.trim() || null,
    observations: observations.trim() || null,
    copies: clampLabelCopies(copies),
  };
}

export default function LabelGeneratorDialog({
  open,
  onClose,
  clientName,
  suppliers,
  suppliersLoading = false,
}: LabelGeneratorDialogProps) {
  const { t } = useTranslation();
  const [supplierId, setSupplierId] = useState(EMPTY_SUPPLIER_VALUE);
  const [countedBy, setCountedBy] = useState('');
  const [code, setCode] = useState('');
  const [quantity, setQuantity] = useState('');
  const [lot, setLot] = useState('');
  const [expiry, setExpiry] = useState('');
  const [description, setDescription] = useState('');
  const [observations, setObservations] = useState('');
  const [copiesInput, setCopiesInput] = useState('1');
  const [codeError, setCodeError] = useState('');
  const [quantityError, setQuantityError] = useState('');
  const [copiesError, setCopiesError] = useState('');

  const trimmedClientName = clientName.trim() || t('clients.common.no_information');
  const copies = clampLabelCopies(Number(copiesInput));

  const selectedSupplierName = useMemo(() => {
    if (!supplierId) return null;
    return suppliers.find((s) => s.id === supplierId)?.name?.trim() ?? null;
  }, [supplierId, suppliers]);

  const sheetData = useMemo(
    () =>
      buildSheetData(
        trimmedClientName,
        selectedSupplierName,
        countedBy,
        code,
        quantity,
        lot,
        expiry,
        description,
        observations,
        copies
      ),
    [
      trimmedClientName,
      selectedSupplierName,
      countedBy,
      code,
      quantity,
      lot,
      expiry,
      description,
      observations,
      copies,
    ]
  );

  const validate = (): boolean => {
    let valid = true;
    const nextCodeError = code.trim() ? '' : t('clients.labels.validation_code_required');
    const nextQuantityError = quantity.trim() ? '' : t('clients.labels.validation_quantity_required');
    let nextCopiesError = '';
    const parsedCopies = Number(copiesInput);
    if (!copiesInput.trim() || !Number.isFinite(parsedCopies)) {
      nextCopiesError = t('clients.labels.validation_copies');
      valid = false;
    } else if (parsedCopies < LABEL_COPIES_MIN || parsedCopies > LABEL_COPIES_MAX) {
      nextCopiesError = t('clients.labels.validation_copies');
      valid = false;
    }
    if (nextCodeError) valid = false;
    if (nextQuantityError) valid = false;
    setCodeError(nextCodeError);
    setQuantityError(nextQuantityError);
    setCopiesError(nextCopiesError);
    return valid;
  };

  const canPrint = code.trim().length > 0 && quantity.trim().length > 0 && copies >= LABEL_COPIES_MIN;

  const handleClear = () => {
    setCountedBy('');
    setCode('');
    setQuantity('');
    setLot('');
    setExpiry('');
    setDescription('');
    setObservations('');
    setCopiesInput('1');
    setCodeError('');
    setQuantityError('');
    setCopiesError('');
  };

  const handleClose = () => {
    handleClear();
    setSupplierId(EMPTY_SUPPLIER_VALUE);
    onClose();
  };

  const handlePrint = () => {
    if (!validate()) return;
    window.print();
  };

  const handleCopiesBlur = () => {
    setCopiesInput(String(clampLabelCopies(Number(copiesInput))));
    if (copiesError) setCopiesError('');
  };

  return (
    <>
    <BaseDialog
      open={open}
      onClose={handleClose}
      title={t('clients.labels.dialog_title')}
      subtitle={t('clients.labels.helper_not_saved')}
      maxWidth="lg"
      actions={
        <>
          <Button onClick={handleClose}>{t('common.cancel')}</Button>
          <Button onClick={handleClear}>{t('clients.labels.clear')}</Button>
          <Button variant="contained" onClick={handlePrint} disabled={!canPrint}>
            {t('clients.labels.print')}
          </Button>
        </>
      }
    >
      <Box
        sx={{
          display: 'grid',
          gap: 3,
          gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 1fr) minmax(0, 1fr)' },
        }}
      >
        <Stack spacing={2} component="form" noValidate onSubmit={(e) => e.preventDefault()}>
          <TextField
            label={t('clients.labels.field_client')}
            value={trimmedClientName}
            fullWidth
            size="small"
            InputProps={{ readOnly: true }}
          />
          <TextField
            select
            label={t('clients.labels.field_supplier')}
            value={supplierId}
            onChange={(e) => setSupplierId(e.target.value)}
            fullWidth
            size="small"
            disabled={suppliersLoading}
            helperText={suppliersLoading ? t('common.loading') : undefined}
          >
            <MenuItem value={EMPTY_SUPPLIER_VALUE}>{t('clients.labels.supplier_empty')}</MenuItem>
            {suppliers.map((supplier) => (
              <MenuItem key={supplier.id} value={supplier.id}>
                {supplier.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            label={t('clients.labels.field_counted_by')}
            value={countedBy}
            onChange={(e) => setCountedBy(e.target.value)}
            fullWidth
            size="small"
          />
          <TextField
            label={t('clients.labels.field_code')}
            value={code}
            onChange={(e) => {
              setCode(e.target.value);
              if (codeError) setCodeError('');
            }}
            required
            fullWidth
            size="small"
            error={Boolean(codeError)}
            helperText={codeError || undefined}
          />
          <TextField
            label={t('clients.labels.field_quantity')}
            value={quantity}
            onChange={(e) => {
              setQuantity(e.target.value);
              if (quantityError) setQuantityError('');
            }}
            required
            fullWidth
            size="small"
            error={Boolean(quantityError)}
            helperText={quantityError || undefined}
          />
          <TextField
            label={t('clients.labels.field_lot')}
            value={lot}
            onChange={(e) => setLot(e.target.value)}
            fullWidth
            size="small"
          />
          <TextField
            label={t('clients.labels.field_expiry')}
            value={expiry}
            onChange={(e) => setExpiry(e.target.value)}
            fullWidth
            size="small"
            placeholder="MM/AAAA"
          />
          <TextField
            label={t('clients.labels.field_description')}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            fullWidth
            size="small"
          />
          <TextField
            label={t('clients.labels.field_observations')}
            value={observations}
            onChange={(e) => setObservations(e.target.value)}
            fullWidth
            size="small"
            multiline
            minRows={2}
          />
          <TextField
            label={t('clients.labels.copies')}
            type="number"
            value={copiesInput}
            onChange={(e) => setCopiesInput(e.target.value)}
            onBlur={handleCopiesBlur}
            inputProps={{ min: LABEL_COPIES_MIN, max: LABEL_COPIES_MAX }}
            required
            fullWidth
            size="small"
            error={Boolean(copiesError)}
            helperText={copiesError || t('clients.labels.copies_hint')}
          />
        </Stack>

        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            {t('clients.labels.preview')}
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
            {t('clients.labels.print_a4_hint')}
          </Typography>
          <LabelPrintSheet data={sheetData} mode="preview" />
          <FormHelperText sx={{ mt: 1 }}>{t('clients.labels.print_browser_hint')}</FormHelperText>
          {!canPrint ? (
            <FormHelperText sx={{ mt: 0.5 }}>{t('clients.labels.preview_requires_fields')}</FormHelperText>
          ) : null}
        </Box>
      </Box>
    </BaseDialog>
    {open ? <LabelPrintPortal data={sheetData} /> : null}
    </>
  );
}
