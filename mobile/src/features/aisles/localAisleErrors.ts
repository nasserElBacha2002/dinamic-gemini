export type LocalAisleErrorCode =
  | 'INVENTORY_NOT_AVAILABLE_OFFLINE'
  | 'INVENTORY_INACTIVE'
  | 'INVENTORY_CLIENT_NOT_AVAILABLE_OFFLINE'
  | 'SUPPLIER_NOT_AVAILABLE_OFFLINE'
  | 'SUPPLIER_INACTIVE'
  | 'SUPPLIER_CLIENT_MISMATCH'
  | 'RECOGNITION_CONFIG_NOT_READY'
  | 'LOCAL_AISLE_CREATE_FAILED'
  | 'AISLE_CODE_INVALID';

const MESSAGES: Record<LocalAisleErrorCode, string> = {
  INVENTORY_NOT_AVAILABLE_OFFLINE: 'El inventario no está disponible offline.',
  INVENTORY_INACTIVE: 'El inventario está inactivo; no se pueden crear pasillos nuevos.',
  INVENTORY_CLIENT_NOT_AVAILABLE_OFFLINE:
    'El inventario no tiene cliente asociado offline; no se puede validar el proveedor.',
  SUPPLIER_NOT_AVAILABLE_OFFLINE: 'El proveedor no está disponible offline.',
  SUPPLIER_INACTIVE: 'El proveedor está inactivo; elegí otro para un pasillo nuevo.',
  SUPPLIER_CLIENT_MISMATCH: 'El proveedor no pertenece al cliente de este inventario.',
  RECOGNITION_CONFIG_NOT_READY:
    'Proveedor no está listo para trabajar offline. Sincronizá perfiles de reconocimiento.',
  LOCAL_AISLE_CREATE_FAILED: 'No se pudo guardar el pasillo localmente.',
  AISLE_CODE_INVALID: 'El código del pasillo no es válido.',
};

export class LocalAisleError extends Error {
  readonly code: LocalAisleErrorCode;

  constructor(code: LocalAisleErrorCode, message?: string) {
    super(message ?? MESSAGES[code]);
    this.name = 'LocalAisleError';
    this.code = code;
  }
}

export function userMessageForLocalAisleError(error: unknown): string {
  if (error instanceof LocalAisleError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return MESSAGES.LOCAL_AISLE_CREATE_FAILED;
}
