import { describe, expect, it } from 'vitest';
import {
  formatFallbackProgressSummary,
  isFallbackProgressVisible,
} from '../src/features/inventories/utils/fallbackProgressSummary';

describe('fallbackProgressSummary', () => {
  it('formats counters and null cost', () => {
    expect(
      formatFallbackProgressSummary({
        resolved_internal: 14,
        fallback_requested: 6,
        fallback_skipped: 0,
        fallback_in_progress: 0,
        resolved_external: 3,
        external_unrecognized: 2,
        external_failed: 1,
        pending_manual_review: 0,
        estimated_external_cost: null,
      }),
    ).toContain('14 internas');
  });

  it('hides when flag off and no requests', () => {
    expect(
      isFallbackProgressVisible(
        {
          resolved_internal: 1,
          fallback_requested: 0,
          fallback_skipped: 1,
          fallback_in_progress: 0,
          resolved_external: 0,
          external_unrecognized: 0,
          external_failed: 0,
          pending_manual_review: 0,
          estimated_external_cost: null,
        },
        false,
      ),
    ).toBe(false);
  });

  it('shows when requests occurred', () => {
    expect(
      isFallbackProgressVisible(
        {
          resolved_internal: 0,
          fallback_requested: 2,
          fallback_skipped: 0,
          fallback_in_progress: 0,
          resolved_external: 1,
          external_unrecognized: 0,
          external_failed: 1,
          pending_manual_review: 0,
          estimated_external_cost: 0.01,
        },
        false,
      ),
    ).toBe(true);
  });
});
