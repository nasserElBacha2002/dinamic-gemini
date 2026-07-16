import '@testing-library/jest-dom/vitest';
import { i18nInit } from '../i18n';

await i18nInit;

// Default jsdom viewport for MUI `useMediaQuery` / `useAppBreakpoint`: desktop (≥ md).
// Compact-layout tests should mock `useAppBreakpoint` explicitly.
const TEST_VIEWPORT_WIDTH_PX = 1280;
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  configurable: true,
  value: (query: string) => {
    const minMatch = /min-width:\s*(\d+(?:\.\d+)?)(px)?/i.exec(query);
    const maxMatch = /max-width:\s*(\d+(?:\.\d+)?)(px)?/i.exec(query);
    let matches = false;
    if (minMatch) {
      matches = TEST_VIEWPORT_WIDTH_PX >= Number(minMatch[1]);
    } else if (maxMatch) {
      matches = TEST_VIEWPORT_WIDTH_PX <= Number(maxMatch[1]);
    }
    return {
      matches,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    };
  },
});

// jsdom doesn't implement createObjectURL/revokeObjectURL; used for local file previews.
if (!('createObjectURL' in URL)) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (URL as any).createObjectURL = () => 'blob:test-mock-url';
}
if (!('revokeObjectURL' in URL)) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (URL as any).revokeObjectURL = () => {};
}
