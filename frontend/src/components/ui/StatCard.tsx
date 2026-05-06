/**
 * Thin wrapper over `KpiCard` — same `label` / `value` API only (no `description`, no drill-down).
 *
 * @deprecated Prefer {@link KpiCard} for metric summaries (`description`, `onClick`, redesign §8.3 / §14.6).
 * Export kept for compatibility; validate removal in **F8** dead-code pass (no in-repo usages as of F7.4).
 */

import type { ReactNode } from 'react';
import KpiCard from './KpiCard';

/** @deprecated Use {@link KpiCardProps} via `KpiCard` instead. */
export interface StatCardProps {
  label: string;
  value: ReactNode;
}

/** @deprecated See {@link StatCardProps}. */
export default function StatCard({ label, value }: StatCardProps) {
  return <KpiCard label={label} value={value} />;
}
