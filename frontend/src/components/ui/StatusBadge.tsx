/**
 * StatusBadge — Re diseño 3.3 §8.4, §11: **preferred** presentation for product status (inventory, aisle, review, quality).
 * Uses fixed **semantic → color** mapping (§6.3). Use this for new screens when status fits the semantic vocabulary.
 *
 * **vs `StatusChip`:** `StatusChip` is the **transitional / escape hatch** when a util already maps domain → MUI
 * `Chip` color (e.g. `getAisleStatusColor`). Prefer migrating call sites to `StatusBadge` + `StatusBadgeSemantic`
 * when semantics align; do not add a third status chip pattern.
 */

import { Chip } from '@mui/material';
import type { ChipProps } from '@mui/material';
import type { ChipColorType } from './types';

/** Product semantic roles — align with §6.3 (green / orange / red / grey / blue). */
export type StatusBadgeSemantic = 'success' | 'warning' | 'error' | 'neutral' | 'info' | 'review';

const SEMANTIC_TO_CHIP_COLOR: Record<StatusBadgeSemantic, ChipColorType> = {
  success: 'success',
  warning: 'warning',
  error: 'error',
  neutral: 'default',
  info: 'info',
  /** Operational “needs attention” — same hue family as warning per redesign. */
  review: 'warning',
};

export interface StatusBadgeProps {
  label: string;
  semantic: StatusBadgeSemantic;
  size?: ChipProps['size'];
  variant?: 'filled' | 'outlined';
}

export default function StatusBadge({
  label,
  semantic,
  size = 'small',
  variant = 'outlined',
}: StatusBadgeProps) {
  return (
    <Chip
      label={label}
      size={size}
      color={SEMANTIC_TO_CHIP_COLOR[semantic]}
      variant={variant}
      sx={{ fontWeight: 500 }}
    />
  );
}
