/**
 * DINAMIC_POSITION payload v1/v2 — mirrors backend domain/aisle_location/payload.py
 * and client_position_label/hierarchy.py.
 *
 * Client-side parse never claims cryptographic signature verification.
 */

export type PositionSide = 'LEFT' | 'RIGHT';

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

/** Active position context after scanning a position label (forward-fill). */
export type ActivePositionState = {
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
  readonly validationStatus: 'STRUCTURALLY_VALID_UNVERIFIED';
  readonly signature: string | null;
  readonly keyVersion: number | null;
};

export function activePositionFromParsed(
  parsed: ParsedDinamicPosition,
  sourcePayload: string
): ActivePositionState {
  const rawPayload = sourcePayload.trim();
  return {
    labelId: parsed.labelId,
    positionLabelId: parsed.labelId,
    displayName: parsed.displayName,
    canonicalKey: parsed.canonicalKey,
    pallet: parsed.pallet,
    side: parsed.side,
    level: parsed.level,
    markerIndex: parsed.markerIndex,
    markerTotal: parsed.markerTotal,
    formattedMarker: parsed.formattedMarker,
    rawPayload,
    sourcePayload: rawPayload,
    validationStatus: 'STRUCTURALLY_VALID_UNVERIFIED',
    signature: parsed.signature,
    keyVersion: parsed.keyVersion,
  };
}
