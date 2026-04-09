/**
 * Epic 4 — Review history section for Result Detail (audit list).
 * Phase 6: Human-readable change summary from before_json/after_json when available.
 */

import { Box, Typography, List, ListItem, ListItemText } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import type { ReviewHistoryItem } from '../../types';
import { formatDate } from '../../../../utils/formatDate';

function getActionLabel(action: string, t: TFunction): string {
  switch (action) {
    case 'confirm':
      return t('review_history.action_confirm');
    case 'update_quantity':
      return t('review_history.action_update_quantity');
    case 'update_sku':
      return t('review_history.action_update_sku');
    case 'delete_position':
      return t('review_history.action_delete_position');
    default:
      return action;
  }
}

/** Build a short change summary from before/after JSON for known action types. Fallback when payloads are partial. */
function getChangeSummary(item: ReviewHistoryItem, t: TFunction): string | null {
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
        return t('review_history.summary_status', { before: String(before.status), after: String(after.status) });
      }
      return t('review_history.summary_confirmed');
    }
    case 'update_quantity': {
      if (!hasPayload) return null;
      const b = before.corrected_quantity;
      const a = after.corrected_quantity;
      if (a != null && b !== undefined) return t('review_history.summary_quantity', { before: b, after: a });
      if (a != null) return t('review_history.summary_quantity_set', { value: a });
      return null;
    }
    case 'update_sku': {
      if (!hasPayload) return null;
      const b = before.sku;
      const a = after.sku;
      if (a != null && b != null) return t('review_history.summary_sku', { before: String(b), after: String(a) });
      if (a != null) return t('review_history.summary_sku_set', { value: String(a) });
      return null;
    }
    case 'delete_position': {
      if (hasPayload && after.status != null && before.status != null) {
        return t('review_history.summary_status', { before: String(before.status), after: String(after.status) });
      }
      return t('review_history.summary_invalid');
    }
    default:
      return null;
  }
}

export interface ResultReviewHistoryProps {
  items: ReviewHistoryItem[];
  /** When false, omit section heading (e.g. parent SectionCard provides the title). */
  showHeading?: boolean;
}

export default function ResultReviewHistory({ items, showHeading = true }: ResultReviewHistoryProps) {
  const { t } = useTranslation();

  return (
    <Box sx={{ mt: showHeading ? 2 : 0 }}>
      {showHeading ? (
        <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
          {t('review_history.heading', { count: items.length })}
        </Typography>
      ) : null}
      {items.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {t('review_history.empty')}
        </Typography>
      ) : (
        <List dense sx={{ bgcolor: 'action.hover', borderRadius: 1 }}>
          {items.map((a) => {
            const summary = getChangeSummary(a, t);
            const secondary = [summary, formatDate(a.createdAt), a.userName ? a.userName : '', a.notes ? a.notes : '']
              .filter(Boolean)
              .join(' · ');
            return (
              <ListItem key={a.id}>
                <ListItemText primary={getActionLabel(a.action, t)} secondary={secondary || undefined} />
              </ListItem>
            );
          })}
        </List>
      )}
    </Box>
  );
}
