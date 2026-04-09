import { describe, it, expect } from 'vitest';
import { rowMatchesSearchQuery } from '../src/utils/tableSearch';

describe('rowMatchesSearchQuery', () => {
  it('matches when query is empty', () => {
    expect(rowMatchesSearchQuery('', ['Hello'])).toBe(true);
    expect(rowMatchesSearchQuery('  ', ['x'])).toBe(true);
  });

  it('matches if any field contains query case-insensitively', () => {
    expect(rowMatchesSearchQuery('foo', ['x', 'FooBar'])).toBe(true);
    expect(rowMatchesSearchQuery('foo', ['x', 'bar'])).toBe(false);
  });

  it('treats nullish parts as empty strings', () => {
    expect(rowMatchesSearchQuery('a', [null, undefined, 'abc'])).toBe(true);
  });
});
