import { describe, expect, it } from 'vitest';
import { ApiError } from '../../../src/api/types/errors';
import { isApiNotPreparedError, isPublisherActivePresence } from '../../../src/features/liveStream/liveStreamPresence';

describe('liveStreamPresence', () => {
  it('detects active publisher presence', () => {
    expect(isPublisherActivePresence('live')).toBe(true);
    expect(isPublisherActivePresence('connecting')).toBe(true);
    expect(isPublisherActivePresence('no_stream')).toBe(false);
  });

  it('detects not prepared API error', () => {
    const err = new ApiError('conflict', 409, { code: 'LIVE_STREAM_NOT_PREPARED' });
    expect(isApiNotPreparedError(err)).toBe(true);
    expect(isApiNotPreparedError(new ApiError('other', 404))).toBe(false);
  });
});