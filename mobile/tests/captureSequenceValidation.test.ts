import { validateCompleteSequence } from '../src/core/captureSequenceValidation';

describe('validateCompleteSequence', () => {
  it('accepts contiguous 1..N with client ids', () => {
    expect(
      validateCompleteSequence(
        [
          { sequence_number: 1, upload_client_file_id: 'a' },
          { sequence_number: 2, upload_client_file_id: 'b' },
          { sequence_number: 3, upload_client_file_id: 'c' },
        ],
        3,
      ),
    ).toEqual([]);
  });

  it('rejects gaps and count mismatches', () => {
    const errors = validateCompleteSequence(
      [
        { sequence_number: 2, upload_client_file_id: 'a' },
      ],
      3,
      { requireClientImageId: false },
    );
    expect(errors.some((e) => e.includes('persisted sequenced asset count'))).toBe(true);
    expect(errors.some((e) => e.includes('min(sequence_number)'))).toBe(true);
  });
});
