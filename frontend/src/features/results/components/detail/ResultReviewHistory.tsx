/**
 * Epic 4 — Review history section for Result Detail (audit list, secondary).
 * Richer before/after audit detail is intentionally deferred to a later epic.
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
          {items.map((a) => (
            <ListItem key={a.id}>
              <ListItemText
                primary={getActionLabel(a.action)}
                secondary={
                  <>
                    {formatDate(a.createdAt)}
                    {a.userName && ` · ${a.userName}`}
                    {a.notes && ` · ${a.notes}`}
                  </>
                }
              />
            </ListItem>
          ))}
        </List>
      )}
    </Box>
  );
}
