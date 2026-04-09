import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDebouncedSearchInput } from '../src/hooks/useDebouncedSearchInput';

describe('useDebouncedSearchInput', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('clears applied immediately when input becomes empty', () => {
    const { result } = renderHook(() => useDebouncedSearchInput(300, ''));
    act(() => {
      result.current.setInput('abc');
    });
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(result.current.applied).toBe('abc');

    act(() => {
      result.current.setInput('');
    });
    expect(result.current.applied).toBe('');
  });

  it('debounces non-empty input', () => {
    const { result } = renderHook(() => useDebouncedSearchInput(200, ''));
    act(() => result.current.setInput('a'));
    expect(result.current.applied).toBe('');
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(result.current.applied).toBe('a');

    act(() => result.current.setInput('ab'));
    expect(result.current.applied).toBe('a');
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(result.current.applied).toBe('ab');
  });
});
