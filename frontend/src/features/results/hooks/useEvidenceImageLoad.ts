/**
 * Evidence image load state — fetch preflight to distinguish 404, 403, network.
 * Caller revokes blobUrl when done (hook revokes on url change or unmount).
 */

import { useEffect, useRef, useState } from 'react';
import { fetchEvidenceImage } from '../../../api/client';

export type EvidenceImageErrorKind =
  | 'not_found'
  | 'forbidden'
  | 'network'
  | 'heic_preview_unavailable';

export type EvidenceImageLoadState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'loaded'; blobUrl: string }
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

function messageForKind(kind: EvidenceImageErrorKind): string {
  switch (kind) {
    case 'not_found':
      return 'Source image is no longer available.';
    case 'forbidden':
      return 'You do not have permission to load this image.';
    case 'heic_preview_unavailable':
      return 'Preview is not available for this image.';
    case 'network':
    default:
      return 'Image could not be loaded.';
  }
}

/**
 * Load evidence image via fetch (with auth), then expose blob URL or differentiated error.
 * Revokes blob URL on url change or unmount to avoid leaks.
 */
export function useEvidenceImageLoad(imageUrl: string | null): EvidenceImageLoadState {
  const [state, setState] = useState<EvidenceImageLoadState>({ status: 'idle' });
  const blobUrlRef = useRef<string | null>(null);

  useEffect(() => {
    if (!imageUrl || imageUrl.trim() === '') {
      setState({ status: 'idle' });
      blobUrlRef.current = null;
      return;
    }
    let cancelled = false;
    setState({ status: 'loading' });
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current);
      blobUrlRef.current = null;
    }
    fetchEvidenceImage(imageUrl).then((result) => {
      if (cancelled) return;
      if (result.ok) {
        blobUrlRef.current = result.blobUrl;
        setState({ status: 'loaded', blobUrl: result.blobUrl });
      } else {
        const kind = kindFromResponse(result.status, result.detail);
        setState({
          status: 'error',
          kind,
          message: messageForKind(kind),
        });
      }
    });
    return () => {
      cancelled = true;
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
    };
  }, [imageUrl]);

  useEffect(() => {
    return () => {
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
    };
  }, []);

  return state;
}
