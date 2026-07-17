import { admitImage, isAdmissibleImage } from '../src/core/imageFilter';
import { makeImage, makeVideo } from './factories';

describe('photos-only admission filter', () => {
  it('admits allowed image formats', () => {
    for (const mime of ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif']) {
      const ext = mime === 'image/jpeg' ? '.jpg' : `.${mime.split('/')[1]}`;
      expect(isAdmissibleImage(makeImage({ mimeType: mime, displayName: `x${ext}` }))).toBe(true);
    }
  });

  it('rejects a video by MIME', () => {
    expect(admitImage(makeVideo())).toEqual({ admitted: false, reason: 'video_mime' });
  });

  it('rejects a video by extension even if MIME is missing', () => {
    expect(admitImage(makeImage({ mimeType: '', displayName: 'clip.mov' }))).toEqual({
      admitted: false,
      reason: 'video_extension',
    });
  });

  it('rejects excluded image formats (gif/bmp/tiff/svg)', () => {
    for (const mime of ['image/gif', 'image/bmp', 'image/tiff', 'image/svg+xml']) {
      expect(admitImage(makeImage({ mimeType: mime, displayName: 'x.bin' })).admitted).toBe(false);
    }
  });

  it('rejects octet-stream and missing mime', () => {
    expect(admitImage(makeImage({ mimeType: 'application/octet-stream' })).admitted).toBe(false);
    expect(admitImage(makeImage({ mimeType: '', displayName: 'noext' })).admitted).toBe(false);
  });

  it('rejects zero-byte files', () => {
    expect(admitImage(makeImage({ size: 0 }))).toEqual({ admitted: false, reason: 'empty_size' });
  });

  it('rejects mime/extension mismatch', () => {
    expect(admitImage(makeImage({ mimeType: 'image/png', displayName: 'photo.jpg' })).admitted).toBe(true);
    expect(admitImage(makeImage({ mimeType: 'image/jpeg', displayName: 'photo.gif' }))).toEqual({
      admitted: false,
      reason: 'disallowed_extension',
    });
  });
});
