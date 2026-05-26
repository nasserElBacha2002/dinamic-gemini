/**
 * Shared image-display-url resolution (aisle source assets + supplier reference images).
 * Presigned remote URLs are returned for direct <img src>; local/legacy uses authenticated /file blob.
 */

import { getStoredToken } from '../features/auth/storage';
import i18n from '../i18n';
import { protectedFetch } from '../api/http';

export type FetchReferenceImageDisplayResult =
  | { ok: true; imageSrc: string; revoke?: () => void }
  | { ok: false; status: number; detail?: string };

async function readOptionalDetail(response: Response): Promise<string | undefined> {
  try {
    const data = (await response.json()) as { detail?: unknown };
    return typeof data?.detail === 'string' ? data.detail : undefined;
  } catch {
    return undefined;
  }
}

async function fetchAuthorizedFileAsBlob(fileUrl: string): Promise<FetchReferenceImageDisplayResult> {
  const token = getStoredToken();
  const headers = new Headers();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  try {
    const response = await fetch(fileUrl, { credentials: 'omit', headers });
    if (!response.ok) {
      const detail = await readOptionalDetail(response);
      return { ok: false, status: response.status, detail };
    }
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    return {
      ok: true,
      imageSrc: blobUrl,
      revoke: () => URL.revokeObjectURL(blobUrl),
    };
  } catch {
    return { ok: false, status: 0, detail: undefined };
  }
}

export async function fetchReferenceImageDisplay(
  displayUrl: string,
  fileUrl: string
): Promise<FetchReferenceImageDisplayResult> {
  try {
    const response = await protectedFetch(displayUrl);
    if (!response.ok) {
      const detail = await readOptionalDetail(response);
      return { ok: false, status: response.status, detail };
    }
    let data: {
      image_url?: unknown;
      requires_authenticated_fetch?: unknown;
      display_strategy?: unknown;
    };
    try {
      data = (await response.json()) as typeof data;
    } catch {
      return { ok: false, status: 502, detail: i18n.t('errors.invalid_image_display_url') };
    }
    const imageUrl =
      typeof data.image_url === 'string' && data.image_url.trim() !== ''
        ? data.image_url.trim()
        : null;
    const needFetch = data.requires_authenticated_fetch === true;
    if (imageUrl) {
      return { ok: true, imageSrc: imageUrl };
    }
    if (needFetch) {
      return fetchAuthorizedFileAsBlob(fileUrl);
    }
    return { ok: false, status: 502, detail: i18n.t('errors.invalid_image_display_url') };
  } catch {
    return { ok: false, status: 0, detail: undefined };
  }
}
