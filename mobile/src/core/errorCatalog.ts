/** Productive error catalog — user message + retry/action metadata. */

export type AppErrorCode =
  | 'AUTH_SESSION_EXPIRED'
  | 'NETWORK_OFFLINE'
  | 'UPLOAD_FILE_TOO_LARGE'
  | 'UPLOAD_UNSUPPORTED_FORMAT'
  | 'UPLOAD_PERMISSION_DENIED'
  | 'CAPTURE_STORAGE_LOW'
  | 'FGS_START_FAILED'
  | 'AISLE_INACTIVE'
  | 'JOB_ALREADY_RUNNING'
  | 'JOB_FAILED'
  | 'CONFIG_MISSING'
  | 'CONFIG_INSECURE_HTTP'
  | 'UNKNOWN';

export interface AppErrorDefinition {
  readonly code: AppErrorCode;
  readonly userMessage: string;
  readonly retryable: boolean;
  readonly severity: 'info' | 'warn' | 'error';
}

export const APP_ERRORS: Readonly<Record<AppErrorCode, AppErrorDefinition>> = {
  AUTH_SESSION_EXPIRED: {
    code: 'AUTH_SESSION_EXPIRED',
    userMessage: 'La sesión venció. Volvé a iniciar sesión.',
    retryable: false,
    severity: 'warn',
  },
  NETWORK_OFFLINE: {
    code: 'NETWORK_OFFLINE',
    userMessage: 'Sin conexión. La captura local continúa; las cargas se reanudarán al volver online.',
    retryable: true,
    severity: 'warn',
  },
  UPLOAD_FILE_TOO_LARGE: {
    code: 'UPLOAD_FILE_TOO_LARGE',
    userMessage: 'Una fotografía supera el tamaño máximo permitido.',
    retryable: false,
    severity: 'error',
  },
  UPLOAD_UNSUPPORTED_FORMAT: {
    code: 'UPLOAD_UNSUPPORTED_FORMAT',
    userMessage: 'Formato de imagen no soportado.',
    retryable: false,
    severity: 'error',
  },
  UPLOAD_PERMISSION_DENIED: {
    code: 'UPLOAD_PERMISSION_DENIED',
    userMessage: 'No tenés permisos para cargar a este pasillo.',
    retryable: false,
    severity: 'error',
  },
  CAPTURE_STORAGE_LOW: {
    code: 'CAPTURE_STORAGE_LOW',
    userMessage: 'Poco espacio de almacenamiento. Liberá espacio antes de continuar.',
    retryable: false,
    severity: 'error',
  },
  FGS_START_FAILED: {
    code: 'FGS_START_FAILED',
    userMessage: 'No se pudo iniciar el servicio de captura en segundo plano.',
    retryable: true,
    severity: 'error',
  },
  AISLE_INACTIVE: {
    code: 'AISLE_INACTIVE',
    userMessage: 'El pasillo está inactivo o no disponible.',
    retryable: false,
    severity: 'error',
  },
  JOB_ALREADY_RUNNING: {
    code: 'JOB_ALREADY_RUNNING',
    userMessage: 'Ya hay un procesamiento activo en este pasillo.',
    retryable: false,
    severity: 'warn',
  },
  JOB_FAILED: {
    code: 'JOB_FAILED',
    userMessage: 'El procesamiento del pasillo falló. Revisá el detalle o reintentá.',
    retryable: true,
    severity: 'error',
  },
  CONFIG_MISSING: {
    code: 'CONFIG_MISSING',
    userMessage: 'Falta la URL del backend en la configuración.',
    retryable: false,
    severity: 'error',
  },
  CONFIG_INSECURE_HTTP: {
    code: 'CONFIG_INSECURE_HTTP',
    userMessage: 'En producción solo se permite HTTPS.',
    retryable: false,
    severity: 'error',
  },
  UNKNOWN: {
    code: 'UNKNOWN',
    userMessage: 'Ocurrió un error inesperado.',
    retryable: true,
    severity: 'error',
  },
};

export function userMessageForCode(code: string | null | undefined): string {
  if (code && code in APP_ERRORS) {
    return APP_ERRORS[code as AppErrorCode].userMessage;
  }
  return APP_ERRORS.UNKNOWN.userMessage;
}
