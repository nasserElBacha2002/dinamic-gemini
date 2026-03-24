/**
 * Thin wrapper over `KpiCard` — same `label` / `value` API.
 * Prefer importing `KpiCard` for new code (description, onClick for §14.6 drill-down).
 */

import type { ReactNode } from 'react';
import KpiCard from './KpiCard';

export interface StatCardProps {
  label: string;
  value: ReactNode;
}

export default function StatCard({ label, value }: StatCardProps) {
  return <KpiCard label={label} value={value} />;
}
