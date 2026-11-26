import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import { apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export type HlsLiveAuthMode = 'basic' | 'session' | 'none';

/** Prefix relative API playlist paths with ``VITE_API_BASE_URL``. */
export function resolveLiveStreamPlaylistUrl(playlistUrl: string): string {
  const trimmed = playlistUrl.trim();
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    return trimmed;
  }
  let base = API_BASE.replace(/\/$/, '');
  const path = trimmed;
  if (path.startsWith('/api/v3') && base.endsWith('/api/v3')) {
    base = base.slice(0, -'/api/v3'.length);
  }
  if (path.startsWith('/')) {
    return `${base}${path}`;
  }
  return `${base}/${path}`;
}

export function inferLiveStreamAuthMode(playlistPathOrUrl: string): HlsLiveAuthMode {
  const url = playlistPathOrUrl.trim();
  if (url.includes('/api/public/live/') && url.includes('/hls/')) {
    return 'none';
  }
  if (url.includes('/live-stream/hls/')) {
    return 'session';
  }
  return 'basic';
}

export type LiveStreamPresence =
  | 'no_stream'
  | 'connecting'
  | 'live'
  | 'reconnecting'
  | 'ended'
  | 'service_unavailable';

export interface LiveStreamStatus {
  presence: LiveStreamPresence;
  publisher_ready: boolean;
  bytes_received: number | null;
  publish_blocked: boolean;
}

export interface LiveStreamStopResponse {
  aisle_code: string;
  canonical_aisle_code: string;
  mediamtx_path: string;
  publisher_kicked: boolean;
  status: LiveStreamStatus;
}

export interface LiveStreamPrepareResponse {
  inventory_id: string;
  aisle_code: string;
  canonical_aisle_code: string;
  channel_slug: string;
  mediamtx_path: string;
  aisle_id: string | null;
  rtmp_publish_url: string;
  publish_username: string;
  publish_password: string;
  read_username: string;
  read_password: string;
  hls_playlist_url: string;
  status: LiveStreamStatus;
}

export interface PublicLiveGrantResponse {
  grant_id: string;
  public_url: string;
  expires_at: string;
  view_username: string;
  view_password: string;
}

export interface PublicLivePlaybackResponse {
  presence: LiveStreamPresence;
  hls_playlist_url: string;
  view_username: string;
  view_password: string;
  expires_at: string;
  publish_blocked: boolean;
}

export async function prepareLiveStream(
  inventoryId: string,
  aisleCode: string,
): Promise<LiveStreamPrepareResponse> {
  const url = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/live-stream/prepare`;
  return apiRequestJson<LiveStreamPrepareResponse>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ aisle_code: aisleCode }),
  });
}

export async function getLiveStreamStatus(
  inventoryId: string,
  aisleCode: string,
): Promise<LiveStreamStatus> {
  const qs = new URLSearchParams({ aisle_code: aisleCode });
  const url = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/live-stream/status?${qs}`;
  return apiRequestJson<LiveStreamStatus>(url);
}

export async function stopLiveStream(
  inventoryId: string,
  aisleCode: string,
): Promise<LiveStreamStopResponse> {
  const url = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/live-stream/stop`;
  return apiRequestJson<LiveStreamStopResponse>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ aisle_code: aisleCode }),
  });
}

export async function createPublicLiveGrant(
  inventoryId: string,
  aisleCode: string,
  ttlHours?: number,
): Promise<PublicLiveGrantResponse> {
  const url = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/live-stream/public-grants`;
  return apiRequestJson<PublicLiveGrantResponse>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ aisle_code: aisleCode, ttl_hours: ttlHours ?? null }),
  });
}

export async function revokePublicLiveGrant(inventoryId: string, grantId: string): Promise<void> {
  const url = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/live-stream/public-grants/${encodeURIComponent(grantId)}`;
  await apiRequestJson<void>(url, { method: 'DELETE' });
}

export async function getPublicLivePlayback(token: string): Promise<PublicLivePlaybackResponse> {
  const url = `${API_BASE}/api/public/live/${encodeURIComponent(token)}`;
  return apiRequestJson<PublicLivePlaybackResponse>(url);
}