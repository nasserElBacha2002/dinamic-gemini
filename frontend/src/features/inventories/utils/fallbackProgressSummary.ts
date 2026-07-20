/**
 * Minimal Phase 5 fallback_progress display helpers (unit-tested).
 */
import type { FallbackProgress } from '../../../api/types/responses';

export function formatFallbackProgressSummary(
  progress: FallbackProgress,
  costPlaceholder = '—',
): string {
  const cost =
    progress.estimated_external_cost == null
      ? costPlaceholder
      : String(progress.estimated_external_cost);
  return [
    `${progress.resolved_internal} internas`,
    `${progress.fallback_requested} a fallback`,
    `${progress.resolved_external} externas`,
    `${progress.external_failed} fallidas`,
    `costo ${cost}`,
  ].join(' · ');
}

export function isFallbackProgressVisible(
  progress: FallbackProgress | null | undefined,
  flagEnabledInSnapshot: boolean,
): boolean {
  if (!progress) return false;
  if (!flagEnabledInSnapshot && progress.fallback_requested === 0) return false;
  return true;
}
