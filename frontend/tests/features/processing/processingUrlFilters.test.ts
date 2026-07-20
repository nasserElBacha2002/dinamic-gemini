import { describe, expect, it } from 'vitest';
import {
  createDefaultProcessingFilters,
  mergeProcessingFilterPatch,
  parseProcessingFilters,
  writeProcessingFilters,
} from '../../../src/features/processing/utils/processingUrlFilters';

describe('processingUrlFilters', () => {
  it('parses and writes query params', () => {
    const params = new URLSearchParams(
      'tab=procesamiento&status=failed&search=sku-1&page=2&hasWarnings=true&hasFallback=false&assetId=a1'
    );
    const parsed = parseProcessingFilters(params);
    expect(parsed.status).toBe('failed');
    expect(parsed.search).toBe('sku-1');
    expect(parsed.page).toBe(2);
    expect(parsed.hasWarnings).toBe(true);
    expect(parsed.hasFallback).toBe(false);
    expect(parsed.assetId).toBe('a1');

    const written = writeProcessingFilters(new URLSearchParams(), parsed);
    expect(written.get('tab')).toBe('procesamiento');
    expect(written.get('status')).toBe('failed');
    expect(written.get('search')).toBe('sku-1');
    expect(written.get('page')).toBe('2');
    expect(written.get('hasWarnings')).toBe('true');
    expect(written.get('hasFallback')).toBe('false');
    expect(written.get('assetId')).toBe('a1');
  });

  it('resets page when filters change', () => {
    const current = { ...createDefaultProcessingFilters(), page: 4 };
    const next = mergeProcessingFilterPatch(current, { status: 'resolved' });
    expect(next.page).toBe(1);
    expect(next.status).toBe('resolved');
  });

  it('omits default values from URL', () => {
    const written = writeProcessingFilters(new URLSearchParams(), createDefaultProcessingFilters());
    expect(written.get('tab')).toBe('procesamiento');
    expect(written.get('page')).toBeNull();
    expect(written.get('status')).toBeNull();
  });
});
