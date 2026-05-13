import { describe, it, expect } from 'vitest';
import { parseResultDetailNavigationState } from '../src/features/results/utils/navigationContext';

describe('parseResultDetailNavigationState returnTo', () => {
  it('maps legacy review_queue returnTo to aisle_results', () => {
    const s = parseResultDetailNavigationState({
      resultIds: ['a', 'b'],
      returnTo: 'review_queue',
    });
    expect(s?.returnTo).toBe('aisle_results');
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
