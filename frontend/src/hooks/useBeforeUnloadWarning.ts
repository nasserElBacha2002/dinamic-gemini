import { useEffect } from 'react';

/**
 * Registers a `beforeunload` handler while `enabled` is true so the browser warns
 * before refresh or tab close during long-running uploads.
 */
export function useBeforeUnloadWarning(enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return;

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };

    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [enabled]);
}
