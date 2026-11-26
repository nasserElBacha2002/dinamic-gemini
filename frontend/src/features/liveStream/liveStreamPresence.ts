import type { LiveStreamPresence } from '../../api/liveStreamApi';

export function isPublisherActivePresence(presence: LiveStreamPresence): boolean {
  return presence === 'live' || presence === 'connecting' || presence === 'reconnecting';
}

export function isApiNotPreparedError(error: unknown): boolean {
  if (typeof error !== 'object' || error === null) return false;
  const status = 'status' in error ? (error as { status?: number }).status : undefined;
  const data = 'data' in error ? (error as { data?: { code?: string } }).data : undefined;
  return status === 409 && data?.code === 'LIVE_STREAM_NOT_PREPARED';
}