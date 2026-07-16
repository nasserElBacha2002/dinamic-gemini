import {
  compareCursor,
  cursorFromMarker,
  cursorOf,
  isAfterCursor,
  maxCursor,
} from '../src/core/compositeCursor';
import type { CaptureMarker } from '../src/domain/entities/captureMarker';
import { makeImage } from './factories';

describe('composite cursor', () => {
  it('orders by dateAdded first', () => {
    expect(compareCursor({ dateAdded: 10, mediaStoreId: 5 }, { dateAdded: 11, mediaStoreId: 1 })).toBeLessThan(0);
  });

  it('breaks ties on mediaStoreId', () => {
    expect(compareCursor({ dateAdded: 10, mediaStoreId: 6 }, { dateAdded: 10, mediaStoreId: 5 })).toBeGreaterThan(0);
    expect(compareCursor({ dateAdded: 10, mediaStoreId: 5 }, { dateAdded: 10, mediaStoreId: 5 })).toBe(0);
  });

  it('treats a same-timestamp photo with a higher id as "after"', () => {
    const cursor = { dateAdded: 1000, mediaStoreId: 5 };
    const sameSecondNewer = makeImage({ dateAdded: 1000, mediaStoreId: 6 });
    const sameSecondOlder = makeImage({ dateAdded: 1000, mediaStoreId: 4 });
    expect(isAfterCursor(sameSecondNewer, cursor)).toBe(true);
    expect(isAfterCursor(sameSecondOlder, cursor)).toBe(false);
  });

  it('empty-gallery marker yields the lowest cursor so all later photos qualify', () => {
    const marker: CaptureMarker = {
      mediaStoreId: null,
      dateAdded: null,
      dateModified: null,
      displayName: null,
      size: null,
      bucketId: null,
      inventoryId: 'inv',
      aisleId: 'a',
    };
    const cursor = cursorFromMarker(marker);
    expect(cursor).toEqual({ dateAdded: -1, mediaStoreId: -1 });
    expect(isAfterCursor(makeImage({ dateAdded: 0, mediaStoreId: 0 }), cursor)).toBe(true);
  });

  it('maxCursor returns the greatest of a set, else the fallback', () => {
    const fallback = { dateAdded: 5, mediaStoreId: 5 };
    const imgs = [makeImage({ dateAdded: 7, mediaStoreId: 2 }), makeImage({ dateAdded: 7, mediaStoreId: 9 })];
    expect(maxCursor(imgs, fallback)).toEqual({ dateAdded: 7, mediaStoreId: 9 });
    expect(maxCursor([], fallback)).toEqual(fallback);
    expect(cursorOf(imgs[0]!)).toEqual({ dateAdded: 7, mediaStoreId: 2 });
  });
});
