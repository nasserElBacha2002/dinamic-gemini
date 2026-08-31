import { describe, expect, it } from 'vitest';
import {
  defaultExtractionProfileConfiguration,
  BASIC_CHARSET_OPTIONS,
} from '../src/features/clients/utils/defaultExtractionProfileConfiguration';

describe('defaultExtractionProfileConfiguration (MINIMAL)', () => {
  it('ITEM defaults are identity-only', () => {
    const cfg = defaultExtractionProfileConfiguration('ITEM');
    expect(cfg.recognition_mode).toBe('MINIMAL');
    expect(cfg.required_fields).toEqual(['label_id']);
    expect(cfg.quantity_rules.required).toBe(false);
    expect(cfg.quantity_rules.expected_presence).toBe('OPTIONAL');
    expect(cfg.internal_code_sources).toEqual([]);
    expect(cfg.deterministic?.field_mappings[0]?.target).toBe('label_id');
    expect(cfg.deterministic?.payload_structure).toBe('SIMPLE');
  });

  it('POSITION defaults are identity-only with hyphen charset', () => {
    const cfg = defaultExtractionProfileConfiguration('POSITION');
    expect(cfg.recognition_mode).toBe('MINIMAL');
    expect(cfg.required_fields).toEqual(['position_id']);
    expect(cfg.deterministic?.field_mappings[0]?.target).toBe('position_id');
    expect(cfg.deterministic?.character_set).toBe('ALPHANUMERIC_WITH_HYPHEN');
  });

  it('exposes simple charset options including hyphen', () => {
    const values = BASIC_CHARSET_OPTIONS.map((o) => o.value);
    expect(values).toContain('ALPHANUMERIC_WITH_HYPHEN');
    expect(values).toContain('NUMERIC');
    expect(values).toContain('ANY');
  });
});
