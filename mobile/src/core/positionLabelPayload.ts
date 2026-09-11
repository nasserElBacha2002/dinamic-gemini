/**
 * DINAMIC_POSITION payload v1/v2 — mirrors backend domain/aisle_location/payload.py
 * and client_position_label/hierarchy.py.
 *
 * Client-side parse never claims cryptographic signature verification.
 */

export type PositionSide = 'LEFT' | 'RIGHT';
export const LOCAL_POSITION_SCHEMA_VERSION = 2;
export const POSITION_SYNC_PAYLOAD_VERSION = 2;
export const LOCAL_POSITION_CODE_MAX_LENGTH = 64;

export type LocalPositionSource =
  | 'LOCAL_CODE_SCAN'
  | 'SERVER_CODE_SCAN'
  | 'VISION'
  | 'OCR'
  | 'TXT'
  | 'MANUAL';

export type LocalPositionValidationStatus =
  | 'STRUCTURALLY_VALID'
  | 'LEGACY_ACCEPTED'
  | 'PENDING_SERVER_VALIDATION'
  | 'SERVER_ACCEPTED'
  | 'SERVER_REJECTED';

export type LocalSignatureVerification =
  | 'MISSING'
  | 'UNVERIFIED'
  | 'INVALID'
  | 'NOT_APPLICABLE';

export type LocalRecognizedPositionV2 = {
  readonly schemaVersion: 2;
  readonly payloadVersion: 2;
  readonly localRecognitionId: string;
  readonly captureSessionId: string;
  readonly inventoryId: string | null;
  readonly aisleLocalId: string | null;
  readonly rawCode: string;
  readonly normalizedCode: string;
  readonly remotePositionId: string | null;
  readonly remotePositionLabelId: string | null;
  readonly pallet: string | null;
  readonly side: PositionSide | null;
  readonly level: number | null;
  readonly source: LocalPositionSource;
  readonly profileId: string | null;
  readonly profileVersion: number | null;
  readonly clientSupplierId: string | null;
  readonly validationStatus: LocalPositionValidationStatus;
  readonly signatureEvidence: {
    readonly present: boolean;
    readonly verification: LocalSignatureVerification;
  };
  readonly capturedAt: string;
};

export function normalizeLocalPositionCode(raw: string): string {
  const normalized = String(raw ?? '').normalize('NFC').trim().toUpperCase();
  if (!normalized) throw new Error('POSITION_CODE_REQUIRED');
  if (normalized.length > LOCAL_POSITION_CODE_MAX_LENGTH) {
    throw new Error('POSITION_CODE_TOO_LONG');
  }
  for (const character of normalized) {
    if (/\p{C}/u.test(character)) throw new Error('POSITION_CODE_CONTROL_CHARACTER');
  }
  return normalized;
}

export type DinamicPositionValidationStatus =
  | 'STRUCTURALLY_VALID_UNVERIFIED'
  | 'INVALID_FORMAT'
  | 'UNKNOWN_VERSION';

export type DinamicPositionPayloadV1 = {
  readonly type: 'DINAMIC_POSITION';
  readonly version: 1;
  readonly label_id: string;
  readonly position_id?: string;
  readonly key_version?: number;
  readonly signature?: string;
};

export type DinamicPositionPayloadV2 = {
  readonly type: 'DINAMIC_POSITION';
  readonly version: 2;
  readonly label_id: string;
  readonly pallet: string;
  readonly side: PositionSide;
  readonly level: number;
  readonly marker_index: number;
  readonly marker_total: number;
  readonly position_id?: string;
  readonly key_version?: number;
  readonly signature?: string;
};

export type DinamicPositionPayload = DinamicPositionPayloadV1 | DinamicPositionPayloadV2;

export type ParsedDinamicPosition = {
  readonly labelId: string;
  readonly version: number;
  readonly pallet: string | null;
  readonly side: PositionSide | null;
  readonly level: number | null;
  readonly markerIndex: number | null;
  readonly markerTotal: number | null;
  readonly formattedMarker: string | null;
  readonly displayName: string;
  readonly canonicalKey: string;
  readonly validationStatus: 'STRUCTURALLY_VALID_UNVERIFIED';
  readonly signature: string | null;
  readonly keyVersion: number | null;
  readonly raw: DinamicPositionPayload;
};

export function localizeSideEs(side: PositionSide): string {
  return side === 'LEFT' ? 'Izquierda' : 'Derecha';
}

export function formatMarkerPair(index: number, total: number): string {
  const width = total <= 99 ? 2 : String(total).length;
  return `${String(index).padStart(width, '0')}/${String(total).padStart(width, '0')}`;
}

function asSide(value: unknown): PositionSide | null {
  if (value === 'LEFT' || value === 'RIGHT') return value;
  return null;
}

function optionalSignature(parsed: Record<string, unknown>): string | null {
  return typeof parsed.signature === 'string' ? parsed.signature : null;
}

function optionalKeyVersion(parsed: Record<string, unknown>): number | null {
  return typeof parsed.key_version === 'number' ? parsed.key_version : null;
}

/**
 * Classify raw text without claiming signature verification.
 * Use for tests / diagnostics; {@link parseDinamicPositionPayload} still returns null on invalid.
 */
export function classifyDinamicPositionPayload(raw: string): DinamicPositionValidationStatus {
  const text = (raw ?? '').trim();
  if (!text.startsWith('{')) return 'INVALID_FORMAT';
  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(text) as Record<string, unknown>;
  } catch {
    return 'INVALID_FORMAT';
  }
  if (parsed.type !== 'DINAMIC_POSITION') return 'INVALID_FORMAT';
  const labelId =
    typeof parsed.label_id === 'string'
      ? parsed.label_id.trim()
      : typeof parsed.position_id === 'string'
        ? parsed.position_id.trim()
        : '';
  if (!labelId) return 'INVALID_FORMAT';
  const version = typeof parsed.version === 'number' ? parsed.version : 1;
  if (version !== 1 && version !== 2) return 'UNKNOWN_VERSION';

  if (version === 2) {
    const pallet = typeof parsed.pallet === 'string' ? parsed.pallet.trim() : '';
    const side = asSide(parsed.side);
    const level = typeof parsed.level === 'number' ? parsed.level : null;
    const markerIndex = typeof parsed.marker_index === 'number' ? parsed.marker_index : null;
    const markerTotal = typeof parsed.marker_total === 'number' ? parsed.marker_total : null;
    if (
      !pallet ||
      !side ||
      level == null ||
      level < 1 ||
      markerIndex == null ||
      markerTotal == null ||
      markerIndex < 1 ||
      markerTotal < 1 ||
      markerIndex > markerTotal
    ) {
      return 'INVALID_FORMAT';
    }
  }

  return 'STRUCTURALLY_VALID_UNVERIFIED';
}

export function parseDinamicPositionPayload(raw: string): ParsedDinamicPosition | null {
  const status = classifyDinamicPositionPayload(raw);
  if (status !== 'STRUCTURALLY_VALID_UNVERIFIED') return null;

  const text = (raw ?? '').trim();
  const parsed = JSON.parse(text) as Record<string, unknown>;
  const labelId =
    typeof parsed.label_id === 'string'
      ? parsed.label_id.trim()
      : typeof parsed.position_id === 'string'
        ? parsed.position_id.trim()
        : '';
  const version = typeof parsed.version === 'number' ? parsed.version : 1;
  const signature = optionalSignature(parsed);
  const keyVersion = optionalKeyVersion(parsed);

  if (version === 2) {
    const pallet = (parsed.pallet as string).trim();
    const side = asSide(parsed.side)!;
    const level = parsed.level as number;
    const markerIndex = parsed.marker_index as number;
    const markerTotal = parsed.marker_total as number;
    const formattedMarker = formatMarkerPair(markerIndex, markerTotal);
    return {
      labelId,
      version,
      pallet,
      side,
      level,
      markerIndex,
      markerTotal,
      formattedMarker,
      displayName: `${pallet} ${side} N${level} ${formattedMarker}`,
      canonicalKey: `${pallet.toUpperCase()}|${side}|${level}|${markerIndex}|${markerTotal}`,
      validationStatus: 'STRUCTURALLY_VALID_UNVERIFIED',
      signature,
      keyVersion,
      raw: parsed as unknown as DinamicPositionPayloadV2,
    };
  }

  return {
    labelId,
    version,
    pallet: null,
    side: null,
    level: null,
    markerIndex: null,
    markerTotal: null,
    formattedMarker: null,
    displayName: labelId,
    canonicalKey: labelId,
    validationStatus: 'STRUCTURALLY_VALID_UNVERIFIED',
    signature,
    keyVersion,
    raw: parsed as unknown as DinamicPositionPayloadV1,
  };
}

type ActivePositionLegacyAliases = {
  readonly labelId: string;
  /** Same as label_id from payload (alias for export/audit columns). */
  readonly positionLabelId: string;
  readonly displayName: string;
  readonly canonicalKey: string;
  readonly pallet: string | null;
  readonly side: PositionSide | null;
  readonly level: number | null;
  readonly markerIndex: number | null;
  readonly markerTotal: number | null;
  readonly formattedMarker: string | null;
  /** Full raw QR/JSON payload string. */
  readonly rawPayload: string;
  /** @deprecated Prefer rawPayload — kept for older callers. */
  readonly sourcePayload: string;
  readonly signature: string | null;
  readonly keyVersion: number | null;
};

/** V2 state plus stable legacy aliases used by exports during rollout. */
export type ActivePositionState = LocalRecognizedPositionV2 & ActivePositionLegacyAliases;

export type PositionActivationContext = {
  readonly localRecognitionId: string;
  readonly captureSessionId: string;
  readonly inventoryId: string | null;
  readonly aisleLocalId: string | null;
  readonly source: LocalPositionSource;
  readonly profileId?: string | null;
  readonly profileVersion?: number | null;
  readonly clientSupplierId?: string | null;
  readonly remotePositionId?: string | null;
  readonly remotePositionLabelId?: string | null;
  readonly capturedAt?: string;
};

export type LocalPositionRecognitionInput = PositionActivationContext & {
  readonly rawCode: string;
  readonly positionCode?: string;
  readonly normalizedCode?: string;
  readonly canonicalKey?: string;
  readonly displayName?: string;
  readonly rawPayload: string;
  readonly pallet?: string | null;
  readonly side?: PositionSide | null;
  readonly level?: number | null;
  readonly markerIndex?: number | null;
  readonly markerTotal?: number | null;
  readonly formattedMarker?: string | null;
  readonly signatureValue?: string | null;
  readonly keyVersion?: number | null;
};

export function createActivePositionState(
  input: LocalPositionRecognitionInput
): ActivePositionState {
  const normalizedCode = normalizeLocalPositionCode(input.normalizedCode ?? input.rawCode);
  const rawCode = input.rawCode;
  const positionCode = (input.positionCode ?? input.rawCode).trim();
  const rawPayload = input.rawPayload;
  return {
    schemaVersion: LOCAL_POSITION_SCHEMA_VERSION,
    payloadVersion: POSITION_SYNC_PAYLOAD_VERSION,
    localRecognitionId: input.localRecognitionId,
    captureSessionId: input.captureSessionId,
    inventoryId: input.inventoryId,
    aisleLocalId: input.aisleLocalId,
    rawCode,
    normalizedCode,
    remotePositionId: input.remotePositionId ?? null,
    remotePositionLabelId: input.remotePositionLabelId ?? null,
    labelId: positionCode,
    positionLabelId: positionCode,
    displayName: input.displayName ?? positionCode,
    canonicalKey: input.canonicalKey ?? normalizedCode,
    pallet: input.pallet ?? null,
    side: input.side ?? null,
    level: input.level ?? null,
    markerIndex: input.markerIndex ?? null,
    markerTotal: input.markerTotal ?? null,
    formattedMarker: input.formattedMarker ?? null,
    rawPayload,
    sourcePayload: rawPayload,
    source: input.source,
    profileId: input.profileId ?? null,
    profileVersion: input.profileVersion ?? null,
    clientSupplierId: input.clientSupplierId ?? null,
    validationStatus: 'STRUCTURALLY_VALID',
    signatureEvidence: {
      present: Boolean(input.signatureValue),
      verification: input.signatureValue ? 'UNVERIFIED' : 'MISSING',
    },
    signature: input.signatureValue ?? null,
    keyVersion: input.keyVersion ?? null,
    capturedAt: input.capturedAt ?? new Date().toISOString(),
  };
}

export function activePositionFromParsed(
  parsed: ParsedDinamicPosition,
  sourcePayload: string,
  context: PositionActivationContext
): ActivePositionState {
  return createActivePositionState({
    ...context,
    rawCode: sourcePayload,
    positionCode: parsed.labelId,
    normalizedCode: parsed.labelId,
    canonicalKey: parsed.canonicalKey,
    displayName: parsed.displayName,
    rawPayload: sourcePayload,
    pallet: parsed.pallet,
    side: parsed.side,
    level: parsed.level,
    markerIndex: parsed.markerIndex,
    markerTotal: parsed.markerTotal,
    formattedMarker: parsed.formattedMarker,
    signatureValue: parsed.signature,
    keyVersion: parsed.keyVersion,
  });
}

export type ActivePositionParseResult =
  | { readonly ok: true; readonly state: ActivePositionState; readonly migrated: boolean }
  | { readonly ok: false; readonly errorCode: string };

export function parseActivePositionStateJson(
  json: string,
  expected: Omit<PositionActivationContext, 'localRecognitionId' | 'source'>
): ActivePositionParseResult {
  let value: unknown;
  try {
    value = JSON.parse(json);
  } catch {
    return { ok: false, errorCode: 'ACTIVE_POSITION_JSON_INVALID' };
  }
  if (!isRecord(value)) {
    return { ok: false, errorCode: 'ACTIVE_POSITION_SCHEMA_INVALID' };
  }
  if (value.schemaVersion === LOCAL_POSITION_SCHEMA_VERSION) {
    return parseV2ActivePosition(value, expected);
  }
  const labelId = textOrNull(value.labelId) ?? textOrNull(value.positionLabelId);
  const rawPayload =
    exactTextOrNull(value.rawPayload) ?? exactTextOrNull(value.sourcePayload);
  if (!labelId || !rawPayload) {
    return { ok: false, errorCode: 'ACTIVE_POSITION_LEGACY_INVALID' };
  }
  const parsed = parseDinamicPositionPayload(rawPayload);
  const parsedCode = parsed ? safeNormalizePositionCode(parsed.labelId) : null;
  const labelCode = safeNormalizePositionCode(labelId);
  if (!parsed || !parsedCode || parsedCode !== labelCode) {
    return { ok: false, errorCode: 'ACTIVE_POSITION_LEGACY_INVALID' };
  }
  return {
    ok: true,
    migrated: true,
    state: activePositionFromParsed(parsed, rawPayload, {
      ...expected,
      localRecognitionId: `legacy:${expected.captureSessionId}:${labelCode}`,
      source: 'LOCAL_CODE_SCAN',
    }),
  };
}

export function serializeActivePositionState(state: ActivePositionState): string {
  return JSON.stringify(state);
}

export function serializeLegacyActivePositionState(state: ActivePositionState): string {
  return JSON.stringify({
    labelId: state.labelId,
    positionLabelId: state.positionLabelId,
    displayName: state.displayName,
    canonicalKey: state.canonicalKey,
    pallet: state.pallet,
    side: state.side,
    level: state.level,
    markerIndex: state.markerIndex,
    markerTotal: state.markerTotal,
    formattedMarker: state.formattedMarker,
    rawPayload: state.rawPayload,
    sourcePayload: state.sourcePayload,
    validationStatus: 'STRUCTURALLY_VALID_UNVERIFIED',
    signature: state.signature,
    keyVersion: state.keyVersion,
  });
}

function parseV2ActivePosition(
  value: Record<string, unknown>,
  expected: Omit<PositionActivationContext, 'localRecognitionId' | 'source'>
): ActivePositionParseResult {
  const rawCode = exactTextOrNull(value.rawCode);
  const normalizedCode = textOrNull(value.normalizedCode);
  const localRecognitionId = textOrNull(value.localRecognitionId);
  const source = textOrNull(value.source);
  if (!rawCode || !normalizedCode || !localRecognitionId || !isLocalPositionSource(source)) {
    return { ok: false, errorCode: 'ACTIVE_POSITION_SCHEMA_INVALID' };
  }
  const identityCode = textOrNull(value.labelId) ?? rawCode;
  const canonicalIdentityCode = safeNormalizePositionCode(identityCode);
  const canonicalStoredCode = safeNormalizePositionCode(normalizedCode);
  if (
    value.captureSessionId !== expected.captureSessionId ||
    value.inventoryId !== expected.inventoryId ||
    value.aisleLocalId !== expected.aisleLocalId ||
    canonicalIdentityCode === null ||
    canonicalStoredCode === null ||
    canonicalIdentityCode !== canonicalStoredCode
  ) {
    return { ok: false, errorCode: 'ACTIVE_POSITION_CONTEXT_MISMATCH' };
  }
  const signatureEvidence = isRecord(value.signatureEvidence)
    ? value.signatureEvidence
    : isRecord(value.signature)
      ? value.signature
      : {};
  const verification = textOrNull(signatureEvidence.verification);
  if (!isLocalSignatureVerification(verification)) {
    return { ok: false, errorCode: 'ACTIVE_POSITION_SIGNATURE_INVALID' };
  }
  const side: PositionSide | null =
    value.side === 'LEFT' || value.side === 'RIGHT' ? value.side : null;
  const aliases = {
    labelId: textOrNull(value.labelId) ?? rawCode,
    positionLabelId: textOrNull(value.positionLabelId) ?? rawCode,
    displayName: textOrNull(value.displayName) ?? rawCode,
    canonicalKey: textOrNull(value.canonicalKey) ?? normalizedCode,
    pallet: textOrNull(value.pallet),
    side,
    level: integerOrNull(value.level),
    markerIndex: integerOrNull(value.markerIndex),
    markerTotal: integerOrNull(value.markerTotal),
    formattedMarker: textOrNull(value.formattedMarker),
    rawPayload: exactTextOrNull(value.rawPayload) ?? rawCode,
    sourcePayload: exactTextOrNull(value.sourcePayload) ?? rawCode,
    signature: textOrNull(value.signature) ?? textOrNull(value.signatureValue),
    keyVersion: integerOrNull(value.keyVersion),
  };
  return {
    ok: true,
    migrated: false,
    state: {
      ...aliases,
      schemaVersion: 2,
      payloadVersion: 2,
      localRecognitionId,
      captureSessionId: expected.captureSessionId,
      inventoryId: expected.inventoryId,
      aisleLocalId: expected.aisleLocalId,
      rawCode,
      normalizedCode: canonicalStoredCode,
      remotePositionId: textOrNull(value.remotePositionId),
      remotePositionLabelId: textOrNull(value.remotePositionLabelId),
      source,
      profileId: textOrNull(value.profileId),
      profileVersion: integerOrNull(value.profileVersion),
      clientSupplierId: textOrNull(value.clientSupplierId),
      validationStatus: isLocalPositionValidationStatus(value.validationStatus)
        ? value.validationStatus
        : 'STRUCTURALLY_VALID',
      signatureEvidence: {
        present: signatureEvidence.present === true,
        verification,
      },
      capturedAt: textOrNull(value.capturedAt) ?? new Date(0).toISOString(),
    },
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function textOrNull(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function exactTextOrNull(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function integerOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isInteger(value) ? value : null;
}

function isLocalPositionSource(value: string | null): value is LocalPositionSource {
  return (
    value === 'LOCAL_CODE_SCAN' ||
    value === 'SERVER_CODE_SCAN' ||
    value === 'VISION' ||
    value === 'OCR' ||
    value === 'TXT' ||
    value === 'MANUAL'
  );
}

function isLocalSignatureVerification(
  value: string | null
): value is LocalSignatureVerification {
  return (
    value === 'MISSING' ||
    value === 'UNVERIFIED' ||
    value === 'INVALID' ||
    value === 'NOT_APPLICABLE'
  );
}

function isLocalPositionValidationStatus(
  value: unknown
): value is LocalPositionValidationStatus {
  return (
    value === 'STRUCTURALLY_VALID' ||
    value === 'LEGACY_ACCEPTED' ||
    value === 'PENDING_SERVER_VALIDATION' ||
    value === 'SERVER_ACCEPTED' ||
    value === 'SERVER_REJECTED'
  );
}

function safeNormalizePositionCode(value: string): string | null {
  try {
    return normalizeLocalPositionCode(value);
  } catch {
    return null;
  }
}
