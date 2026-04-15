import { describe, expect, it } from 'vitest';
import {
  canonicalizeInventoriesListQuery,
  canonicalizeOptionalId,
  inventoriesListKeyPart,
  positionsListKeyPart,
  reviewQueueListKeyPart,
} from '../src/api/queryParamCanonicalization';

describe('queryParamCanonicalization', () => {
  it('canonicalizes inventories list defaults and trims equivalent text values', () => {
    const a = canonicalizeInventoriesListQuery({
      page: 1,
      page_size: 25,
      search: '  abc  ',
      status: '',
      sort_by: ' created_at ',
      sort_dir: ' desc ',
    });
    const b = canonicalizeInventoriesListQuery({
      page: 1,
      page_size: 25,
      search: 'abc',
      status: null,
      sort_by: 'created_at',
      sort_dir: 'desc',
    });
    expect(inventoriesListKeyPart(a)).toEqual(inventoriesListKeyPart(b));
  });

  it('canonicalizes review queue key for empty/null equivalents', () => {
    const a = reviewQueueListKeyPart({
      inventory_id: ' inv-1 ',
      aisle_id: '',
      traceability: '  UNKNOWN ',
      position_status: '  REVIEWED ',
      has_evidence: false,
      qty_zero: true,
      page: 1,
      page_size: 50,
    });
    const b = reviewQueueListKeyPart({
      inventory_id: 'inv-1',
      aisle_id: null,
      traceability: 'unknown',
      position_status: 'reviewed',
      has_evidence: false,
      qty_zero: true,
      page: 1,
      page_size: 50,
    });
    expect(a).toEqual(b);
  });

  it('keeps positions job slice distinct from explicit job ids', () => {
    const resolverDefault = positionsListKeyPart({ page: 1, page_size: 10, job_id: '   ' });
    const explicit = positionsListKeyPart({ page: 1, page_size: 10, job_id: 'job-1' });
    expect(resolverDefault.job_slice).toBe('resolver_default');
    expect(explicit.job_id).toBe('job-1');
    expect(resolverDefault).not.toEqual(explicit);
  });

  it('canonicalizes optional ids with trim and null collapse', () => {
    expect(canonicalizeOptionalId('  job-a  ')).toBe('job-a');
    expect(canonicalizeOptionalId('')).toBeNull();
    expect(canonicalizeOptionalId('   ')).toBeNull();
    expect(canonicalizeOptionalId(null)).toBeNull();
    expect(canonicalizeOptionalId(undefined)).toBeNull();
  });
});
