/**
 * Epic 4 / Sprint 4.3 — Review actions: confirm (primary path), corrections, destructive (separated).
 */

import { useState, useEffect } from 'react';
import { Paper, Typography, Box, Button, Stack, TextField, Divider } from '@mui/material';
import type { ResultDetail } from '../../types';

export interface ResultReviewActionsProps {
  result: ResultDetail;
  actionLoading: boolean;
  onConfirm: () => void;
  onUpdateQuantity: (quantity: number) => void;
  onUpdateSku: (sku: string) => void;
  onDeleteClick: () => void;
}

export default function ResultReviewActions({
  result,
  actionLoading,
  onConfirm,
  onUpdateQuantity,
  onUpdateSku,
  onDeleteClick,
}: ResultReviewActionsProps) {
  const isDeleted = result.reviewStatus === 'INVALID';

  if (isDeleted) {
    return null;
  }

  return (
    <Paper
      sx={{
        p: 2,
        mb: 2,
        border: 1,
        borderColor: 'divider',
      }}
      elevation={0}
    >
      <Typography variant="subtitle1" sx={{ mb: 2, fontWeight: 600 }}>
        Review actions
      </Typography>

      <Box>
        <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 0.5 }}>
          Confirm
        </Typography>
        <Button
          variant="contained"
          color="primary"
          size="large"
          fullWidth
          onClick={onConfirm}
          disabled={actionLoading}
          sx={{ mt: 0.75, py: 1 }}
        >
          {actionLoading ? 'Sending…' : 'Confirm result'}
        </Button>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.75 }}>
          Accept as correct. Marks the result as reviewed without changing quantity or SKU.
        </Typography>
      </Box>

      <Divider sx={{ my: 1.75 }} />

      <Box>
        <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 0.5 }}>
          Corrections
        </Typography>
        <ResultFieldsForm
          result={result}
          actionLoading={actionLoading}
          onUpdateQuantity={onUpdateQuantity}
          onUpdateSku={onUpdateSku}
        />
      </Box>

      <Divider sx={{ my: 1.75 }} />

      <Box
        sx={{
          p: 1.5,
          borderRadius: 1,
          bgcolor: 'action.hover',
          border: 1,
          borderColor: 'error.light',
        }}
      >
        <Typography variant="overline" color="error" sx={{ letterSpacing: 0.5 }}>
          Invalidate result
        </Typography>
        <Button
          variant="outlined"
          color="error"
          fullWidth
          onClick={onDeleteClick}
          disabled={actionLoading}
          sx={{ mt: 1 }}
        >
          Mark result invalid
        </Button>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.75 }}>
          Sets review status to invalid and removes this row from active review work. The record stays visible
          for audit. Requires confirmation.
        </Typography>
      </Box>
    </Paper>
  );
}

const SKU_MAX_LEN = 128;

function ResultFieldsForm({
  result,
  actionLoading,
  onUpdateQuantity,
  onUpdateSku,
}: {
  result: ResultDetail;
  actionLoading: boolean;
  onUpdateQuantity: (quantity: number) => void;
  onUpdateSku: (sku: string) => void;
}) {
  const initialQty = result.correctedQty ?? result.detectedQty ?? 0;
  const [qtyStr, setQtyStr] = useState(String(initialQty));
  const [sku, setSku] = useState(result.sku ?? '');
  const [qtyError, setQtyError] = useState('');
  const [skuError, setSkuError] = useState('');

  useEffect(() => {
    const n = result.correctedQty ?? result.detectedQty ?? 0;
    setQtyStr(String(n));
    setQtyError('');
  }, [result.correctedQty, result.detectedQty]);

  useEffect(() => {
    setSku(result.sku ?? '');
    setSkuError('');
  }, [result.sku]);

  const submitQuantity = () => {
    const trimmed = qtyStr.trim();
    if (trimmed.includes('.') || trimmed.includes('e') || trimmed.includes('E')) {
      setQtyError('Enter a whole number 0 or greater.');
      return;
    }
    const n = Number.parseInt(trimmed, 10);
    if (trimmed === '' || Number.isNaN(n) || n < 0) {
      setQtyError('Enter a whole number 0 or greater.');
      return;
    }
    setQtyError('');
    onUpdateQuantity(n);
  };

  const submitSku = () => {
    const t = sku.trim();
    if (!t) {
      setSkuError('SKU is required.');
      return;
    }
    if (t.length > SKU_MAX_LEN) {
      setSkuError(`SKU must be at most ${SKU_MAX_LEN} characters.`);
      return;
    }
    setSkuError('');
    onUpdateSku(t);
  };

  return (
    <Stack spacing={1} sx={{ mt: 0.75 }}>
      <Stack direction="row" spacing={1} alignItems="flex-start" flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          type="text"
          inputMode="numeric"
          label="Corrected quantity"
          value={qtyStr}
          onChange={(e) => {
            setQtyStr(e.target.value);
            if (qtyError) setQtyError('');
          }}
          inputProps={{ inputMode: 'numeric' }}
          error={Boolean(qtyError)}
          helperText={qtyError || ' '}
          sx={{ width: 160 }}
        />
        <Button
          size="small"
          variant="outlined"
          onClick={submitQuantity}
          disabled={actionLoading}
          sx={{ flexShrink: 0, mt: 0.5 }}
        >
          Update quantity
        </Button>
      </Stack>
      <Stack direction="row" spacing={1} alignItems="flex-start" flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          label="SKU"
          value={sku}
          onChange={(e) => {
            setSku(e.target.value);
            if (skuError) setSkuError('');
          }}
          error={Boolean(skuError)}
          helperText={skuError || ' '}
          inputProps={{ maxLength: SKU_MAX_LEN }}
          sx={{ width: 200 }}
        />
        <Button
          size="small"
          variant="outlined"
          onClick={submitSku}
          disabled={actionLoading}
          sx={{ flexShrink: 0, mt: 0.5 }}
        >
          Update SKU
        </Button>
      </Stack>
    </Stack>
  );
}
