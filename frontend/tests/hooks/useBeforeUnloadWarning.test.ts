import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useBeforeUnloadWarning } from '../../src/hooks/useBeforeUnloadWarning';

describe('useBeforeUnloadWarning', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('registers beforeunload while enabled', () => {
    const addSpy = vi.spyOn(window, 'addEventListener');
    const { rerender } = renderHook(({ enabled }) => useBeforeUnloadWarning(enabled), {
      initialProps: { enabled: true },
    });

    expect(addSpy).toHaveBeenCalledWith('beforeunload', expect.any(Function));

    rerender({ enabled: false });
    expect(addSpy).toHaveBeenCalledWith('beforeunload', expect.any(Function));
  });

  it('does not register beforeunload when disabled', () => {
    const addSpy = vi.spyOn(window, 'addEventListener');
    renderHook(() => useBeforeUnloadWarning(false));

    const beforeUnloadCalls = addSpy.mock.calls.filter(([event]) => event === 'beforeunload');
    expect(beforeUnloadCalls).toHaveLength(0);
  });

  it('removes listener on unmount after being enabled', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener');
    const { unmount } = renderHook(() => useBeforeUnloadWarning(true));
    unmount();

    const beforeUnloadRemovals = removeSpy.mock.calls.filter(([event]) => event === 'beforeunload');
    expect(beforeUnloadRemovals.length).toBeGreaterThan(0);
  });
});
