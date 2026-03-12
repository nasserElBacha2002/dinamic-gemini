/**
 * Epic 4 — Review actions panel for Result Detail (confirm, update quantity/SKU, delete).
 */

import { useState, useEffect } from 'react';
import { Paper, Typography, Box, Button, Stack, TextField } from '@mui/material';
import type { ResultDetail, ResultProductInfo } from '../../types';

export interface ResultReviewActionsProps {
  result: ResultDetail;
  actionLoading: boolean;
  onConfirm: () => void;
  onUpdateQuantity: (productId: string, quantity: number) => void;
  onUpdateSku: (productId: string, sku: string, description?: string) => void;
  onDeleteClick: () => void;
}

function ProductReviewForm({
  product,
  detectedQty,
  actionLoading,
  onUpdateQuantity,
  onUpdateSku,
}: {
  product: ResultProductInfo;
  detectedQty: number | null;
  actionLoading: boolean;
  onUpdateQuantity: (productId: string, quantity: number) => void;
  onUpdateSku: (productId: string, sku: string, description?: string) => void;
}) {
  const initialQty = product.correctedQty ?? detectedQty ?? 0;
  const [qty, setQty] = useState<number>(initialQty);
  const [sku, setSku] = useState(product.sku ?? '');
  const [desc, setDesc] = useState(product.description ?? '');

  useEffect(() => {
    setQty(product.correctedQty ?? detectedQty ?? 0);
  }, [product.correctedQty, detectedQty]);
  useEffect(() => {
    setSku(product.sku ?? '');
    setDesc(product.description ?? '');
  }, [product.sku, product.description]);

  const productId = product.productId ?? '';

  return (
    <Box sx={{ pl: 1, borderLeft: 2, borderColor: 'divider', mt: 1 }}>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Product: {product.sku ?? '—'} {productId ? `(id: ${productId})` : ''}
      </Typography>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 1 }} flexWrap="wrap">
        <TextField
          size="small"
          type="number"
          label="Corrected quantity"
          value={qty}
          onChange={(e) => setQty(Number(e.target.value) || 0)}
          inputProps={{ min: 0 }}
          sx={{ width: 120 }}
        />
        <Button
          size="small"
          variant="outlined"
          onClick={() => onUpdateQuantity(productId, Math.max(0, qty))}
          disabled={actionLoading || !productId}
        >
          Update quantity
        </Button>
      </Stack>
      <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
        <TextField
          size="small"
          label="SKU"
          value={sku}
          onChange={(e) => setSku(e.target.value)}
          sx={{ width: 160 }}
        />
        <TextField
          size="small"
          label="Description (optional)"
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          sx={{ width: 200 }}
        />
        <Button
          size="small"
          variant="outlined"
          onClick={() => onUpdateSku(productId, sku.trim(), desc.trim() || undefined)}
          disabled={actionLoading || !sku.trim() || !productId}
        >
          Update SKU
        </Button>
      </Stack>
    </Box>
  );
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
        </Box>
        {result.product && (
          <ProductReviewForm
            product={result.product}
            detectedQty={result.detectedQty}
            actionLoading={actionLoading}
            onUpdateQuantity={onUpdateQuantity}
            onUpdateSku={onUpdateSku}
          />
        )}
        <Box>
          <Button
            variant="outlined"
            color="error"
            onClick={onDeleteClick}
            disabled={actionLoading}
          >
            Delete result
          </Button>
        </Box>
      </Stack>
    </Paper>
  );
}
