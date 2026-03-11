/**
 * Status chip: label + MUI color. Caller provides label and color (e.g. from status utils).
 * Use for aisle status, job status, position status to keep Chip usage consistent.
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
