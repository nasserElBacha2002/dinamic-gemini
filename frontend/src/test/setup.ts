import '@testing-library/jest-dom/vitest';
import { i18nInit } from '../i18n';

await i18nInit;

// jsdom doesn't implement createObjectURL/revokeObjectURL; used for local file previews.
if (!('createObjectURL' in URL)) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (URL as any).createObjectURL = () => 'blob:test-mock-url';
}
if (!('revokeObjectURL' in URL)) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (URL as any).revokeObjectURL = () => {};
}
