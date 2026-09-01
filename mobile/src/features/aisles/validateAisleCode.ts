import { LocalAisleError } from './localAisleErrors';

const MAX_AISLE_CODE_LENGTH = 64;

export function validateAisleCode(code: string): string {
  const trimmed = code.trim();
  if (!trimmed) {
    throw new LocalAisleError('AISLE_CODE_INVALID', 'El código del pasillo es obligatorio.');
  }
  if (trimmed.length > MAX_AISLE_CODE_LENGTH) {
    throw new LocalAisleError(
      'AISLE_CODE_INVALID',
      `El código del pasillo supera el máximo permitido (${MAX_AISLE_CODE_LENGTH}).`,
    );
  }
  return trimmed;
}
