import { detectNewPhotos } from '../src/core/photoDetection';
import { makeImage, makeVideo } from './factories';

const EMPTY_CURSOR = { dateAdded: -1, mediaStoreId: -1 };

describe('new-photo detection', () => {
  it('returns only photos after the cursor, sorted ascending', () => {
    const cursor = { dateAdded: 100, mediaStoreId: 10 };
    const candidates = [
      makeImage({ mediaStoreId: 9, dateAdded: 100 }), // same ts, older id -> not new
      makeImage({ mediaStoreId: 11, dateAdded: 100 }), // same ts, newer id -> new
      makeImage({ mediaStoreId: 12, dateAdded: 101 }), // later ts -> new
      makeImage({ mediaStoreId: 8, dateAdded: 50 }), // older -> not new
    ];
    const res = detectNewPhotos({ candidates, cursor, seenIds: new Set() });
    expect(res.newPhotos.map((p) => p.mediaStoreId)).toEqual([11, 12]);
    expect(res.nextCursor).toEqual({ dateAdded: 101, mediaStoreId: 12 });
    expect(res.seenAdditions).toEqual([11, 12]);
  });

  it('is idempotent via the seen-set even when the cursor has not advanced', () => {
    const cursor = EMPTY_CURSOR;
    const candidates = [makeImage({ mediaStoreId: 1, dateAdded: 100 })];
    const first = detectNewPhotos({ candidates, cursor, seenIds: new Set() });
    expect(first.newPhotos).toHaveLength(1);
    const second = detectNewPhotos({
      candidates,
      cursor, // deliberately NOT advanced
      seenIds: new Set(first.seenAdditions),
    });
    expect(second.newPhotos).toHaveLength(0);
  });

  it('detects 20 new drone photos in one pass', () => {
    const candidates = Array.from({ length: 20 }, (_, i) =>
      makeImage({ mediaStoreId: 100 + i, dateAdded: 200 + i, displayName: `DJI_${i}.jpg` }),
    );
    const res = detectNewPhotos({ candidates, cursor: EMPTY_CURSOR, seenIds: new Set() });
    expect(res.newPhotos).toHaveLength(20);
    expect(res.rejected).toHaveLength(0);
  });

  describe('MANDATORY negative test: a video appears during capture', () => {
    it('a new .mp4 is ignored, creates no queue entry, and does not move the cursor', () => {
      const cursor = { dateAdded: 100, mediaStoreId: 10 };
      const newPhoto = makeImage({ mediaStoreId: 11, dateAdded: 101, displayName: 'DJI_A.jpg' });
      const newVideo = makeVideo({ mediaStoreId: 12, dateAdded: 102, displayName: 'DJI_B.mp4' });

      const res = detectNewPhotos({
        candidates: [newPhoto, newVideo],
        cursor,
        seenIds: new Set(),
      });

      // Video is absent from detected photos.
      expect(res.newPhotos.map((p) => p.mediaStoreId)).toEqual([11]);
      // Video is recorded only as rejected (for metrics/logging), never queued.
      expect(res.rejected).toEqual([{ mediaStoreId: 12, reason: 'video_mime' }]);
      // Video (id=12, later ts) did NOT advance the marker; only the photo (id=11) did.
      expect(res.nextCursor).toEqual({ dateAdded: 101, mediaStoreId: 11 });
      // Video is not added to the seen-set.
      expect(res.seenAdditions).toEqual([11]);
    });

    it('a video-only change produces zero detections and an unchanged cursor', () => {
      const cursor = { dateAdded: 100, mediaStoreId: 10 };
      const res = detectNewPhotos({
        candidates: [makeVideo({ mediaStoreId: 20, dateAdded: 500 })],
        cursor,
        seenIds: new Set(),
      });
      expect(res.newPhotos).toHaveLength(0);
      expect(res.seenAdditions).toHaveLength(0);
      expect(res.nextCursor).toEqual(cursor);
    });
  });
});
