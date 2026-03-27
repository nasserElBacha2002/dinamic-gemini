import { describe, it, expect } from 'vitest';
import { parseResultDetailNavigationState } from '../src/features/results/utils/navigationContext';

describe('parseResultDetailNavigationState returnTo', () => {
  it('parses review_queue', () => {
    const s = parseResultDetailNavigationState({
      resultIds: ['a', 'b'],
      returnTo: 'review_queue',
    });
    expect(s?.returnTo).toBe('review_queue');
  });

  it('parses aisle_results', () => {
    const s = parseResultDetailNavigationState({
      resultIds: ['a'],
      returnTo: 'aisle_results',
    });
    expect(s?.returnTo).toBe('aisle_results');
  });

  it('drops invalid returnTo', () => {
    const s = parseResultDetailNavigationState({
      resultIds: ['a'],
      returnTo: 'nope',
    });
    expect(s?.returnTo).toBeUndefined();
  });
});
