/**
 * Epic 3.1.B — Traceability status chip.
 * Shows valid/missing/invalid/unvalidated with semantic colors.
 * Use when displaying source_image_id traceability from backend.
 */

import { Chip, Tooltip } from '@mui/material';
import type { TraceabilityStatus } from '../../api/types';
import type { ChipColorType } from './types';

const TRACEABILITY_COLOR: Record<TraceabilityStatus, ChipColorType> = {
  valid: 'success',
  missing: 'default',
  invalid: 'error',
  unvalidated: 'info',
};

const TRACEABILITY_LABEL: Record<TraceabilityStatus, string> = {
  valid: 'Valid',
  missing: 'Missing',
  invalid: 'Invalid',
  unvalidated: 'Unvalidated',
};

export type { TraceabilityStatus };

export interface TraceabilityChipProps {
  status: TraceabilityStatus;
  size?: 'small' | 'medium';
  variant?: 'filled' | 'outlined';
  /** Optional tooltip (e.g. traceability_warning when status is invalid). */
  tooltip?: string | null;
}

export default function TraceabilityChip({
  status,
  size = 'small',
  variant = 'outlined',
  tooltip,
}: TraceabilityChipProps) {
  const color = TRACEABILITY_COLOR[status];
  const label = TRACEABILITY_LABEL[status];
  const chip = (
    <Chip
      label={label}
      size={size}
      color={color}
      variant={variant}
    />
  );
  if (tooltip && tooltip.trim()) {
    return (
      <Tooltip title={tooltip} placement="top">
        <span>{chip}</span>
      </Tooltip>
    );
  }
  return chip;
}
