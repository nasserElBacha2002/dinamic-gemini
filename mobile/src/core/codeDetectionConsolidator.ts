/**
 * Collapse barcode detections from one image into 0..N physical product labels.
 * D1 labels dedupe by label_id. Legacy PIPE/DI1 keeps ≤1 semantics when no D1 present.
 */

import {
  extractDinamicPositionCode,
  parseEncodedLabelPayload,
  type PayloadParseResult,
  QUANTITY_MAX_DEFAULT,
} from './labelPayload';
import {
  parseProductLabelPayload,
  type ParsedProductLabelPayload,
} from './productLabelFormat';

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
  readonly rejections: readonly {
    readonly validationStatus: string;
    readonly rawValue: string;
    readonly detectionIndex: number;
    readonly labelId: string | null;
  }[];
}

export function consolidateCodeDetections(
  candidates: readonly DetectedCodeCandidate[],
  options?: { readonly quantityMax?: number },
): ConsolidationResult {
  if (candidates.length === 0) {
    return {
      status: 'NO_DETECTIONS',
      internalCode: null,
      quantity: null,
      selectedIndex: null,
      distinctCodes: [],
      warnings: [],
      parsed: null,
      productResults: [],
      rejections: [],
    };
  }

  const quantityMax = options?.quantityMax ?? QUANTITY_MAX_DEFAULT;
  const enriched = candidates.map((c, i) => ({
    ...c,
    detectionIndex: c.detectionIndex ?? i,
    d1: parseProductLabelPayload(c.rawValue),
    parsed: parseEncodedLabelPayload(c.rawValue, { quantityMax }),
  }));

  const d1ByLabel = new Map<
    string,
    { det: (typeof enriched)[number]; parsed: ParsedProductLabelPayload }[]
  >();
  const rejections: Array<{
    validationStatus: string;
    rawValue: string;
    detectionIndex: number;
    labelId: string | null;
  }> = [];
  let hasD1Attempt = false;

  for (const det of enriched) {
    if (det.d1.status === 'NOT_OUR_FORMAT') continue;
    hasD1Attempt = true;
    if (det.d1.status === 'VALID' && det.d1.labelId && det.d1.internalCode && det.d1.quantity) {
      const list = d1ByLabel.get(det.d1.labelId) ?? [];
      list.push({ det, parsed: det.d1 });
      d1ByLabel.set(det.d1.labelId, list);
    } else {
      rejections.push({
        validationStatus: det.d1.status,
        rawValue: det.rawValue,
        detectionIndex: det.detectionIndex,
        labelId: det.d1.labelId,
      });
    }
  }

  if (d1ByLabel.size > 0) {
    const products: ProductLabelResult[] = [];
    for (const [labelId, group] of d1ByLabel) {
      const codes = new Set(group.map((g) => g.parsed.internalCode));
      const qtys = new Set(group.map((g) => g.parsed.quantity));
      if (codes.size > 1 || qtys.size > 1) {
        rejections.push({
          validationStatus: 'QUANTITY_CONFLICT',
          rawValue: group[0]!.det.rawValue,
          detectionIndex: group[0]!.det.detectionIndex,
          labelId,
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
        validationStatus: 'VALID',
        selectedIndex: first.det.detectionIndex,
        duplicateDetectionCount: group.length,
        rawPayload: first.det.rawValue,
        normalizedPayload: first.parsed.normalizedPayload,
      });
    }
    if (products.length === 0) {
      return {
        status: 'NO_VALID_CODE',
        internalCode: null,
        quantity: null,
        selectedIndex: null,
        distinctCodes: [],
        warnings: ['NO_VALID_D1_PRODUCT_LABEL'],
        parsed: null,
        productResults: [],
        rejections,
      };
    }
    const primary = products[0]!;
    return {
      status: products.length > 1 ? 'RESOLVED_MULTI' : 'RESOLVED',
      internalCode: primary.internalCode,
      quantity: primary.quantity,
      selectedIndex: primary.selectedIndex,
      distinctCodes: products.map((p) => p.internalCode),
      warnings: products.length > 1 ? ['MULTI_PRODUCT_IMAGE'] : [],
      parsed: null,
      productResults: products,
      rejections,
    };
  }

  if (hasD1Attempt && rejections.length > 0) {
    return {
      status: 'NO_VALID_CODE',
      internalCode: null,
      quantity: null,
      selectedIndex: null,
      distinctCodes: [],
      warnings: ['D1_CANDIDATES_FAILED'],
      parsed: null,
      productResults: [],
      rejections,
    };
  }

  // Legacy ≤1 path
  const withCode = enriched.filter((d) => d.parsed.status === 'VALID' && d.parsed.internalCode);
  if (withCode.length === 0) {
    const positionLabel = enriched.find(
      (d) =>
        d.parsed.status === 'INVALID' && d.parsed.errorCode === 'POSITION_LABEL_DETECTED',
    );
    const positionCode = positionLabel
      ? extractDinamicPositionCode(positionLabel.rawValue)
      : null;
    return {
      status: 'NO_VALID_CODE',
      internalCode: positionCode,
      quantity: null,
      selectedIndex: positionLabel?.detectionIndex ?? null,
      distinctCodes: [],
      warnings: positionLabel ? ['POSITION_LABEL_DETECTED'] : ['NO_VALID_CODE'],
      parsed: positionLabel?.parsed ?? enriched[0]?.parsed ?? null,
      productResults: [],
      rejections,
    };
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
    return {
      status: 'MULTIPLE_DISTINCT_CODES',
      internalCode: null,
      quantity: null,
      selectedIndex: null,
      distinctCodes,
      warnings: ['MULTIPLE_DISTINCT_CODES', 'LEGACY_NO_LABEL_ID'],
      parsed: withCode[0]?.parsed ?? null,
      productResults: [],
      rejections,
    };
  }

  const code = distinctCodes[0]!;
  const group = grouped.get(code)!;
  const quantities = new Set(
    group
      .map((d) => (d.parsed.status === 'VALID' ? d.parsed.quantity : null))
      .filter((q): q is number => q != null),
  );

  if (quantities.size > 1) {
    return {
      status: 'QUANTITY_CONFLICT',
      internalCode: code,
      quantity: null,
      selectedIndex: null,
      distinctCodes,
      warnings: ['QUANTITY_CONFLICT'],
      parsed: group[0]?.parsed ?? null,
      productResults: [],
      rejections,
    };
  }

  if (quantities.size === 0) {
    return {
      status: 'MISSING_QUANTITY',
      internalCode: code,
      quantity: null,
      selectedIndex: group[0]?.detectionIndex ?? null,
      distinctCodes,
      warnings: ['QUANTITY_MISSING'],
      parsed: group[0]?.parsed ?? null,
      productResults: [],
      rejections,
    };
  }

  const quantity = [...quantities][0]!;
  const selected =
    group.find((d) => d.parsed.status === 'VALID' && d.parsed.quantity === quantity) ?? group[0]!;
  return {
    status: 'RESOLVED',
    internalCode: code,
    quantity,
    selectedIndex: selected.detectionIndex,
    distinctCodes,
    warnings: [],
    parsed: selected.parsed,
    productResults: [],
    rejections,
  };
}
