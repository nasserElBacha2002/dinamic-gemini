/**
 * Sprint 4.2 — Quick review entry point until Sprint 4.4 implements the drawer workflow.
 * Does not perform review actions; directs operators to full result review when needed today.
 */

import { Box, Button, Drawer, Typography } from '@mui/material';
import type { ReviewQueueItem } from '../../../api/types';

export interface QuickReviewDrawerProps {
  open: boolean;
  row: ReviewQueueItem | null;
  onClose: () => void;
  onOpenFullReview: () => void;
}

export default function QuickReviewDrawer({
  open,
  row,
  onClose,
  onOpenFullReview,
}: QuickReviewDrawerProps) {
  const sku = row?.position.sku?.trim() || '—';
  return (
    <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: { xs: '100%', sm: 400 }, p: 2 } }}>
      <Typography variant="h6" component="h2" gutterBottom>
        Quick review
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Inline quick actions for this result are planned for Sprint 4.4. Today, confirming or changing a result
        still requires full review (evidence and audit history).
      </Typography>
      {row ? (
        <Typography variant="body2" sx={{ mb: 2 }}>
          <strong>SKU:</strong> {sku}
        </Typography>
      ) : null}
      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        <Button variant="contained" onClick={onOpenFullReview}>
          Open full review
        </Button>
        <Button variant="text" onClick={onClose}>
          Close
        </Button>
      </Box>
    </Drawer>
  );
}
