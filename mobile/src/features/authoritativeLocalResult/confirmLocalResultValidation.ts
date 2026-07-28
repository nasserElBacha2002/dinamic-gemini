import { CODE_MAX_LENGTH, QUANTITY_MAX_DEFAULT } from '../../core/labelPayload';
import type { ConfirmedQuantityStatus } from '../../database/repositories/confirmedLocalResultRepository';

export type ConfirmValidationErrorCode =
  | 'CODE_REQUIRED'
  | 'CODE_LENGTH_OUT_OF_RANGE'
  | 'CODE_CONTROL_CHARACTERS'
  | 'QUANTITY_REQUIRED'
  | 'QUANTITY_NOT_POSITIVE'
  | 'QUANTITY_ABOVE_MAX'
  | 'QUANTITY_MUST_BE_NULL_WHEN_MISSING';

function hasControlChars(value: string): boolean {
  for (let i = 0; i < value.length; i += 1) {
    const c = value.charCodeAt(i);
    if (c < 0x20 || c === 0x7f) {
      return true;
    }
  }
  return false;
}

export function validateConfirmedInternalCode(code: string): ConfirmValidationErrorCode | null {
  const trimmed = code.trim();
  if (!trimmed) {
    return 'CODE_REQUIRED';
  }
  if (trimmed.length < 1 || trimmed.length > CODE_MAX_LENGTH) {
    return 'CODE_LENGTH_OUT_OF_RANGE';
  }
  if (hasControlChars(trimmed)) {
    return 'CODE_CONTROL_CHARACTERS';
  }
  return null;
}

export function validateConfirmedQuantity(input: {
  readonly quantity: number | null;
  readonly quantityStatus: ConfirmedQuantityStatus;
  readonly quantityMax?: number;
}): ConfirmValidationErrorCode | null {
  const max = input.quantityMax ?? QUANTITY_MAX_DEFAULT;
  if (input.quantityStatus === 'MISSING') {
    if (input.quantity != null) {
      return 'QUANTITY_MUST_BE_NULL_WHEN_MISSING';
    }
    return null;
  }
  if (input.quantity == null) {
    return 'QUANTITY_REQUIRED';
  }
  if (!Number.isInteger(input.quantity) || input.quantity <= 0) {
    return 'QUANTITY_NOT_POSITIVE';
  }
  if (input.quantity > max) {
    return 'QUANTITY_ABOVE_MAX';
  }
  return null;
}

export function userMessageForConfirmValidation(code: ConfirmValidationErrorCode): string {
  switch (code) {
    case 'CODE_REQUIRED':
      return 'El código interno es obligatorio.';
    case 'CODE_LENGTH_OUT_OF_RANGE':
      return `El código debe tener entre 1 y ${CODE_MAX_LENGTH} caracteres.`;
    case 'CODE_CONTROL_CHARACTERS':
      return 'El código contiene caracteres no válidos.';
    case 'QUANTITY_REQUIRED':
      return 'La cantidad es obligatoria cuando está presente.';
    case 'QUANTITY_NOT_POSITIVE':
      return 'La cantidad debe ser un entero positivo.';
    case 'QUANTITY_ABOVE_MAX':
      return 'La cantidad supera el máximo permitido.';
    case 'QUANTITY_MUST_BE_NULL_WHEN_MISSING':
      return 'La cantidad debe estar vacía cuando se marca como ausente.';
    default:
      return 'Datos inválidos.';
  }
}
