import { EMPTY_CURSOR } from '../src/core/compositeCursor';
import {
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
