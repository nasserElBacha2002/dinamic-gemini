import { describe, expect, it } from 'vitest';
import {
  isExternalSignedStorageUrl,
  shouldRenderImageDirectly,
} from '../src/utils/imageDisplayStrategy';

describe('imageDisplayStrategy', () => {
  it('detects GCS signed URLs', () => {
    expect(
      isExternalSignedStorageUrl(
        'https://storage.googleapis.com/bucket/v3/client_suppliers/x.jpg?X-Goog-Signature=abc'
      )
    ).toBe(true);
  });

  it('presigned_url strategy renders directly without fetch', () => {
    expect(
      shouldRenderImageDirectly({
        url: 'https://storage.googleapis.com/bucket/obj.jpg',
        strategy: 'presigned_url',
        requiresAuthenticatedFetch: false,
      })
    ).toBe(true);
  });

  it('authenticated_fetch strategy does not render directly', () => {
    expect(
      shouldRenderImageDirectly({
        url: 'https://storage.googleapis.com/bucket/obj.jpg',
        strategy: 'authenticated_file_fetch',
        requiresAuthenticatedFetch: true,
      })
    ).toBe(false);
  });

  it('detects S3 signed URLs', () => {
    expect(
      shouldRenderImageDirectly({
        url: 'https://my-bucket.s3.amazonaws.com/v3/uploads/x.jpg',
        strategy: undefined,
        requiresAuthenticatedFetch: false,
      })
    ).toBe(true);
  });
});
