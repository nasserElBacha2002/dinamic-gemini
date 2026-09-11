import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { decideQuantityCompleteness, fallbackEligible } from '../src/core/quantityCompleteness';

type MatrixFile = {
  rows: Array<{
    id: string;
    kind: 'ITEM' | 'POSITION';
    required: boolean;
    expected_presence: string;
    missing_quantity_action: string;
    allow_external_fallback: boolean;
    required_fields?: string[];
    fields: Record<string, string | number | null>;
    expected: {
      quantity_required_for_completion: boolean;
      identity_complete: boolean;
      completion_complete: boolean;
      persistence_complete: boolean;
      missing_completion_fields: string[];
      fallback_eligible: boolean;
    };
  }>;
};

const matrixPath = resolve(
  __dirname,
  '../../contracts/offline-recognition/v1/quantity-completeness-matrix.json',
);

describe('quantity completeness matrix — mobile', () => {
  const file = JSON.parse(readFileSync(matrixPath, 'utf8')) as MatrixFile;

  for (const row of file.rows) {
    it(row.id, () => {
      const decision = decideQuantityCompleteness({
        kind: row.kind,
        required: row.required,
        expected_presence: row.expected_presence,
        missing_quantity_action: row.missing_quantity_action,
        allow_external_fallback: row.allow_external_fallback,
        required_fields: row.required_fields,
      });
      expect(decision.quantity_required_for_completion).toBe(
        row.expected.quantity_required_for_completion,
      );
      const identityComplete = row.expected.identity_complete;
      const quantityPresent = row.fields.quantity != null;
      expect(
        fallbackEligible(decision, { identityComplete, quantityPresent }),
      ).toBe(row.expected.fallback_eligible);
    });
  }
});
