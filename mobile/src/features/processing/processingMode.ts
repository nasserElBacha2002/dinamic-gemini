/**
 * Aisle identification / processing mode for mobile process-aisle starts.
 * Matches web PROCESS_AISLE_IDENTIFICATION_OPTIONS + backend ProcessAisleRequest.identification_mode.
 * Inherit = omit field / null (never send AUTO or empty string).
 */

export const AISLE_IDENTIFICATION_MODES = ['CODE_SCAN', 'INTERNAL_OCR'] as const;

export type AisleIdentificationMode = (typeof AISLE_IDENTIFICATION_MODES)[number];

/** UI sentinel — never sent on the wire. */
export const INHERITED_IDENTIFICATION_MODE = '__INHERITED__' as const;

export type IdentificationModeSelection = AisleIdentificationMode | typeof INHERITED_IDENTIFICATION_MODE;

export interface ProcessAisleIdentificationOption {
  readonly value: IdentificationModeSelection;
  readonly label: string;
  readonly description: string;
}

/** Product options for new jobs (legacy excluded). */
export const PROCESS_AISLE_IDENTIFICATION_OPTIONS: readonly ProcessAisleIdentificationOption[] = [
  {
    value: INHERITED_IDENTIFICATION_MODE,
    label: 'Automático (configuración predeterminada)',
    description: 'Utiliza la configuración definida para el pasillo, inventario o cliente.',
  },
  {
    value: 'CODE_SCAN',
    label: 'Escanear códigos',
    description: 'Lee códigos QR y códigos de barras de las etiquetas.',
  },
  {
    value: 'INTERNAL_OCR',
    label: 'Reconocimiento de etiqueta',
    description: 'Reconoce el código, la cantidad y otros datos impresos en la etiqueta.',
  },
] as const;

export function isSupportedIdentificationMode(value: unknown): value is AisleIdentificationMode {
  return value === 'CODE_SCAN' || value === 'INTERNAL_OCR';
}

export function isLegacyIdentificationMode(value: unknown): boolean {
  const raw = String(value ?? '')
    .trim()
    .toUpperCase();
  return raw === 'LEGACY_LLM' || raw === 'LEGACY_LLM_TEMPORARY';
}

/**
 * Normalize UI / persisted preference to a wire-safe selection.
 * Legacy and unknown values fall back to inherit (null override).
 */
export function sanitizeIdentificationModeSelection(
  raw: unknown,
): AisleIdentificationMode | null {
  if (raw == null) return null;
  if (raw === INHERITED_IDENTIFICATION_MODE) return null;
  const upper = String(raw).trim().toUpperCase();
  if (!upper) return null;
  if (isLegacyIdentificationMode(upper)) return null;
  if (isSupportedIdentificationMode(upper)) return upper;
  return null;
}

export function selectionFromPreference(
  preference: AisleIdentificationMode | null,
): IdentificationModeSelection {
  return preference ?? INHERITED_IDENTIFICATION_MODE;
}

export function preferenceFromSelection(
  selection: IdentificationModeSelection,
): AisleIdentificationMode | null {
  if (selection === INHERITED_IDENTIFICATION_MODE) return null;
  return sanitizeIdentificationModeSelection(selection);
}

export function labelForIdentificationMode(mode: AisleIdentificationMode | null | undefined): string {
  if (mode == null) {
    return 'Automático (configuración predeterminada)';
  }
  const found = PROCESS_AISLE_IDENTIFICATION_OPTIONS.find((o) => o.value === mode);
  return found?.label ?? mode;
}

export interface ProcessAisleRequestBody {
  readonly idempotency_key: string;
  readonly identification_mode?: AisleIdentificationMode;
}

/** Build POST /process body. Inherit → omit identification_mode (do not send null/empty). */
export function buildProcessAisleRequestBody(
  idempotencyKey: string,
  identificationMode: AisleIdentificationMode | null | undefined,
): ProcessAisleRequestBody {
  const mode = sanitizeIdentificationModeSelection(identificationMode);
  if (mode == null) {
    return { idempotency_key: idempotencyKey };
  }
  return {
    idempotency_key: idempotencyKey,
    identification_mode: mode,
  };
}

export function mapProcessStartErrorMessage(
  error: { code?: string | null; status?: number | null; message?: string },
): string {
  const code = (error.code || '').toUpperCase();
  if (code === 'LEGACY_PROCESSING_MODE_NOT_ALLOWED_FOR_NEW_CONFIGURATION') {
    return 'El tipo de procesamiento seleccionado ya no está disponible.';
  }
  if (code === 'STRATEGY_DISABLED' || code === 'CODE_SCAN_DISABLED') {
    return 'Este tipo de procesamiento no está disponible en este momento. Seleccioná otra opción.';
  }
  if (code === 'NETWORK_ERROR') {
    return 'No se pudo iniciar el procesamiento. Verificá tu conexión e intentá nuevamente.';
  }
  if (code === 'ACTIVE_JOB_EXISTS') {
    return 'Ya hay un procesamiento en curso para este pasillo.';
  }
  if (error.status == null && !code) {
    return 'No se pudo iniciar el procesamiento. Verificá tu conexión e intentá nuevamente.';
  }
  const message = (error.message || '').trim();
  if (message) return message;
  return 'No se pudo iniciar el procesamiento.';
}
