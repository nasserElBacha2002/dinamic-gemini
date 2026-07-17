import {
  compareCursor,
  cursorFromMarker,
  cursorOf,
  EMPTY_CURSOR,
  isAfterCursor,
  maxCursor,
} from '../src/core/compositeCursor';
import type { CaptureMarker } from '../src/domain/entities/captureMarker';
import { parseMediaStoreNumericId, requireAssetId } from '../src/domain/entities/galleryImage';
import { makeImage } from './factories';

describe('composite cursor (dateAdded + assetId)', () => {
  it('orders by dateAdded first', () => {
    expect(
      compareCursor({ dateAdded: 10, assetId: '5' }, { dateAdded: 11, assetId: '1' }),
    ).toBeLessThan(0);
  });

  it('breaks ties on assetId lexicographically', () => {
    expect(
      compareCursor({ dateAdded: 10, assetId: '6' }, { dateAdded: 10, assetId: '5' }),
    ).toBeGreaterThan(0);
    expect(
      compareCursor({ dateAdded: 10, assetId: '5' }, { dateAdded: 10, assetId: '5' }),
    ).toBe(0);
  });

  it('treats a same-timestamp photo with a higher assetId as after', () => {
    const cursor = { dateAdded: 1000, assetId: '5' };
    expect(isAfterCursor(makeImage({ dateAdded: 1000, assetId: '6' }), cursor)).toBe(true);
    expect(isAfterCursor(makeImage({ dateAdded: 1000, assetId: '4' }), cursor)).toBe(false);
  });

  it('empty-gallery marker yields EMPTY_CURSOR', () => {
    const marker: CaptureMarker = {
      assetId: null,
      mediaStoreNumericId: null,
      dateAdded: null,
      dateModified: null,
      displayName: null,
      size: null,
      bucketId: null,
      inventoryId: 'inv',
      aisleId: 'a',
    };
    expect(cursorFromMarker(marker)).toEqual(EMPTY_CURSOR);
    expect(isAfterCursor(makeImage({ dateAdded: 0, assetId: '0' }), EMPTY_CURSOR)).toBe(true);
  });

  it('maxCursor returns the greatest of a set', () => {
    const fallback = { dateAdded: 5, assetId: '5' };
    const imgs = [
      makeImage({ dateAdded: 7, assetId: '2' }),
      makeImage({ dateAdded: 7, assetId: '9' }),
    ];
    expect(maxCursor(imgs, fallback)).toEqual({ dateAdded: 7, assetId: '9' });
    expect(cursorOf(imgs[0]!)).toEqual({ dateAdded: 7, assetId: '2' });
  });
});

describe('asset id parsing', () => {
  it('parses numeric ids and rejects non-numeric without falling back to 0', () => {
    expect(parseMediaStoreNumericId('42')).toBe(42);
    expect(parseMediaStoreNumericId('abc')).toBeUndefined();
    expect(parseMediaStoreNumericId('')).toBeUndefined();
    expect(parseMediaStoreNumericId('12.3')).toBeUndefined();
  });

  it('requireAssetId throws on empty', () => {
    expect(() => requireAssetId('')).toThrow(/empty/);
    expect(requireAssetId('  7  ')).toBe('7');
  });
});
