/**
 * **Transitional:** thin `Chip` wrapper when status → color is already computed (e.g. `getAisleStatusColor`, job status).
 * For **new** UI, prefer **StatusBadge** + `StatusBadgeSemantic` when the state maps to redesign semantics (§8.4, §11).
 * Do not introduce additional ad-hoc Chip wrappers for domain status.
 */

import { Chip } from '@mui/material';
import type { ChipColorType } from './types';

export type StatusChipColor = ChipColorType;

export interface StatusChipProps {
  label: string;
  color?: StatusChipColor;
  size?: 'small' | 'medium';
  variant?: 'filled' | 'outlined';
}

export default function StatusChip({
  label,
  color = 'default',
  size = 'small',
  variant = 'filled',
}: StatusChipProps) {
  return <Chip label={label} size={size} color={color} variant={variant} />;
}
