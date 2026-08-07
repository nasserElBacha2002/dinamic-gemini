import { describe, expect, it } from 'vitest';
import { safeInternalPath } from '../../src/utils/safeInternalPath';

describe('safeInternalPath', () => {
  it('allows valid internal routes', () => {
    expect(safeInternalPath('/')).toBe('/');
    expect(safeInternalPath('/inventories')).toBe('/inventories');
    expect(safeInternalPath('/clients/abc?x=1')).toBe('/clients/abc?x=1');
  });

  it('rejects external and protocol-relative URLs', () => {
    expect(safeInternalPath('https://evil.example/x', '/home')).toBe('/home');
    expect(safeInternalPath('http://evil.example/x', '/home')).toBe('/home');
    expect(safeInternalPath('//evil.example/x', '/home')).toBe('/home');
  });

  it('rejects javascript and backslash vectors', () => {
    expect(safeInternalPath('javascript:alert(1)', '/home')).toBe('/home');
    expect(safeInternalPath('/\\evil.example', '/home')).toBe('/home');
    expect(safeInternalPath('\\evil', '/home')).toBe('/home');
  });

  it('rejects non-strings and empty values', () => {
    expect(safeInternalPath(null, '/home')).toBe('/home');
    expect(safeInternalPath('', '/home')).toBe('/home');
    expect(safeInternalPath('   ', '/home')).toBe('/home');
  });
});
