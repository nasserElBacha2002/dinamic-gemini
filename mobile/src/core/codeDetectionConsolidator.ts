/**
 * Collapse barcode detections from one image into 0..N physical product labels
 * plus an optional co-located POSITION label (same photo).
 *
 * D1 labels dedupe by label_id. Legacy PIPE/DI1 keeps ≤1 semantics when no D1 present.
 * Known D1 (even invalid) blocks legacy fallback for that image's product path.
 */

import {
  parseEncodedLabelPayload,
  type PayloadParseResult,
  QUANTITY_MAX_DEFAULT,
} from './labelPayload';
import {
  parseProductLabelPayload,
  type ParsedProductLabelPayload,
} from './productLabelFormat';
import type { ProductLabelRejection } from './productLabelRejection';
import { parseDinamicPositionPayload } from './positionLabelPayload';

export type ConsolidationStatus =
  | 'NO_DETECTIONS'
  | 'NO_VALID_CODE'
  | 'RESOLVED'
  | 'RESOLVED_MULTI'
  | 'MISSING_QUANTITY'
  | 'QUANTITY_CONFLICT'
  | 'MULTIPLE_DISTINCT_CODES';

export interface DetectedCodeCandidate {
  readonly rawValue: string;
  readonly symbology: string;
  readonly detectionIndex?: number;
  /** Optional ML Kit bounding box as "l,t,w,h" (diagnostics only). */
  readonly boundingBox?: string | null;
}

export interface ProductLabelResult {
  readonly labelId: string;
  readonly internalCode: string;
  readonly quantity: number;
  readonly formatVersion: string;
  readonly checksum: string;
  readonly validationStatus: string;
  readonly selectedIndex: number;
  readonly duplicateDetectionCount: number;
  readonly rawPayload: string;
  readonly normalizedPayload: string | null;
}

export interface ConsolidationResult {
  readonly status: ConsolidationStatus;
  readonly internalCode: string | null;
  readonly quantity: number | null;
  readonly selectedIndex: number | null;
  readonly distinctCodes: readonly string[];
  readonly warnings: readonly string[];
  readonly parsed: PayloadParseResult | null;
  readonly productResults: readonly ProductLabelResult[];
  readonly rejections: readonly ProductLabelRejection[];
  /** True when any D1-shaped candidate was seen (blocks legacy revival). */
  readonly d1Mode: boolean;
  /** Exact ML Kit raw string for a co-located DINAMIC_POSITION QR, if any. */
  readonly positionRawPayload: string | null;
}

function findPositionRawPayload(
  candidates: readonly { readonly rawValue: string }[],
): string | null {
  for (const c of candidates) {
    if (parseDinamicPositionPayload(c.rawValue)) {
      return c.rawValue;
    }
  }
  return null;
}

function emptyResult(
  overrides: Partial<ConsolidationResult> &
    Pick<ConsolidationResult, 'status' | 'positionRawPayload'>,
): ConsolidationResult {
  return {
    internalCode: null,
    quantity: null,
    selectedIndex: null,
    distinctCodes: [],
    warnings: [],
    parsed: null,
    productResults: [],
    rejections: [],
    d1Mode: false,
    ...overrides,
  };
}

function rejectionFromD1(
  det: { rawValue: string; detectionIndex: number },
  parsed: ParsedProductLabelPayload,
): ProductLabelRejection {
  const mapped =
    parsed.status === 'CHECKSUM_FAILED'
      ? 'D1_CHECKSUM_FAILED'
      : parsed.status === 'MALFORMED'
        ? 'D1_MALFORMED'
        : parsed.status === 'UNKNOWN_VERSION'
          ? 'UNKNOWN_VERSION'
          : parsed.status;
  return {
    labelId: parsed.labelId,
    validationStatus: mapped,
    reason: parsed.detail ?? mapped,
    detectionIndex: det.detectionIndex,
    rawValuePreview: det.rawValue.slice(0, 48),
  };
}

export function consolidateCodeDetections(
  candidates: readonly DetectedCodeCandidate[],
  options?: { readonly quantityMax?: number },
): ConsolidationResult {
  if (candidates.length === 0) {
    return emptyResult({ status: 'NO_DETECTIONS', positionRawPayload: null });
  }

  const quantityMax = options?.quantityMax ?? QUANTITY_MAX_DEFAULT;
  const enriched = candidates.map((c, i) => ({
    ...c,
    detectionIndex: c.detectionIndex ?? i,
    d1: parseProductLabelPayload(c.rawValue),
    parsed: parseEncodedLabelPayload(c.rawValue, { quantityMax }),
  }));

  const positionRawPayload = findPositionRawPayload(enriched);

  const d1ByLabel = new Map<
    string,
    { det: (typeof enriched)[number]; parsed: ParsedProductLabelPayload }[]
  >();
  const rejections: ProductLabelRejection[] = [];
  let hasD1Attempt = false;

  for (const det of enriched) {
    if (det.d1.status === 'NOT_OUR_FORMAT') continue;
    hasD1Attempt = true;
    if (det.d1.status === 'VALID' && det.d1.labelId && det.d1.internalCode && det.d1.quantity) {
      const list = d1ByLabel.get(det.d1.labelId) ?? [];
      list.push({ det, parsed: det.d1 });
      d1ByLabel.set(det.d1.labelId, list);
    } else {
      rejections.push(rejectionFromD1(det, det.d1));
    }
  }

  if (d1ByLabel.size > 0) {
    const products: ProductLabelResult[] = [];
    for (const [labelId, group] of d1ByLabel) {
      const codes = new Set(group.map((g) => g.parsed.internalCode));
      const qtys = new Set(group.map((g) => g.parsed.quantity));
      if (codes.size > 1 || qtys.size > 1) {
        rejections.push({
          labelId,
          validationStatus: 'QUANTITY_CONFLICT',
          reason: 'conflicting_code_or_qty_for_label',
          detectionIndex: group[0]!.det.detectionIndex,
          rawValuePreview: group[0]!.det.rawValue.slice(0, 48),
        });
        continue;
      }
      const first = group[0]!;
      products.push({
        labelId,
        internalCode: first.parsed.internalCode!,
        quantity: first.parsed.quantity!,
        formatVersion: first.parsed.formatVersion ?? 'D1',
        checksum: first.parsed.checksumReceived ?? '',
        validationStatus: 'D1_VALID',
        selectedIndex: first.det.detectionIndex,
        duplicateDetectionCount: group.length,
        rawPayload: first.det.rawValue,
        normalizedPayload: first.parsed.normalizedPayload,
      });
    }
    if (products.length === 0) {
      const warnings = ['NO_VALID_D1_PRODUCT_LABEL', 'D1_CANDIDATES_FAILED'];
      if (positionRawPayload) warnings.push('POSITION_LABEL_DETECTED');
      return emptyResult({
        status: 'NO_VALID_CODE',
        warnings,
        rejections,
        d1Mode: true,
        positionRawPayload,
        parsed: null,
      });
    }
    const primary = products[0]!;
    const warnings: string[] = [];
    if (products.length > 1) warnings.push('MULTI_PRODUCT_IMAGE');
    if (positionRawPayload) warnings.push('POSITION_LABEL_DETECTED');
    if (rejections.length > 0) warnings.push('D1_PARTIAL_REJECTIONS');
    return {
      status: products.length > 1 ? 'RESOLVED_MULTI' : 'RESOLVED',
      internalCode: primary.internalCode,
      quantity: primary.quantity,
      selectedIndex: primary.selectedIndex,
      distinctCodes: products.map((p) => p.internalCode),
      warnings,
      parsed: null,
      productResults: products,
      rejections,
      d1Mode: true,
      positionRawPayload,
    };
  }

  // Known Dinamic D1 attempt(s) failed → never revive via legacy barcode.
  if (hasD1Attempt) {
    const warnings = ['D1_CANDIDATES_FAILED'];
    if (positionRawPayload) warnings.push('POSITION_LABEL_DETECTED');
    return emptyResult({
      status: 'NO_VALID_CODE',
      warnings,
      rejections,
      d1Mode: true,
      positionRawPayload,
    });
  }

  // Legacy ≤1 path (true legacy stickers with no D1 QR).
  const withCode = enriched.filter((d) => d.parsed.status === 'VALID' && d.parsed.internalCode);
  if (withCode.length === 0) {
    const warnings = positionRawPayload
      ? (['POSITION_LABEL_DETECTED'] as const)
      : (['NO_VALID_CODE'] as const);
    return emptyResult({
      status: 'NO_VALID_CODE',
      warnings: [...warnings],
      rejections,
      d1Mode: false,
      positionRawPayload,
      selectedIndex: positionRawPayload
        ? enriched.find((d) => d.rawValue === positionRawPayload)?.detectionIndex ?? null
        : null,
      parsed: enriched[0]?.parsed ?? null,
    });
  }

  const grouped = new Map<string, typeof withCode>();
  for (const det of withCode) {
    const code = det.parsed.status === 'VALID' ? det.parsed.internalCode : null;
    if (!code) continue;
    const list = grouped.get(code) ?? [];
    list.push(det);
    grouped.set(code, list);
  }

  const distinctCodes = [...grouped.keys()];
  if (distinctCodes.length > 1) {
    return emptyResult({
      status: 'MULTIPLE_DISTINCT_CODES',
      distinctCodes,
      warnings: ['MULTIPLE_DISTINCT_CODES', 'LEGACY_NO_LABEL_ID'],
      parsed: withCode[0]?.parsed ?? null,
      rejections,
      d1Mode: false,
      positionRawPayload,
    });
  }

  const code = distinctCodes[0]!;
  const group = grouped.get(code)!;
  const quantities = new Set(
    group
      .map((d) => (d.parsed.status === 'VALID' ? d.parsed.quantity : null))
      .filter((q): q is number => q != null),
  );

  if (quantities.size > 1) {
    return emptyResult({
      status: 'QUANTITY_CONFLICT',
      internalCode: code,
      distinctCodes,
      warnings: ['QUANTITY_CONFLICT'],
      parsed: group[0]?.parsed ?? null,
      rejections,
      d1Mode: false,
      positionRawPayload,
    });
  }

  if (quantities.size === 0) {
    return emptyResult({
      status: 'MISSING_QUANTITY',
      internalCode: code,
      selectedIndex: group[0]?.detectionIndex ?? null,
      distinctCodes,
      warnings: ['QUANTITY_MISSING'],
      parsed: group[0]?.parsed ?? null,
      rejections,
      d1Mode: false,
      positionRawPayload,
    });
  }

  const quantity = [...quantities][0]!;
  const selected =
    group.find((d) => d.parsed.status === 'VALID' && d.parsed.quantity === quantity) ?? group[0]!;
  const warnings = positionRawPayload
    ? ['POSITION_LABEL_DETECTED', 'LEGACY_ONLY']
    : ['LEGACY_ONLY'];
  return {
    status: 'RESOLVED',
    internalCode: code,
    quantity,
    selectedIndex: selected.detectionIndex,
    distinctCodes,
    warnings,
    parsed: selected.parsed,
    productResults: [],
    rejections,
    d1Mode: false,
    positionRawPayload,
  };
}
