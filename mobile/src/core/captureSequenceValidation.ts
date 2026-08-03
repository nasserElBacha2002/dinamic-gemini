/**
 * Mirrors backend ``validate_complete_sequence`` for client-side seal preflight.
 * Empty array means the sequenced set is valid for ``expectedCount``.
 *
 * Asset list responses may omit ``upload_client_file_id``; pass
 * ``requireClientImageId: false`` for remote list preflight.
 */

export type SequencedAssetLike = {
  readonly sequence_number?: number | null;
  readonly upload_client_file_id?: string | null;
  readonly id?: string;
};

export function validateCompleteSequence(
  assets: readonly SequencedAssetLike[],
  expectedCount: number,
  options: { readonly requireClientImageId?: boolean } = {},
): string[] {
  const requireClientImageId = options.requireClientImageId !== false;
  const errors: string[] = [];
  if (expectedCount < 1) {
    errors.push('expected_asset_count must be >= 1');
    return errors;
  }
  const sequenced = assets.filter((a) => a.sequence_number != null);
  if (sequenced.length !== expectedCount) {
    errors.push(
      `persisted sequenced asset count ${sequenced.length} != expected ${expectedCount}`,
    );
  }
  const numbers = sequenced.map((a) => Number(a.sequence_number));
  if (numbers.length > 0) {
    const min = Math.min(...numbers);
    const max = Math.max(...numbers);
    if (min !== 1) {
      errors.push(`min(sequence_number)=${min} expected 1`);
    }
    if (max !== expectedCount) {
      errors.push(`max(sequence_number)=${max} expected ${expectedCount}`);
    }
    const distinct = new Set(numbers);
    if (distinct.size !== numbers.length) {
      errors.push('duplicate sequence_number values present');
    }
    if (distinct.size !== expectedCount) {
      errors.push(`distinct sequence_number count ${distinct.size} != ${expectedCount}`);
    }
  }
  if (requireClientImageId) {
    const missingClient = sequenced.filter((a) => !(a.upload_client_file_id || '').trim());
    if (missingClient.length > 0) {
      errors.push(`${missingClient.length} assets missing client_image_id`);
    }
  }
  return errors;
}
