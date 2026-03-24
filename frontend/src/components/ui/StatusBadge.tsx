/**
 * StatusBadge — Re diseño 3.3 §8.4, §11: semantic status for inventory, aisle, review, traceability quality.
 * Maps product semantics to theme colors (§6.3); prefer this over raw Chip for domain status.
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
