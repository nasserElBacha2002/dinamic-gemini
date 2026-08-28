import { describe, expect, it } from '@jest/globals';
import {
  formatLocalScanDetection,
  labelForLocalScanStatus,
} from '../src/features/localCodeScan/localScanUi';

describe('localScanUi D1 rejection feedback', () => {
  it('shows checksum message for D1_CANDIDATES_FAILED', () => {
    const rejections = JSON.stringify([
      {
        labelId: 'A1B2C3D4E5',
        validationStatus: 'D1_CHECKSUM_FAILED',
        reason: 'checksum mismatch',
      },
    ]);
    expect(labelForLocalScanStatus('INVALID', 'D1_CANDIDATES_FAILED', rejections)).toBe(
      'Etiqueta inválida: checksum incorrecto',
    );
    expect(
      formatLocalScanDetection({
        status: 'INVALID',
        internal_code: null,
        quantity: null,
        error_code: 'D1_CANDIDATES_FAILED',
        detected_symbology: 'QR_CODE',
        rejections_json: rejections,
      }),
    ).toBe('Etiqueta inválida: checksum incorrecto');
  });

  it('shows generic Dinamic invalid for malformed rejections', () => {
    const rejections = JSON.stringify([
      { labelId: null, validationStatus: 'D1_MALFORMED', reason: 'd1_grammar_mismatch' },
    ]);
    expect(labelForLocalScanStatus('INVALID', 'D1_CANDIDATES_FAILED', rejections)).toBe(
      'Etiqueta Dinamic inválida',
    );
  });

  it('shows duplicate position message', () => {
    expect(labelForLocalScanStatus('DETECTED_UNVERIFIED', 'POSITION_LABEL_DUPLICATE')).toBe(
      'Etiqueta de posición duplicada — ya registrada en esta sesión',
    );
  });
});
