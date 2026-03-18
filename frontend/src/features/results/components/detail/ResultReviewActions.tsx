/**
 * Epic 4 — Review actions panel for Result Detail (confirm, update quantity/SKU, delete).
 * Phase 6: Action labels and short descriptions so operators understand effect before clicking.
 */

import { useState, useEffect } from 'react';
import { Paper, Typography, Box, Button, Stack, TextField } from '@mui/material';
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
  // Temporary visible-model rule: INVALID = deleted (backend status "deleted" maps here). Do not show actions.
  const isDeleted = result.reviewStatus === 'INVALID';

  if (isDeleted) {
    return null;
  }

  return (
    <Paper sx={{ p: 2, mb: 2 }}>
      <Typography variant="subtitle1" sx={{ mb: 1.5, fontWeight: 600 }}>
        Review actions
      </Typography>
      <Stack spacing={2}>
        <Box>
          <Button
            variant="contained"
            color="primary"
            onClick={onConfirm}
            disabled={actionLoading}
          >
            {actionLoading ? 'Sending…' : 'Confirm result'}
          </Button>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
            Accept as correct without changing quantity or SKU. Marks result as reviewed.
          </Typography>
        </Box>
        <Box sx={{ pl: 1, borderLeft: 2, borderColor: 'divider', mt: 1 }}>
          <ResultFieldsForm
            result={result}
            actionLoading={actionLoading}
            onUpdateQuantity={onUpdateQuantity}
            onUpdateSku={onUpdateSku}
          />
        </Box>
        <Box>
          <Button
            variant="outlined"
            color="error"
            onClick={onDeleteClick}
            disabled={actionLoading}
          >
            Delete result
          </Button>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
            Mark result as invalid/deleted. No further review actions will be available.
          </Typography>
        </Box>
      </Stack>
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
    <>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Set corrected quantity or override SKU. Changes are saved and visible on reread.
      </Typography>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 1 }} flexWrap="wrap">
        <TextField
          size="small"
          type="number"
          label="Corrected quantity"
          value={qty}
          onChange={(e) => setQty(Number(e.target.value) || 0)}
          inputProps={{ min: 0 }}
          sx={{ width: 140 }}
        />
        <Button
          size="small"
          variant="outlined"
          onClick={() => onUpdateQuantity(Math.max(0, qty))}
          disabled={actionLoading}
        >
          Update quantity
        </Button>
      </Stack>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
        Sets the manual override quantity (replaces system count for this result).
      </Typography>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 1 }} flexWrap="wrap">
        <TextField
          size="small"
          label="SKU"
          value={sku}
          onChange={(e) => setSku(e.target.value)}
          sx={{ width: 200 }}
        />
        <Button
          size="small"
          variant="outlined"
          onClick={() => onUpdateSku(sku.trim())}
          disabled={actionLoading || !sku.trim()}
        >
          Update SKU
        </Button>
      </Stack>
      <Typography variant="caption" color="text.secondary" display="block">
        Overrides the visible SKU/classification for this result.
      </Typography>
    </>
  );
}
