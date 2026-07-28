/**
 * Collapse multiple barcode detections from one image into at most one logical label.
 * Mirrors backend CodeDetectionConsolidator.
 */

import {
  parseEncodedLabelPayload,
  type PayloadParseResult,
  QUANTITY_MAX_DEFAULT,
} from './labelPayload';

export type ConsolidationStatus =
  | 'NO_DETECTIONS'
  | 'NO_VALID_CODE'
  | 'RESOLVED'
  | 'MISSING_QUANTITY'
  | 'QUANTITY_CONFLICT'
  | 'MULTIPLE_DISTINCT_CODES';

export interface DetectedCodeCandidate {
  readonly rawValue: string;
  readonly symbology: string;
  readonly detectionIndex?: number;
}

export interface ConsolidationResult {
  readonly status: ConsolidationStatus;
  readonly internalCode: string | null;
  readonly quantity: number | null;
  readonly selectedIndex: number | null;
  readonly distinctCodes: readonly string[];
  readonly warnings: readonly string[];
  readonly parsed: PayloadParseResult | null;
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
    };
  }

  const quantityMax = options?.quantityMax ?? QUANTITY_MAX_DEFAULT;
  const enriched = candidates.map((c, i) => ({
    ...c,
    detectionIndex: c.detectionIndex ?? i,
    parsed: parseEncodedLabelPayload(c.rawValue, { quantityMax }),
  }));

  const withCode = enriched.filter((d) => d.parsed.status === 'VALID' && d.parsed.internalCode);
  if (withCode.length === 0) {
    return {
      status: 'NO_VALID_CODE',
      internalCode: null,
      quantity: null,
      selectedIndex: null,
      distinctCodes: [],
      warnings: ['NO_VALID_CODE'],
      parsed: enriched[0]?.parsed ?? null,
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
      warnings: ['MULTIPLE_DISTINCT_CODES'],
      parsed: withCode[0]?.parsed ?? null,
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
  };
}
