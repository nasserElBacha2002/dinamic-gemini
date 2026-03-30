/**
 * Evidence image load state — authenticated fetch resolves to an <img>-safe URL
 * (presigned S3 Location or local blob URL). Caller: use imageSrc on <img>; hook revokes
 * object URLs on url change or unmount.
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
 * Resolve authenticated asset file URL for display: presigned redirect target or blob URL.
 */
export function useEvidenceImageLoad(imageUrl: string | null): EvidenceImageLoadState {
  const [state, setState] = useState<EvidenceImageLoadState>({ status: 'idle' });
  const revokeRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!imageUrl || imageUrl.trim() === '') {
      setState({ status: 'idle' });
      if (revokeRef.current) {
        revokeRef.current();
        revokeRef.current = null;
      }
      return;
    }
    let cancelled = false;
    setState({ status: 'loading' });
    if (revokeRef.current) {
      revokeRef.current();
      revokeRef.current = null;
    }
    fetchEvidenceImage(imageUrl).then((result) => {
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
          message: messageForKind(kind),
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
  }, [imageUrl]);

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
