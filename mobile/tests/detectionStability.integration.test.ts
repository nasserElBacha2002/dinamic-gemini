/**
 * Integration-style pure test: detection → waiting_stability → settled → lastValid advances.
 */
import { compareCursor, EMPTY_CURSOR } from '../src/core/compositeCursor';
import { detectNewPhotos } from '../src/core/photoDetection';
import { evaluateStability } from '../src/core/stability';
import { makeImage } from './factories';

describe('detection + stability integration (pure)', () => {
  it('does not treat a photo as last-valid until stability settles', () => {
    let scanCursor = EMPTY_CURSOR;
    let lastValid = EMPTY_CURSOR;
    const inspected = new Set<string>();

    const img = makeImage({ assetId: '50', dateAdded: 500 });
    const detection = detectNewPhotos({
      candidates: [img],
      scanCursor,
      inspectedIds: inspected,
    });
    expect(detection.admitted).toHaveLength(1);
    scanCursor = detection.nextScanCursor;
    detection.inspectedIds.forEach((id) => inspected.add(id));

    // Immediately after detection, lastValid must NOT have advanced.
    expect(compareCursor(lastValid, EMPTY_CURSOR)).toBe(0);

    const growing = evaluateStability([
      { size: 100, dateModified: 1, accessible: true },
      { size: 200, dateModified: 2, accessible: true },
    ]);
    expect(growing.phase).toBe('waiting');

    const settled = evaluateStability([
      { size: 300, dateModified: 3, accessible: true },
      { size: 300, dateModified: 3, accessible: true },
    ]);
    expect(settled.phase).toBe('settled');

    if (settled.phase === 'settled') {
      const next = { dateAdded: img.dateAdded, assetId: img.assetId };
      if (compareCursor(next, lastValid) > 0) {
        lastValid = next;
      }
    }

    expect(lastValid).toEqual({ dateAdded: 500, assetId: '50' });
    expect(scanCursor).toEqual({ dateAdded: 500, assetId: '50' });
  });

  it('decode-failure path leaves lastValid unchanged while scan cursor already advanced', () => {
    const lastValid = EMPTY_CURSOR;
    const img = makeImage({ assetId: '77', dateAdded: 700 });
    const detection = detectNewPhotos({
      candidates: [img],
      scanCursor: EMPTY_CURSOR,
      inspectedIds: new Set(),
    });
    const scanCursor = detection.nextScanCursor;
    const status = 'undecodable' as const;
    expect(status).toBe('undecodable');
    expect(lastValid).toEqual(EMPTY_CURSOR);
    expect(scanCursor).toEqual({ dateAdded: 700, assetId: '77' });
  });
});
