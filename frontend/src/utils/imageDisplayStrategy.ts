/** How the SPA should load an image for preview (aligns with backend display_strategy). */

export type ImageDisplayStrategy = 'presigned_url' | 'authenticated_file_fetch';

export interface ImageDisplayResolution {
  imageSrc: string;
  revoke?: () => void;
}

export function isExternalSignedStorageUrl(url: string): boolean {
  const trimmed = (url || '').trim();
  if (!trimmed.startsWith('https://')) return false;
  if (trimmed.includes('.storage.googleapis.com/')) return true;
  if (trimmed.startsWith('https://storage.googleapis.com/')) return true;
  if (trimmed.includes('.amazonaws.com/')) return true;
  return false;
}

export function shouldRenderImageDirectly(args: {
  url: string;
  strategy?: string | null;
  requiresAuthenticatedFetch?: boolean;
}): boolean {
  if (args.requiresAuthenticatedFetch === true) return false;
  if (args.strategy === 'presigned_url') return true;
  const url = (args.url || '').trim();
  if (!url) return false;
  return isExternalSignedStorageUrl(url);
}
