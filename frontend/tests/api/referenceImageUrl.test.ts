/**
 * HEIC preview regression fix — reference image URL includes job_id when available.
 * Ensures the frontend builds the URL that backend needs to resolve normalized preview from the correct job.
 *
 * jobId is derived in ResultEvidencePanel from result.technicalMetadata.entityId (backend contract:
 * detail `technical_snapshot.entity_uid`, format "<job_id>_<entity_suffix>", e.g. "uuid_E1").
 */

import { describe, it, expect } from 'vitest';
import { getReferenceImageDisplayUrl, getReferenceImageFileUrl } from '../../src/api/client';

describe('getReferenceImageFileUrl', () => {
  it('includes job_id query param when jobId is provided', () => {
    const url = getReferenceImageFileUrl('inv-1', 'aisle-1', 'asset-uuid', 'job-uuid-123');
    expect(url).toContain('job_id=');
    expect(url).toContain(encodeURIComponent('job-uuid-123'));
    expect(url).toMatch(/\?job_id=job-uuid-123/);
  });

  it('does not include job_id when jobId is omitted', () => {
    const url = getReferenceImageFileUrl('inv-1', 'aisle-1', 'asset-uuid');
    expect(url).not.toContain('job_id=');
    expect(url).toContain('/file');
  });

  it('does not include job_id when jobId is null or empty', () => {
    expect(getReferenceImageFileUrl('inv-1', 'aisle-1', 'asset-uuid', null)).not.toContain('job_id=');
    expect(getReferenceImageFileUrl('inv-1', 'aisle-1', 'asset-uuid', '')).not.toContain('job_id=');
  });

  it('encodes jobId in URL when provided (entity_uid-derived value)', () => {
    const jobIdFromEntityUid = '1d4bff03-7a84-493d-ab5c-57f6f12ee5c1';
    const url = getReferenceImageFileUrl('inv', 'aisle', 'asset-id', jobIdFromEntityUid);
    expect(url).toContain('job_id=');
    expect(url).toContain(jobIdFromEntityUid);
  });
});

describe('getReferenceImageDisplayUrl', () => {
  it('uses image-display-url path and job_id like getReferenceImageFileUrl', () => {
    const url = getReferenceImageDisplayUrl('inv-1', 'aisle-1', 'asset-uuid', 'job-uuid-123');
    expect(url).toContain('/image-display-url');
    expect(url).toContain('job_id=');
    expect(url).toContain('job-uuid-123');
  });

  it('omits job_id when not provided', () => {
    const url = getReferenceImageDisplayUrl('inv-1', 'aisle-1', 'asset-uuid');
    expect(url).toContain('/image-display-url');
    expect(url).not.toContain('job_id=');
  });
});
