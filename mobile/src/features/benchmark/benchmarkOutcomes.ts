/**
 * Scan / pipeline terminal outcomes for fixtures (including intentional QR duplicates).
 * POSITION_LABEL_DETECTED is a success semantic for position-only photos (see localCodeScanStrategy).
 */
export type BenchmarkPhotoOutcome =
  | 'decoded_accepted'
  | 'decoded_duplicate'
  | 'decoded_invalid_format'
  | 'position_detected'
  | 'position_duplicate'
  | 'not_detected'
  | 'scanner_technical_error'
  | 'profile_resolution_error'
  | 'persistence_error'
  | 'unknown';

const PROFILE_CODES = new Set([
  'PACKAGE_EXPORT_OFFLINE_CONFIG_REQUIRED',
  'RECOGNITION_CONFIG_NOT_READY',
  'SUPPLIER_PROFILE_MISSING',
  'PROFILE_RESOLUTION_FAILED',
  'AMBIGUOUS_LABEL_KIND',
]);

const TECHNICAL_CODES = new Set([
  'LOCAL_SCAN_TIMEOUT',
  'LOCAL_SCAN_FAILED',
  'SCANNING_LEASE_EXPIRED',
  'CANCELLED',
  'EXPORT_PREP_FAILED',
  'EXPORT_PREP_HASH_FAILED',
  'EXPORT_PREP_DRAFT_NOT_READY',
]);

const NOT_DETECTED_CODES = new Set([
  'NO_DETECTIONS',
  'NO_VALID_CODE',
  'NO_CODE',
  'NOT_DETECTED',
  'D1_CANDIDATES_FAILED',
]);

const INVALID_FORMAT_CODES = new Set([
  'INVALID_FORMAT',
  'INVALID_PAYLOAD',
  'PARSE_ERROR',
  'PAYLOAD_PARSE_FAILED',
]);

const PERSIST_CODES = new Set([
  'SQLITE_ERROR',
  'PERSIST_FAILED',
  'TX_FAILED',
  'DATABASE_ERROR',
]);

export function classifyDraftOutcome(input: {
  readonly draftStatus: string | null | undefined;
  readonly errorCode: string | null | undefined;
  readonly validationStatus: string | null | undefined;
  readonly positionDetected?: boolean | number | null;
}): BenchmarkPhotoOutcome {
  const err = (input.errorCode ?? '').trim().toUpperCase();
  const validation = (input.validationStatus ?? '').trim().toUpperCase();
  const status = (input.draftStatus ?? '').trim().toUpperCase();
  const positionFlag =
    input.positionDetected === true ||
    input.positionDetected === 1 ||
    Number(input.positionDetected) === 1;

  if (PROFILE_CODES.has(err) || err === 'PACKAGE_EXPORT_OFFLINE_CONFIG_REQUIRED') {
    return 'profile_resolution_error';
  }
  if (err.includes('RECOGNITION_CONFIG') || err.includes('PROFILE_MISSING')) {
    return 'profile_resolution_error';
  }

  // Position success / duplicate — exact codes from localCodeScanStrategy + export readiness.
  if (err === 'POSITION_LABEL_DUPLICATE') {
    return 'position_duplicate';
  }
  if (err === 'POSITION_LABEL_DETECTED' || (positionFlag && !err)) {
    return 'position_detected';
  }
  if (positionFlag && (status === 'RESOLVED' || status === 'UNRESOLVED' || status === 'DETECTED_UNVERIFIED')) {
    // Position applied even if products unresolved on same photo.
    if (!err || err === 'POSITION_LABEL_DETECTED') {
      return 'position_detected';
    }
  }

  if (validation === 'DUPLICATE_LABEL') {
    return 'decoded_duplicate';
  }
  // ITEM duplicate: exact validation or known product duplicate codes only (not broad includes).
  if (err === 'DUPLICATE_LABEL' || err === 'PRODUCT_LABEL_DUPLICATE') {
    return 'decoded_duplicate';
  }

  if (INVALID_FORMAT_CODES.has(err) || err === 'INVALID') {
    return 'decoded_invalid_format';
  }

  if (NOT_DETECTED_CODES.has(err) || status === 'NO_DETECTIONS') {
    return 'not_detected';
  }

  if (PERSIST_CODES.has(err) || err.startsWith('SQLITE_')) {
    return 'persistence_error';
  }

  if (TECHNICAL_CODES.has(err) || status === 'FAILED' || status === 'FAILED_RETRYABLE' || status === 'ERROR') {
    return 'scanner_technical_error';
  }

  if (status === 'RESOLVED' || status === 'READY' || status === 'CONFIRMED' || status === 'DETECTED_UNVERIFIED') {
    return 'decoded_accepted';
  }

  if (!err && (status === '' || status === 'PENDING' || status === 'SCANNING')) {
    return 'unknown';
  }

  if (err) {
    // Unknown non-empty code: do not blanket as technical if position flag set.
    if (positionFlag) {
      return 'position_detected';
    }
    return 'scanner_technical_error';
  }
  return 'unknown';
}

export function outcomeIsSuccess(outcome: BenchmarkPhotoOutcome): boolean {
  return (
    outcome === 'decoded_accepted' ||
    outcome === 'decoded_duplicate' ||
    outcome === 'position_detected' ||
    outcome === 'position_duplicate'
  );
}
