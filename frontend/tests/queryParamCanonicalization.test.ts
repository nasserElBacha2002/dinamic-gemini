import { describe, expect, it } from 'vitest';
import {
  canonicalizeAislePositionsListQuery,
  canonicalizeInventoriesListQuery,
  canonicalizeOptionalId,
  canonicalizeReviewQueueListQuery,
  inventoriesListKeyPart,
  normalizePositiveInt,
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

describe('normalizePositiveInt (integer policy)', () => {
  it('truncates toward zero and rejects invalid', () => {
    expect(normalizePositiveInt(1.9)).toBe(1);
    expect(normalizePositiveInt(10.2)).toBe(10);
    expect(normalizePositiveInt(NaN)).toBeUndefined();
    expect(normalizePositiveInt(Infinity)).toBeUndefined();
    expect(normalizePositiveInt(-1)).toBeUndefined();
    expect(normalizePositiveInt(0)).toBeUndefined();
  });
});

describe('review queue key/request parity', () => {
  it('uses same canonical object for key as for implied wire identity', () => {
    const raw: Parameters<typeof canonicalizeReviewQueueListQuery>[0] = {
      inventory_id: '  inv-1 ',
      page: 1.9,
      page_size: 10.7,
      min_confidence: Number.POSITIVE_INFINITY,
    };
    const canonical = canonicalizeReviewQueueListQuery(raw);
    expect(canonical.page).toBe(1);
    expect(canonical.page_size).toBe(10);
    expect(canonical.min_confidence).toBeUndefined();
    expect(reviewQueueListKeyPart(raw)).toEqual(reviewQueueListKeyPart(canonical));
  });

  it('idempotent: canonicalizing twice matches once', () => {
    const once = canonicalizeReviewQueueListQuery({
      inventory_id: 'x',
      page: 2,
      has_evidence: true,
    });
    expect(canonicalizeReviewQueueListQuery(once)).toEqual(once);
  });
});

describe('aisle positions key/request parity', () => {
  it('aligns key with canonical payload for pagination edge values', () => {
    const raw = { page: 1.9, page_size: 10.2, job_id: '  run-1 ' };
    const canonical = canonicalizeAislePositionsListQuery(raw);
    expect(canonical.page).toBe(1);
    expect(canonical.page_size).toBe(10);
    expect(canonical.job_id).toBe('run-1');
    expect(positionsListKeyPart(raw)).toEqual(positionsListKeyPart(canonical));
  });

  it('does not collapse distinct min_confidence values', () => {
    const a = positionsListKeyPart({ min_confidence: 0.5 });
    const b = positionsListKeyPart({ min_confidence: 0.6 });
    expect(a).not.toEqual(b);
  });

  it('omits non-finite confidence from canonical and key', () => {
    const c = canonicalizeAislePositionsListQuery({ min_confidence: NaN });
    expect(c.min_confidence).toBeUndefined();
    expect(positionsListKeyPart({ min_confidence: NaN }).min_confidence).toBeUndefined();
  });
});

describe('inventories list integer parity with key', () => {
  it('maps fractional page to truncated integer in canonical and key', () => {
    const q = canonicalizeInventoriesListQuery({ page: 2.4, page_size: 25.9 });
    expect(q.page).toBe(2);
    expect(q.page_size).toBe(25);
    expect(inventoriesListKeyPart({ page: 2.4, page_size: 25.9 })).toEqual(inventoriesListKeyPart(q));
  });
});
