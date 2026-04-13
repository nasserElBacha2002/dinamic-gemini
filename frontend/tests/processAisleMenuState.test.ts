import { describe, expect, it } from 'vitest';
import { computeProcessAisleMenuState } from '../src/features/inventories/adapters';

describe('computeProcessAisleMenuState', () => {
  it('returns i18n keys for disabled reasons instead of translated strings', () => {
    const state = computeProcessAisleMenuState(
      { id: 'a1', status: 'created', assets_count: 0 },
      { aislesDataLoaded: true, aislesLoading: false, processingAisleId: null }
    );
    expect(state.disabled).toBe(true);
    expect(state.disabledReasonKey).toBe('aisle.upload_need_image');
  });

  it('uses distinct keys when aisle list is not ready', () => {
    const loading = computeProcessAisleMenuState(
      { id: 'a1', status: 'created', assets_count: 3 },
      { aislesDataLoaded: false, aislesLoading: true, processingAisleId: null }
    );
    expect(loading.disabledReasonKey).toBe('aisle.upload_error_verify');

    const notLoading = computeProcessAisleMenuState(
      { id: 'a1', status: 'created', assets_count: 3 },
      { aislesDataLoaded: false, aislesLoading: false, processingAisleId: null }
    );
    expect(notLoading.disabledReasonKey).toBe('aisle.upload_error_fallback');
  });
});
