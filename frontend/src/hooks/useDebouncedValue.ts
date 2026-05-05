import { useEffect, useState } from 'react';

/**
 * Returns `value` delayed by `delayMs`. Latest value wins; timers are cleared on change/unmount.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  const immediate = delayMs <= 0;

  useEffect(() => {
    if (immediate) return;
    const id = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(id);
  }, [value, delayMs, immediate]);

  return immediate ? value : debounced;
}
