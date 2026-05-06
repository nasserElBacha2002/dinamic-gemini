import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { ApiError } from '../../src/api/types';
import i18n from '../../src/i18n';
import { useErrorSnackbar } from '../../src/components/ui/useErrorSnackbar';

const showSnackbarMock = vi.fn();

vi.mock('../../src/components/ui/useAppSnackbar', () => ({
  useAppSnackbar: () => ({
    showSnackbar: showSnackbarMock,
    closeSnackbar: vi.fn(),
  }),
}));

describe('useErrorSnackbar', () => {
  beforeEach(() => {
    showSnackbarMock.mockReset();
  });

  it('normalizes known ApiError and uses error severity', () => {
    const { result } = renderHook(() => useErrorSnackbar());
    result.current.showErrorSnackbar(
      new ApiError('not found', 404, { code: 'INVENTORY_NOT_FOUND' }),
      'inventory'
    );

    expect(showSnackbarMock).toHaveBeenCalledWith(i18n.t('errors.not_found'), 'error');
  });

  it('normalizes unknown technical Error to contextual fallback', () => {
    const { result } = renderHook(() => useErrorSnackbar());
    result.current.showErrorSnackbar(
      new Error('TypeError: cannot read properties of undefined at file.ts:22'),
      'analytics'
    );

    expect(showSnackbarMock).toHaveBeenCalledWith(i18n.t('errors.load_metrics'), 'error');
    expect(showSnackbarMock).not.toHaveBeenCalledWith(
      expect.stringContaining('TypeError'),
      'error'
    );
  });
});
