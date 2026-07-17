import { EMPTY_CURSOR } from '../src/core/compositeCursor';
import { detectNewPhotos } from '../src/core/photoDetection';
import { makeImage, makeVideo } from './factories';

describe('new-photo detection with dual cursor semantics', () => {
  it('returns only photos after the scan cursor, sorted ascending', () => {
    const scanCursor = { dateAdded: 100, assetId: '10' };
    const candidates = [
      makeImage({ assetId: '9', dateAdded: 100 }),
      makeImage({ assetId: '11', dateAdded: 100 }),
      makeImage({ assetId: '12', dateAdded: 101 }),
      makeImage({ assetId: '8', dateAdded: 50 }),
    ];
    const res = detectNewPhotos({ candidates, scanCursor, inspectedIds: new Set() });
    expect(res.admitted.map((p) => p.assetId)).toEqual(['11', '12']);
    expect(res.nextScanCursor).toEqual({ dateAdded: 101, assetId: '12' });
    expect(res.inspectedIds).toEqual(['11', '12']);
  });

  it('advances scan cursor for rejects without admitting them', () => {
    const scanCursor = { dateAdded: 100, assetId: '10' };
    const bad = makeImage({
      assetId: '15',
      dateAdded: 105,
      mimeType: 'image/gif',
      displayName: 'x.gif',
    });
    const res = detectNewPhotos({
      candidates: [bad],
      scanCursor,
      inspectedIds: new Set(),
    });
    expect(res.admitted).toHaveLength(0);
    expect(res.rejected).toEqual([{ assetId: '15', reason: 'disallowed_mime' }]);
    expect(res.nextScanCursor).toEqual({ dateAdded: 105, assetId: '15' });
    expect(res.inspectedIds).toEqual(['15']);
  });

  it('does not re-process a previously inspected reject', () => {
    const scanCursor = { dateAdded: 105, assetId: '15' };
    const bad = makeImage({
      assetId: '15',
      dateAdded: 105,
      mimeType: 'image/gif',
      displayName: 'x.gif',
    });
    const res = detectNewPhotos({
      candidates: [bad],
      scanCursor,
      inspectedIds: new Set(['15']),
    });
    expect(res.admitted).toHaveLength(0);
    expect(res.rejected).toHaveLength(0);
    expect(res.nextScanCursor).toEqual(scanCursor);
  });

  it('is idempotent via the inspected set', () => {
    const candidates = [makeImage({ assetId: '1', dateAdded: 100 })];
    const first = detectNewPhotos({
      candidates,
      scanCursor: EMPTY_CURSOR,
      inspectedIds: new Set(),
    });
    expect(first.admitted).toHaveLength(1);
    const second = detectNewPhotos({
      candidates,
      scanCursor: EMPTY_CURSOR,
      inspectedIds: new Set(first.inspectedIds),
    });
    expect(second.admitted).toHaveLength(0);
  });

  it('detects 20 new drone photos in one pass', () => {
    const candidates = Array.from({ length: 20 }, (_, i) =>
      makeImage({
        assetId: String(100 + i),
        dateAdded: 200 + i,
        displayName: `DJI_${i}.jpg`,
      }),
    );
    const res = detectNewPhotos({
      candidates,
      scanCursor: EMPTY_CURSOR,
      inspectedIds: new Set(),
    });
    expect(res.admitted).toHaveLength(20);
    expect(res.rejected).toHaveLength(0);
  });

  describe('defensive core: injected video MIME', () => {
    it('rejects video candidates and advances scan cursor only (not last-valid)', () => {
      const scanCursor = { dateAdded: 100, assetId: '10' };
      const newPhoto = makeImage({ assetId: '11', dateAdded: 101, displayName: 'DJI_A.jpg' });
      const newVideo = makeVideo({ assetId: '12', dateAdded: 102, displayName: 'DJI_B.mp4' });

      const res = detectNewPhotos({
        candidates: [newPhoto, newVideo],
        scanCursor,
        inspectedIds: new Set(),
      });

      expect(res.admitted.map((p) => p.assetId)).toEqual(['11']);
      expect(res.rejected).toEqual([{ assetId: '12', reason: 'video_mime' }]);
      // Scan cursor advances past BOTH inspected rows (photo + reject).
      expect(res.nextScanCursor).toEqual({ dateAdded: 102, assetId: '12' });
      expect(res.inspectedIds).toEqual(['11', '12']);
    });
  });

  describe('native query expectation (documentation test)', () => {
    it('videos never appear when candidates come only from Images collection', () => {
      // Simulates MediaStore.Images-only query: empty video side-effect.
      const scanCursor = { dateAdded: 100, assetId: '10' };
      const res = detectNewPhotos({
        candidates: [makeImage({ assetId: '11', dateAdded: 101 })],
        scanCursor,
        inspectedIds: new Set(),
      });
      expect(res.rejected).toHaveLength(0);
      expect(res.admitted).toHaveLength(1);
      // A .mp4 that never entered candidates cannot move metrics.
      expect(res.admitted.every((p) => !p.mimeType.startsWith('video/'))).toBe(true);
    });
  });
});
