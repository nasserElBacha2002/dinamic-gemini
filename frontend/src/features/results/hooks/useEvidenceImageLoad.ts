/**
 * Evidence image load state — authenticated JSON ``image-display-url`` then presigned URL or blob.
 * Caller: use imageSrc on <img>; hook revokes object URLs on spec change or unmount.
 */

import { useEffect, useRef, useState } from 'react';
import { fetchEvidenceImageDisplay, type EvidenceImageLoadSpec } from '../../../api/client';
import i18n from '../../../i18n';

export type EvidenceImageErrorKind =
  | 'not_found'
  | 'forbidden'
  | 'network'
  | 'heic_preview_unavailable';

export type EvidenceImageLoadState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'loaded'; imageSrc: string }
  | { status: 'error'; kind: EvidenceImageErrorKind; message: string };

function kindFromResponse(status: number, detail?: string): EvidenceImageErrorKind {
  if (status === 403 || status === 401) return 'forbidden';
  if (status === 404) {
    if (typeof detail === 'string' && detail.includes('Preview') && detail.includes('not available')) {
      return 'heic_preview_unavailable';
    }
    return 'not_found';
  }
  return 'network';
}

function messageForKind(kind: EvidenceImageErrorKind, _detail?: string): string {
  switch (kind) {
    case 'not_found':
      return i18n.t('results.evidence_image_load.source_unavailable');
    case 'forbidden':
      return i18n.t('results.evidence_image_load.forbidden');
    case 'heic_preview_unavailable':
      return i18n.t('results.evidence_image_load.preview_unavailable');
    case 'network':
    default:
      return i18n.t('results.evidence_image_load.network_error');
  }
}

/**
 * Resolve reference asset image for display via ``/image-display-url`` + optional ``/file`` blob fetch.
 */
export function useEvidenceImageLoad(spec: EvidenceImageLoadSpec | null): EvidenceImageLoadState {
  const [state, setState] = useState<EvidenceImageLoadState>({ status: 'idle' });
  const revokeRef = useRef<(() => void) | null>(null);

  const inventoryId = spec?.inventoryId ?? '';
  const aisleId = spec?.aisleId ?? '';
  const assetId = spec?.assetId ?? '';
  const jobId = spec?.jobId ?? null;

  useEffect(() => {
    if (!inventoryId.trim() || !aisleId.trim() || !assetId.trim()) {
      queueMicrotask(() => setState({ status: 'idle' }));
      if (revokeRef.current) {
        revokeRef.current();
        revokeRef.current = null;
      }
      return;
    }
    let cancelled = false;
    queueMicrotask(() => setState({ status: 'loading' }));
    if (revokeRef.current) {
      revokeRef.current();
      revokeRef.current = null;
    }
    const payload: EvidenceImageLoadSpec = {
      inventoryId: inventoryId.trim(),
      aisleId: aisleId.trim(),
      assetId: assetId.trim(),
      jobId: jobId != null && String(jobId).trim() !== '' ? String(jobId).trim() : null,
    };
    fetchEvidenceImageDisplay(payload).then((result) => {
      if (cancelled) {
        if (result.ok && result.revoke) result.revoke();
        return;
      }
      if (result.ok) {
        if (result.revoke) {
          revokeRef.current = result.revoke;
        }
        setState({ status: 'loaded', imageSrc: result.imageSrc });
      } else {
        const kind = kindFromResponse(result.status, result.detail);
        setState({
          status: 'error',
          kind,
          message: messageForKind(kind, result.detail),
        });
      }
    });
    return () => {
      cancelled = true;
      if (revokeRef.current) {
        revokeRef.current();
        revokeRef.current = null;
      }
    };
  }, [inventoryId, aisleId, assetId, jobId]);

  useEffect(() => {
    return () => {
      if (revokeRef.current) {
        revokeRef.current();
        revokeRef.current = null;
      }
    };
  }, []);

  return state;
}
