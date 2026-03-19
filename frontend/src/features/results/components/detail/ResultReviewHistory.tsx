/**
 * Epic 4 — Review history section for Result Detail (audit list).
 * Phase 6: Human-readable change summary from before_json/after_json when available.
 */

import { Box, Typography, List, ListItem, ListItemText } from '@mui/material';
import type { ReviewHistoryItem } from '../../types';
import { formatDate } from '../../../../utils/formatDate';

const ACTION_LABELS: Record<string, string> = {
  confirm: 'Confirm',
  update_quantity: 'Update quantity',
  update_sku: 'Update SKU',
  delete_position: 'Delete result',
};

function getActionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}

/** Build a short change summary from before/after JSON for known action types. Fallback when payloads are partial. */
function getChangeSummary(item: ReviewHistoryItem): string | null {
  const before = item.beforeJson;
  const after = item.afterJson;
  const hasPayload =
    before != null &&
    after != null &&
    typeof before === 'object' &&
    typeof after === 'object';

  switch (item.action) {
    case 'confirm': {
      if (hasPayload && after.status != null && before.status != null) {
        return `Status: ${String(before.status)} → ${String(after.status)}`;
      }
      return 'Status confirmed';
    }
    case 'update_quantity': {
      if (!hasPayload) return null;
      const b = before.corrected_quantity;
      const a = after.corrected_quantity;
      if (a != null && b !== undefined) return `Quantity: ${b} → ${a}`;
      if (a != null) return `Quantity set to ${a}`;
      return null;
    }
    case 'update_sku': {
      if (!hasPayload) return null;
      const b = before.sku;
      const a = after.sku;
      if (a != null && b != null) return `SKU: ${String(b)} → ${String(a)}`;
      if (a != null) return `SKU set to ${String(a)}`;
      return null;
    }
    case 'delete_position': {
      if (hasPayload && after.status != null && before.status != null) {
        return `Status: ${String(before.status)} → ${String(after.status)}`;
      }
      return 'Result removed';
    }
    default:
      return null;
  }
}

export interface ResultReviewHistoryProps {
  items: ReviewHistoryItem[];
}

export default function ResultReviewHistory({ items }: ResultReviewHistoryProps) {
  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
        Review history ({items.length})
      </Typography>
      {items.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No review actions yet.
        </Typography>
      ) : (
        <List dense sx={{ bgcolor: 'action.hover', borderRadius: 1 }}>
          {items.map((a) => {
            const summary = getChangeSummary(a);
            const secondary = [
              summary,
              formatDate(a.createdAt),
              a.userName ? a.userName : '',
              a.notes ? a.notes : '',
            ]
              .filter(Boolean)
              .join(' · ');
            return (
              <ListItem key={a.id}>
                <ListItemText
                  primary={getActionLabel(a.action)}
                  secondary={secondary || undefined}
                />
              </ListItem>
            );
          })}
        </List>
      )}
    </Box>
  );
}
