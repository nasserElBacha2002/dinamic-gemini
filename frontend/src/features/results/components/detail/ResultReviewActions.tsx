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
  const [qty, setQty] = useState<number>(initialQty);
  const [sku, setSku] = useState(result.sku ?? '');

  useEffect(() => {
    setQty(result.correctedQty ?? result.detectedQty ?? 0);
  }, [result.correctedQty, result.detectedQty]);

  useEffect(() => {
    setSku(result.sku ?? '');
  }, [result.sku]);

  return (
    <Stack spacing={1} sx={{ mt: 0.75 }}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          type="number"
          label="Corrected quantity"
          value={qty}
          onChange={(e) => setQty(Number(e.target.value) || 0)}
          inputProps={{ min: 0 }}
          sx={{ width: 144 }}
        />
        <Button
          size="small"
          variant="outlined"
          onClick={() => onUpdateQuantity(Math.max(0, qty))}
          disabled={actionLoading}
          sx={{ flexShrink: 0 }}
        >
          Update quantity
        </Button>
      </Stack>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          label="SKU"
          value={sku}
          onChange={(e) => setSku(e.target.value)}
          sx={{ width: 176 }}
        />
        <Button
          size="small"
          variant="outlined"
          onClick={() => onUpdateSku(sku.trim())}
          disabled={actionLoading || !sku.trim()}
          sx={{ flexShrink: 0 }}
        >
          Update SKU
        </Button>
      </Stack>
    </Stack>
  );
}
