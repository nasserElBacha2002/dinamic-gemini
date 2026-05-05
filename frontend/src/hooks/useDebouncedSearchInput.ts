import { useEffect, useState } from 'react';

export type DebouncedSearchInput = {
  /** Raw text in the search field (updates on every keystroke). */
  input: string;
  setInput: (next: string) => void;
  /**
   * Value safe to pass to server queries: debounced while typing, but **cleared immediately**
   * when the field is empty so reset/clear does not leave a stale filter in flight.
   */
  applied: string;
};

/**
 * Pattern for **server-side** table search: debounce non-empty input; apply empty string immediately.
 */
export function useDebouncedSearchInput(debounceMs: number, initialInput = ''): DebouncedSearchInput {
  const [input, setInput] = useState(initialInput);
  const [appliedNonEmpty, setAppliedNonEmpty] = useState(() => initialInput.trim());
  const trimmedInput = input.trim();
  const applied = trimmedInput === '' ? '' : debounceMs <= 0 ? trimmedInput : appliedNonEmpty;

  useEffect(() => {
    if (trimmedInput === '' || debounceMs <= 0) return;
    const id = window.setTimeout(() => setAppliedNonEmpty(trimmedInput), debounceMs);
    return () => window.clearTimeout(id);
  }, [trimmedInput, debounceMs]);

  return { input, setInput, applied };
}
