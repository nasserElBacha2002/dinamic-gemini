import {
  validateConfirmedInternalCode,
  validateConfirmedQuantity,
} from '../src/features/authoritativeLocalResult/confirmLocalResultValidation';
import { ConfirmLocalResultService } from '../src/features/authoritativeLocalResult/confirmLocalResultService';
import { DEFAULT_FEATURE_FLAGS } from '../src/core/featureFlags';

describe('confirm local result validation', () => {
  it('requires non-empty internal code', () => {
    expect(validateConfirmedInternalCode('')).toBe('CODE_REQUIRED');
    expect(validateConfirmedInternalCode('   ')).toBe('CODE_REQUIRED');
    expect(validateConfirmedInternalCode('ABC')).toBeNull();
  });

  it('rejects control characters and overlong codes', () => {
    expect(validateConfirmedInternalCode('A\u0001B')).toBe('CODE_CONTROL_CHARACTERS');
    expect(validateConfirmedInternalCode('x'.repeat(49))).toBe('CODE_LENGTH_OUT_OF_RANGE');
  });

  it('validates quantity present vs missing', () => {
    expect(
      validateConfirmedQuantity({ quantity: null, quantityStatus: 'MISSING' }),
    ).toBeNull();
    expect(
      validateConfirmedQuantity({ quantity: 5, quantityStatus: 'MISSING' }),
    ).toBe('QUANTITY_MUST_BE_NULL_WHEN_MISSING');
    expect(
      validateConfirmedQuantity({ quantity: null, quantityStatus: 'PRESENT' }),
    ).toBe('QUANTITY_REQUIRED');
    expect(
      validateConfirmedQuantity({ quantity: 0, quantityStatus: 'PRESENT' }),
    ).toBe('QUANTITY_NOT_POSITIVE');
    expect(
      validateConfirmedQuantity({ quantity: 100_000_000, quantityStatus: 'PRESENT' }),
    ).toBe('QUANTITY_ABOVE_MAX');
  });
});

describe('ConfirmLocalResultService', () => {
  it('refuses confirm when authoritative flag is off', async () => {
    const service = new ConfirmLocalResultService(
      DEFAULT_FEATURE_FLAGS,
      { upsertConfirmed: jest.fn() } as never,
      { listForPhoto: jest.fn(async () => []) } as never,
    );
    await expect(
      service.confirm({
        capturePhotoId: 'p1',
        captureSessionId: 's1',
        clientFileId: 'cf1',
        confirmedByUserId: 'u1',
        edits: { internalCode: 'ABC', quantity: 1, quantityStatus: 'PRESENT' },
      }),
    ).rejects.toThrow(/no está habilitada/i);
  });

  it('preserves detected fields and stores confirmed finals', async () => {
    const upsert = jest.fn(async () => ({
      id: 'r1',
      confirmed_internal_code: 'XYZ',
    }));
    const service = new ConfirmLocalResultService(
      { ...DEFAULT_FEATURE_FLAGS, mobileAuthoritativeLocalCodeScan: true },
      { upsertConfirmed: upsert } as never,
      { listForPhoto: jest.fn(async () => []) } as never,
    );
    await service.confirm({
      capturePhotoId: 'p1',
      captureSessionId: 's1',
      clientFileId: 'cf1',
      confirmedByUserId: 'u1',
      edits: { internalCode: 'XYZ', quantity: 2, quantityStatus: 'PRESENT' },
      draft: {
        internal_code: 'ABC',
        quantity: 1,
        detected_symbology: 'QR_CODE',
        parser_version: '1.1.0',
        detector_version: 'mlkit-1',
        prepared_asset_fingerprint: 'sha256:' + 'a'.repeat(64),
      } as never,
    });
    expect(upsert).toHaveBeenCalledWith(
      expect.objectContaining({
        detectedInternalCode: 'ABC',
        detectedQuantity: 1,
        confirmedInternalCode: 'XYZ',
        confirmedQuantity: 2,
        source: 'LOCAL_MANUAL_CORRECTION',
      }),
    );
  });

  it('auto-confirms stable photos with draft codes', async () => {
    const upsert = jest.fn(async () => ({ id: 'r1', capture_photo_id: 'p1' }));
    const listForSession = jest.fn(async () => []);
    const listForPhoto = jest.fn(async () => [
      {
        internal_code: 'SKU-1',
        quantity: 3,
        quantity_status: 'PRESENT',
        status: 'READY',
        detected_symbology: 'QR_CODE',
        parser_version: '1.1.0',
        detector_version: 'mlkit-1',
        prepared_asset_fingerprint: `sha256:${'b'.repeat(64)}`,
      },
    ]);
    const service = new ConfirmLocalResultService(
      { ...DEFAULT_FEATURE_FLAGS, mobileAuthoritativeLocalCodeScan: true },
      { upsertConfirmed: upsert, listForSession } as never,
      { listForPhoto } as never,
    );
    const result = await service.confirmResolvedDraftsForSession({
      sessionId: 's1',
      confirmedByUserId: 'u1',
      photos: [
        { id: 'p1', client_file_id: 'cf1', status: 'stable' },
        { id: 'p2', client_file_id: 'cf2', status: 'error' },
      ],
    });
    expect(result).toEqual({ confirmed: 1, skipped: 1 });
    expect(upsert).toHaveBeenCalledTimes(1);
    expect(upsert).toHaveBeenCalledWith(
      expect.objectContaining({
        confirmedInternalCode: 'SKU-1',
        confirmedQuantity: 3,
        source: 'LOCAL_CODE_SCAN',
      }),
    );
  });
});
