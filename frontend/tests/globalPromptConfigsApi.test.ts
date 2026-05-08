import { describe, expect, it } from 'vitest';
import {
  globalPromptConfigActivatePath,
  globalPromptConfigByIdPath,
  globalPromptConfigsActivePath,
  globalPromptConfigsPath,
} from '../src/constants/v3ApiPaths';

describe('global prompt config API paths', () => {
  it('globalPromptConfigsPath points to base collection route', () => {
    expect(globalPromptConfigsPath()).toBe('/api/v3/prompt-configs/global');
  });

  it('globalPromptConfigsActivePath ends with /active', () => {
    expect(globalPromptConfigsActivePath()).toMatch(/\/active$/);
  });

  it('globalPromptConfigByIdPath appends config id', () => {
    expect(globalPromptConfigByIdPath('cfg/x')).toContain(`/global/${encodeURIComponent('cfg/x')}`);
  });

  it('globalPromptConfigActivatePath appends /activate', () => {
    expect(globalPromptConfigActivatePath('cfg-1')).toMatch(/\/activate$/);
  });
});
