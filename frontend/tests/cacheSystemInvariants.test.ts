import { describe, it, expect } from 'vitest';
import {
  canonicalizeAislePositionsListQuery,
  canonicalizeInventoriesListQuery,
  inventoriesListKeyPart,
  positionsListKeyPart,
} from '../src/api/queryParamCanonicalization';
import { queryKeys } from '../src/api/queryKeys';
import { computeGuardrailNotices } from '../src/dev/cacheMutationGuardrails';

describe('cache system invariants (Phase 9)', () => {
  it('equivalent messy inventories list params produce identical key parts', () => {
    const a = inventoriesListKeyPart(
      canonicalizeInventoriesListQuery({ page: undefined, page_size: undefined, status: ' draft ' })
    );
    const b = inventoriesListKeyPart(
      canonicalizeInventoriesListQuery({ page: 1, page_size: 25, status: 'draft' })
    );
    expect(a).toEqual(b);
  });

  it('positions list key parts match for equivalent aisle list queries', () => {
    const c1 = canonicalizeAislePositionsListQuery({ page: 1, page_size: 500, job_id: '  j1  ' });
    const c2 = canonicalizeAislePositionsListQuery({ page: 1, page_size: 500, job_id: 'j1' });
    expect(positionsListKeyPart(c1)).toEqual(positionsListKeyPart(c2));
  });

  it('merge results query key uses factory shape', () => {
    const k = queryKeys.inventories.mergeResultsForJob('inv', 'aisle', 'job-1');
    expect(k).toContain('merge-results');
    expect(k[0]).toBe('v3');
  });
});

describe('cacheMutationGuardrails (Phase 9)', () => {
  it('flags default review strategy observability row', () => {
    const t = Date.now();
    const notices = computeGuardrailNotices([
      {
        kind: 'review_action_cache',
        at: t,
        strategy: 'default',
        scope: { inventoryId: 'i', aisleId: 'a', positionId: 'p' },
        patchHits: [],
        fallbackInvalidations: [],
        directInvalidations: ['positions'],
      },
    ]);
    expect(notices).toContain('review_action_used_default_strategy');
  });

  it('flags duplicate explicit_refresh for same key within window', () => {
    const t = Date.now();
    const notices = computeGuardrailNotices([
      {
        kind: 'explicit_refresh',
        at: t - 100,
        flow: 'merge_merge_results',
        mechanism: 'fetchQuery',
        keySummary: 'v3 › merge',
      },
      {
        kind: 'explicit_refresh',
        at: t,
        flow: 'merge_merge_results',
        mechanism: 'fetchQuery',
        keySummary: 'v3 › merge',
      },
    ]);
    expect(notices).toContain('duplicate_explicit_refresh_same_key');
  });

  it('flags high invalidation fan-out', () => {
    const t = Date.now();
    const notices = computeGuardrailNotices([
      {
        kind: 'mutation_invalidations',
        at: t,
        flow: 'useStartAisleProcessing',
        labels: ['a', 'b', 'c', 'd', 'e', 'f', 'g'],
      },
    ]);
    expect(notices).toContain('mutation_high_invalidation_fanout');
  });
});
