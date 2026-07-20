import type { TFunction } from 'i18next';
import type { StatusBadgeSemantic } from '../../../components/ui/StatusBadge';

export function processingStatusToSemantic(status: string | null | undefined): StatusBadgeSemantic {
  const normalized = String(status ?? '').toLowerCase();
  if (
    normalized === 'resolved' ||
    normalized === 'completed' ||
    normalized === 'succeeded' ||
    normalized === 'persisted'
  ) {
    return 'success';
  }
  if (
    normalized === 'failed' ||
    normalized === 'error' ||
    normalized === 'external_failed' ||
    normalized === 'persistence_failed'
  ) {
    return 'error';
  }
  if (
    normalized === 'manual_review' ||
    normalized === 'pending' ||
    normalized === 'queued' ||
    normalized === 'fallback_requested'
  ) {
    return 'review';
  }
  if (normalized === 'processing' || normalized === 'running' || normalized === 'starting') {
    return 'info';
  }
  if (normalized === 'cancelled' || normalized === 'canceled' || normalized === 'skipped') {
    return 'warning';
  }
  return 'neutral';
}

export function processingStatusLabel(status: string | null | undefined, t: TFunction): string {
  const normalized = String(status ?? '').trim();
  if (!normalized) return t('common.em_dash');
  const key = `processing.status.${normalized.toLowerCase()}`;
  const translated = t(key, { defaultValue: '' });
  if (translated) return translated;
  return normalized;
}

export function processingErrorCodeMessage(code: string | null | undefined, t: TFunction): string {
  const normalized = String(code ?? '').trim();
  if (!normalized) return t('common.em_dash');
  const key = `processing.errors.${normalized}`;
  const translated = t(key, { defaultValue: '' });
  if (translated) return translated;
  return t('processing.errors.unknown_code', { code: normalized });
}

export function formatDurationMs(ms: number | null | undefined, t: TFunction): string {
  if (ms == null || !Number.isFinite(ms)) return t('common.em_dash');
  if (ms < 1000) return t('processing.duration_ms', { value: ms });
  const seconds = Math.round(ms / 100) / 10;
  return t('processing.duration_seconds', { value: seconds });
}

export function shortAssetId(assetId: string): string {
  const s = assetId.trim();
  if (s.length <= 14) return s;
  return `${s.slice(0, 8)}…${s.slice(-4)}`;
}
