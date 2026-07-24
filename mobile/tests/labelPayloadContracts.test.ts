import * as fs from 'fs';
import * as path from 'path';

import { consolidateCodeDetections } from '../src/core/codeDetectionConsolidator';
import { parseEncodedLabelPayload } from '../src/core/labelPayload';
import { hashPayloadFingerprint } from '../src/core/payloadFingerprint';

const CONTRACTS_DIR = path.resolve(__dirname, '../../contracts/code-scan/v1');

function loadJson<T>(name: string): T {
  const raw = fs.readFileSync(path.join(CONTRACTS_DIR, name), 'utf8');
  return JSON.parse(raw) as T;
}

type FixtureExpected = {
  status: 'VALID' | 'INVALID';
  format: string;
  internalCode: string | null;
  quantity: number | null;
  quantityStatus: string;
  formatVersion: string;
  warnings?: string[];
  errorCode?: string;
};

type ValidInvalidFixture = {
  name: string;
  raw: string;
  quantityMax?: number;
  expected: FixtureExpected;
};

describe('labelPayload contracts (code-scan/v1)', () => {
  const valid = loadJson<ValidInvalidFixture[]>('valid.json');
  const invalid = loadJson<ValidInvalidFixture[]>('invalid.json');

  it.each(valid)('$name matches contract', (fixture) => {
    const parsed = parseEncodedLabelPayload(
      fixture.raw,
      fixture.quantityMax != null ? { quantityMax: fixture.quantityMax } : undefined,
    );
    expect(parsed.status).toBe(fixture.expected.status);
    expect(parsed.format).toBe(fixture.expected.format);
    expect(parsed.internalCode).toBe(fixture.expected.internalCode);
    expect(parsed.quantity).toBe(fixture.expected.quantity);
    expect(parsed.quantityStatus).toBe(fixture.expected.quantityStatus);
    expect(parsed.formatVersion).toBe(fixture.expected.formatVersion);
    expect([...parsed.warnings].sort()).toEqual([...(fixture.expected.warnings ?? [])].sort());
  });

  it.each(invalid)('$name matches contract', (fixture) => {
    const parsed = parseEncodedLabelPayload(
      fixture.raw,
      fixture.quantityMax != null ? { quantityMax: fixture.quantityMax } : undefined,
    );
    expect(parsed.status).toBe(fixture.expected.status);
    expect(parsed.format).toBe(fixture.expected.format);
    expect(parsed.internalCode).toBe(fixture.expected.internalCode);
    expect(parsed.quantity).toBe(fixture.expected.quantity);
    expect(parsed.quantityStatus).toBe(fixture.expected.quantityStatus);
    expect(parsed.formatVersion).toBe(fixture.expected.formatVersion);
    if (fixture.expected.errorCode) {
      expect(parsed.status === 'INVALID' ? parsed.errorCode : undefined).toBe(
        fixture.expected.errorCode,
      );
    }
    expect([...parsed.warnings].sort()).toEqual([...(fixture.expected.warnings ?? [])].sort());
  });
});

describe('codeDetectionConsolidator contracts', () => {
  type AmbiguousFixture = {
    name: string;
    candidates: Array<{ raw: string; symbology: string }>;
    expected: {
      status: string;
      errorCode: string | null;
      internalCode: string | null;
      quantity: number | null;
    };
  };

  const ambiguous = loadJson<AmbiguousFixture[]>('ambiguous.json');

  function mapStatus(status: string): string {
    switch (status) {
      case 'MULTIPLE_DISTINCT_CODES':
      case 'QUANTITY_CONFLICT':
        return 'AMBIGUOUS';
      case 'NO_DETECTIONS':
        return 'UNRESOLVED';
      case 'NO_VALID_CODE':
        return 'INVALID';
      case 'MISSING_QUANTITY':
      case 'RESOLVED':
        return 'RESOLVED';
      default:
        return status;
    }
  }

  it.each(ambiguous)('$name', (fixture) => {
    const result = consolidateCodeDetections(
      fixture.candidates.map((c, i) => ({
        rawValue: c.raw,
        symbology: c.symbology,
        detectionIndex: i,
      })),
    );
    expect(mapStatus(result.status)).toBe(fixture.expected.status);
    expect(result.internalCode).toBe(fixture.expected.internalCode);
    expect(result.quantity).toBe(fixture.expected.quantity);
    if (fixture.expected.errorCode) {
      expect(result.status).toBe(fixture.expected.errorCode);
    } else {
      expect(result.status).toBe('RESOLVED');
    }
  });
});

describe('payloadFingerprint', () => {
  it('is stable for identical input', () => {
    expect(hashPayloadFingerprint('ABC|5')).toBe(hashPayloadFingerprint('ABC|5'));
    expect(hashPayloadFingerprint('ABC|5')).not.toBe(hashPayloadFingerprint('ABC|6'));
  });
});
