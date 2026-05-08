import { describe, expect, it } from 'vitest';
import {
  supplierPromptConfigActivatePath,
  supplierPromptConfigByIdPath,
  supplierPromptConfigsActivePath,
  supplierPromptConfigsPath,
} from '../src/constants/v3ApiPaths';

describe('supplier prompt config API paths', () => {
  it('supplierPromptConfigsPath encodes client and supplier ids', () => {
    expect(supplierPromptConfigsPath('c/1', 's 2')).toBe(
      `/api/v3/clients/${encodeURIComponent('c/1')}/suppliers/${encodeURIComponent('s 2')}/prompt-configs`
    );
  });

  it('supplierPromptConfigsActivePath ends with /active', () => {
    expect(supplierPromptConfigsActivePath('a', 'b')).toMatch(/\/active$/);
  });

  it('supplierPromptConfigByIdPath appends config id', () => {
    expect(supplierPromptConfigByIdPath('a', 'b', 'cfg/x')).toContain(
      `/prompt-configs/${encodeURIComponent('cfg/x')}`
    );
  });

  it('supplierPromptConfigActivatePath appends /activate', () => {
    expect(supplierPromptConfigActivatePath('a', 'b', 'cfg-1')).toMatch(/\/activate$/);
  });
});

