import { describe, it, expect } from 'vitest';
import {
  getResultNavigationContext,
  uniqueOrderedIds,
} from '../src/features/results/utils/navigationContext';

describe('uniqueOrderedIds', () => {
  it('dedupes shared sourcePositionId while preserving order', () => {
    expect(uniqueOrderedIds(['posA', 'posA', 'posB', 'posA', 'posC'])).toEqual([
      'posA',
      'posB',
      'posC',
    ]);
  });
});

describe('getResultNavigationContext multi-product photo', () => {
  it('skips duplicate adjacent ids so Next advances to the next distinct position', () => {
    const ids = ['posA', 'posA', 'posB'];
    const ctx = getResultNavigationContext(ids, 'posA');
    expect(ctx).not.toBeNull();
    expect(ctx!.nextId).toBe('posB');
    expect(ctx!.previousId).toBeNull();
  });

  it('skips duplicate adjacent ids for Previous', () => {
    const ids = ['posA', 'posB', 'posB'];
    const ctx = getResultNavigationContext(ids, 'posB');
    expect(ctx!.previousId).toBe('posA');
    expect(ctx!.nextId).toBeNull();
  });
});
