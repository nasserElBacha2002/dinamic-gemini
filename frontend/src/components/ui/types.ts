/**
 * Shared UI types — used by StatusChip, TraceabilityChip, etc.
 * Keeps chip color and similar contracts in one place.
 */

/** MUI Chip color prop — shared by StatusChip and TraceabilityChip. */
export type ChipColorType =
  | 'default'
  | 'primary'
  | 'secondary'
  | 'error'
  | 'info'
  | 'success'
  | 'warning';
