import { createScanCoordinator } from '../src/core/scanCoordinator';
import { mergeUniqueByAssetId } from '../src/core/dedupe';
import { makeImage } from './factories';

describe('scan coordinator serialization', () => {
  it('runs a single pass when events arrive while a scan is in progress', async () => {
    let active = 0;
    let maxActive = 0;
    const runs: number[] = [];

    const coordinator = createScanCoordinator(async () => {
      active += 1;
      maxActive = Math.max(maxActive, active);
      runs.push(Date.now());
      await new Promise((r) => setTimeout(r, 30));
      active -= 1;
    });

    const p1 = coordinator.request();
    const p2 = coordinator.request();
    const p3 = coordinator.request();
    await Promise.all([p1, p2, p3]);

    expect(maxActive).toBe(1);
    // First run + one coalesced follow-up (not three parallel runs).
    expect(coordinator.runCount).toBeGreaterThanOrEqual(2);
    expect(coordinator.runCount).toBeLessThanOrEqual(3);
  });

  it('five consecutive events still never overlap', async () => {
    let active = 0;
    let maxActive = 0;
    const coordinator = createScanCoordinator(async () => {
      active += 1;
      maxActive = Math.max(maxActive, active);
      await new Promise((r) => setTimeout(r, 10));
      active -= 1;
    });
    await Promise.all(Array.from({ length: 5 }, () => coordinator.request()));
    expect(maxActive).toBe(1);
  });
});

describe('dedupe merge', () => {
  it('keeps a photo only once when concurrent scans return the same asset', () => {
    const a = makeImage({ assetId: '42', displayName: 'a.jpg' });
    const b = makeImage({ assetId: '42', displayName: 'a-dup.jpg' });
    const c = makeImage({ assetId: '43', displayName: 'b.jpg' });
    const merged = mergeUniqueByAssetId(
      [{ assetId: a.assetId, image: a, status: 'waiting_stability' as const }],
      [
        { assetId: b.assetId, image: b, status: 'waiting_stability' as const },
        { assetId: c.assetId, image: c, status: 'waiting_stability' as const },
      ],
    );
    expect(merged.map((p) => p.assetId)).toEqual(['42', '43']);
  });
});
