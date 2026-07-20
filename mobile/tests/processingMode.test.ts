import {
  INHERITED_IDENTIFICATION_MODE,
  PROCESS_AISLE_IDENTIFICATION_OPTIONS,
  buildProcessAisleRequestBody,
  isLegacyIdentificationMode,
  isSupportedIdentificationMode,
  labelForIdentificationMode,
  mapProcessStartErrorMessage,
  preferenceFromSelection,
  sanitizeIdentificationModeSelection,
  selectionFromPreference,
} from '../src/features/processing/processingMode';

describe('processingMode', () => {
  it('excludes legacy from selectable options', () => {
    const values = PROCESS_AISLE_IDENTIFICATION_OPTIONS.map((o) => o.value);
    expect(values).toContain('CODE_SCAN');
    expect(values).toContain('INTERNAL_OCR');
    expect(values).toContain(INHERITED_IDENTIFICATION_MODE);
    expect(values).not.toContain('LEGACY_LLM');
    expect(values).not.toContain('LEGACY_LLM_TEMPORARY');
  });

  it('sanitizes unknown and legacy to inherit (null)', () => {
    expect(sanitizeIdentificationModeSelection('LEGACY_LLM')).toBeNull();
    expect(sanitizeIdentificationModeSelection('LEGACY_LLM_TEMPORARY')).toBeNull();
    expect(sanitizeIdentificationModeSelection('FUTURE_MODE')).toBeNull();
    expect(sanitizeIdentificationModeSelection('')).toBeNull();
    expect(sanitizeIdentificationModeSelection(INHERITED_IDENTIFICATION_MODE)).toBeNull();
    expect(sanitizeIdentificationModeSelection('code_scan')).toBe('CODE_SCAN');
    expect(sanitizeIdentificationModeSelection('INTERNAL_OCR')).toBe('INTERNAL_OCR');
  });

  it('builds request body omitting mode when inheriting', () => {
    expect(buildProcessAisleRequestBody('k1', null)).toEqual({ idempotency_key: 'k1' });
    expect(buildProcessAisleRequestBody('k1', undefined)).toEqual({ idempotency_key: 'k1' });
    expect(buildProcessAisleRequestBody('k1', 'LEGACY_LLM' as never)).toEqual({
      idempotency_key: 'k1',
    });
  });

  it('builds request body with explicit CODE_SCAN / INTERNAL_OCR', () => {
    expect(buildProcessAisleRequestBody('k1', 'CODE_SCAN')).toEqual({
      idempotency_key: 'k1',
      identification_mode: 'CODE_SCAN',
    });
    expect(buildProcessAisleRequestBody('k1', 'INTERNAL_OCR')).toEqual({
      idempotency_key: 'k1',
      identification_mode: 'INTERNAL_OCR',
    });
  });

  it('maps selection preference round-trip', () => {
    expect(selectionFromPreference(null)).toBe(INHERITED_IDENTIFICATION_MODE);
    expect(selectionFromPreference('CODE_SCAN')).toBe('CODE_SCAN');
    expect(preferenceFromSelection(INHERITED_IDENTIFICATION_MODE)).toBeNull();
    expect(preferenceFromSelection('INTERNAL_OCR')).toBe('INTERNAL_OCR');
  });

  it('maps process start errors to operator messages', () => {
    expect(
      mapProcessStartErrorMessage({
        code: 'LEGACY_PROCESSING_MODE_NOT_ALLOWED_FOR_NEW_CONFIGURATION',
      }),
    ).toMatch(/ya no está disponible/i);
    expect(mapProcessStartErrorMessage({ code: 'STRATEGY_DISABLED' })).toMatch(
      /no está disponible en este momento/i,
    );
    expect(mapProcessStartErrorMessage({ code: 'NETWORK_ERROR', status: null })).toMatch(
      /conexión/i,
    );
    expect(mapProcessStartErrorMessage({ code: 'ACTIVE_JOB_EXISTS' })).toMatch(/en curso/i);
  });

  it('labels and legacy helpers', () => {
    expect(labelForIdentificationMode(null)).toMatch(/Automático/i);
    expect(labelForIdentificationMode('CODE_SCAN')).toMatch(/Escanear/i);
    expect(isLegacyIdentificationMode('LEGACY_LLM')).toBe(true);
    expect(isSupportedIdentificationMode('INTERNAL_OCR')).toBe(true);
    expect(isSupportedIdentificationMode('LEGACY_LLM')).toBe(false);
  });
});
