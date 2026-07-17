import { EMPTY_CURSOR } from '../src/core/compositeCursor';
import {
  collectNewSinceFloor,
  filterNewestFirstPage,
  simulateIncrementalScanCost,
} from '../src/core/incrementalScan';

describe('incremental newest-first scan', () => {
  it('stops when reaching the scan cursor region', () => {
    const scanCursor = { dateAdded: 100, assetId: '100' };
    // Newest first: 120, 110, 100, 90
    const page = [
      { assetId: '120', dateAdded: 120 },
      { assetId: '110', dateAdded: 110 },
      { assetId: '100', dateAdded: 100 },
      { assetId: '90', dateAdded: 90 },
    ];
    const res = filterNewestFirstPage(page, scanCursor);
    expect(res.newCandidates.map((c) => c.assetId)).toEqual(['120', '110']);
    expect(res.reachedCursor).toBe(true);
    expect(res.examined).toBe(3); // stops at the cursor row
  });

  it('does not hydrate 10k historical photos when only 20 are new', () => {
    const historical = 10_000;
    const neu = 20;
    const pageSize = 50;
    const newestFirst = [
      ...Array.from({ length: neu }, (_, i) => ({
        assetId: `n${i}`,
        dateAdded: 10_000 + i,
      })).reverse(),
      ...Array.from({ length: historical }, (_, i) => ({
        assetId: `h${i}`,
        dateAdded: i,
      })).reverse(),
    ];
    const cursor = { dateAdded: 9999, assetId: 'h9999' };
    const cost = simulateIncrementalScanCost({
      pageSize,
      scanCursor: cursor,
      newestFirstIds: newestFirst,
    });
    expect(cost.hydrated).toBe(neu);
    expect(cost.hydrated).toBeLessThan(100);
    expect(cost.examined).toBeLessThan(neu + pageSize + 5);
  });

  it('empty cursor hydrates only what is walked until end of new region', () => {
    const page = [
      { assetId: '2', dateAdded: 2 },
      { assetId: '1', dateAdded: 1 },
    ];
    const res = filterNewestFirstPage(page, EMPTY_CURSOR);
    expect(res.newCandidates).toHaveLength(2);
    expect(res.reachedCursor).toBe(false);
  });
});

describe('collectNewSinceFloor (batch/same-second robustness)', () => {
  const floor = { dateAdded: 1000, assetId: '100' };

  it('collects every photo of a same-second batch even in arbitrary tie order', () => {
    // 8 drone photos downloaded at once → all share DATE_ADDED second 2000.
    // MediaStore returns the tied rows in an order that does NOT match assetId order,
    // AND places the floor row (assetId 100) among them. The old early-stop would cut here.
    const page = [
      { assetId: '105', dateAdded: 2000 },
      { assetId: '108', dateAdded: 2000 },
      { assetId: '101', dateAdded: 2000 },
      { assetId: '107', dateAdded: 2000 },
      { assetId: '100', dateAdded: 1000 }, // floor row appears mid-page (same second as floor)
      { assetId: '103', dateAdded: 2000 },
      { assetId: '106', dateAdded: 2000 },
      { assetId: '102', dateAdded: 2000 },
      { assetId: '104', dateAdded: 2000 },
      { assetId: '99', dateAdded: 999 }, // strictly older second → stop after this
    ];
    const res = collectNewSinceFloor(page, floor);
    expect(res.newCandidates.map((c) => c.assetId).sort()).toEqual([
      '101', '102', '103', '104', '105', '106', '107', '108',
    ]);
    expect(res.reachedFloor).toBe(true);
  });

  it('does not skip photos indexed out of assetId order within the floor second', () => {
    // A genuinely-new photo with a LOWER assetId than an already-inspected one, same second.
    const page = [
      { assetId: '110', dateAdded: 1000 }, // already inspected in a previous scan
      { assetId: '105', dateAdded: 1000 }, // new, lower id, same second as floor
      { assetId: '100', dateAdded: 1000 }, // the floor itself
      { assetId: '90', dateAdded: 900 },
    ];
    const res = collectNewSinceFloor(page, floor, new Set(['110']));
    expect(res.newCandidates.map((c) => c.assetId)).toEqual(['105']);
    expect(res.reachedFloor).toBe(true);
  });

  it('skips already-inspected ids but keeps scanning for new siblings', () => {
    const page = [
      { assetId: '104', dateAdded: 2000 },
      { assetId: '103', dateAdded: 2000 },
      { assetId: '102', dateAdded: 2000 },
      { assetId: '101', dateAdded: 2000 },
    ];
    const res = collectNewSinceFloor(page, floor, new Set(['103', '101']));
    expect(res.newCandidates.map((c) => c.assetId)).toEqual(['104', '102']);
    expect(res.reachedFloor).toBe(false);
  });

  it('stops only on a strictly-older second, not on same-second ties', () => {
    const page = [
      { assetId: '101', dateAdded: 1000 }, // same second as floor, after floor id
      { assetId: '100', dateAdded: 1000 }, // equal to floor → not older, keep going
      { assetId: '50', dateAdded: 500 }, // strictly older → stop
      { assetId: '200', dateAdded: 3000 }, // never reached
    ];
    const res = collectNewSinceFloor(page, floor);
    expect(res.newCandidates.map((c) => c.assetId)).toEqual(['101']);
    expect(res.reachedFloor).toBe(true);
    expect(res.examined).toBe(3);
  });
});
