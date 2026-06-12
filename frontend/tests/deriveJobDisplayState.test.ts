import { describe, expect, it } from 'vitest';
import {
  deriveEffectiveJobDisplayState,
  isJobProcessingActive,
  isJobTerminalStatus,
  shouldPollJobDetail,
} from '../src/utils/deriveJobDisplayState';

describe('deriveJobDisplayState', () => {
  it('failed latest job overrides processing display', () => {
    expect(
      deriveEffectiveJobDisplayState({
        status: 'failed',
      })
    ).toBe('failed');
  });

  it('succeeded job with failed finalization does not stay in processing', () => {
    expect(
      deriveEffectiveJobDisplayState({
        status: 'succeeded',
        finalization_status: 'failed',
      })
    ).toBe('completed_with_finalization_warning');
  });

  it('polling stops on failed', () => {
    expect(
      shouldPollJobDetail({ status: 'failed' }, 0)
    ).toBe(false);
  });

  it('polling stops on canceled', () => {
    expect(
      shouldPollJobDetail({ status: 'canceled' }, 0)
    ).toBe(false);
  });

  it('polling stops on succeeded with completed finalization', () => {
    expect(
      shouldPollJobDetail({ status: 'succeeded', finalization_status: 'completed' }, 0)
    ).toBe(false);
  });

  it('processing active only for non-terminal jobs', () => {
    expect(isJobProcessingActive({ status: 'running' })).toBe(true);
    expect(isJobProcessingActive({ status: 'failed' })).toBe(false);
    expect(isJobTerminalStatus('succeeded')).toBe(true);
  });
});
