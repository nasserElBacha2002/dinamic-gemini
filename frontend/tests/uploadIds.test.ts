import { describe, expect, it, vi } from 'vitest';
import { newUploadUuid } from '../src/features/uploads/uploadIds';

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

describe('newUploadUuid', () => {
  it('returns crypto.randomUUID when available', () => {
    const spy = vi.spyOn(crypto, 'randomUUID').mockReturnValue(
      'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
    );
    expect(newUploadUuid()).toBe('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee');
    spy.mockRestore();
  });

  it('fallback without randomUUID is still UUID-shaped', () => {
    const spy = vi.spyOn(crypto, 'randomUUID').mockImplementation(() => {
      throw new Error('unavailable');
    });
    // Force fallback path by making randomUUID undefined-like via delete + redefine
    spy.mockRestore();
    const original = crypto.randomUUID;
    Object.defineProperty(crypto, 'randomUUID', {
      configurable: true,
      value: undefined,
    });
    try {
      const id = newUploadUuid();
      expect(id).toMatch(UUID_RE);
    } finally {
      Object.defineProperty(crypto, 'randomUUID', {
        configurable: true,
        value: original,
      });
    }
  });
});
