/**
 * Detection vs domain correctness + absolute/regression gates for Phase 4.
 * Extends (does not replace) classifyPhotoCorrectness for backward-compatible tests.
 */

import type { BenchmarkManifestScenarioKind } from './benchmarkFixtureOrder';
import {
  classifyPhotoCorrectness,
  parseItemPayload,
  parseLabelsJson,
  type CorrectnessResultCode,
  type CorrectnessRegressionGateResult,
  type CorrectnessRow,
  type CorrectnessSummary,
  summarizeCorrectness,
  diffCorrectnessRuns,
  evaluateCorrectnessRegressionGate,
} from './benchmarkCorrectness';

export type DetectionResultCode =
  | 'DETECTION_EXACT_MATCH'
  | 'DETECTION_PARTIAL'
  | 'DETECTION_FALSE_NEGATIVE'
  | 'DETECTION_UNEXPECTED_EXTRA'
  | 'DETECTION_PIPELINE_ERROR';

export type DomainResultCode =
  | 'DOMAIN_EXACT_MATCH'
  | 'CORRECT_REJECTION'
  | 'FALSE_POSITIVE'
  | 'FALSE_NEGATIVE'
  | 'WRONG_POSITION'
  | 'WRONG_ITEM'
  | 'WRONG_QUANTITY'
  | 'PARTIAL_MATCH'
  | 'AMBIGUOUS_EXPECTED'
  | 'AMBIGUOUS_CORRECT'
  | 'AMBIGUOUS_INCORRECT'
  | 'PIPELINE_ERROR';

export type ExpectedDomainOutcome =
  | 'POSITION_APPLIED'
  | 'ITEM_APPLIED'
  | 'AMBIGUOUS'
  | 'CORRECT_REJECTION'
  | 'MIXED_KEEP_VALID_REJECT_FALSE'
  | 'UNKNOWN';

export interface AbsoluteCorrectnessGateConfig {
  readonly minSinglePositionAccuracy: number;
  readonly minSingleItemAccuracy: number;
  readonly minFalseOnlyRejectionAccuracy: number;
  readonly minOverallDomainExactAccuracy: number;
  readonly minOverallDetectionExactAccuracy: number;
}

export const DEFAULT_ABSOLUTE_CORRECTNESS_GATE: AbsoluteCorrectnessGateConfig = {
  minSinglePositionAccuracy: 0.98,
  minSingleItemAccuracy: 0.98,
  minFalseOnlyRejectionAccuracy: 0.98,
  minOverallDomainExactAccuracy: 0.95,
  minOverallDetectionExactAccuracy: 0.95,
};

export function expectedDomainOutcomeForScenario(
  scenarioKind: BenchmarkManifestScenarioKind,
  expectedValidCount: number,
  labelsJson?: string | null,
): ExpectedDomainOutcome {
  switch (scenarioKind) {
    case 'position':
      return 'POSITION_APPLIED';
    case 'item':
      return 'ITEM_APPLIED';
    case 'multi_true': {
      // Andes multi_true in this dataset is often POSITION+ITEM (apply both), not
      // two ITEMs. Ambiguity applies when ≥2 distinct codes of the *same* kind.
      const labels = parseLabelsJson(labelsJson ?? undefined).filter((l) => l.validAndes);
      const positions = labels.filter((l) => l.kind.toLowerCase().includes('position'));
      const items = labels.filter((l) => !l.kind.toLowerCase().includes('position'));
      if (positions.length >= 2 || items.length >= 2) {
        return 'AMBIGUOUS';
      }
      if (positions.length === 1 && items.length === 1) {
        // Position + single item is a valid combined Andes outcome.
        return 'ITEM_APPLIED';
      }
      return expectedValidCount > 1 ? 'AMBIGUOUS' : 'ITEM_APPLIED';
    }
    case 'multi_mixed': {
      const labels = parseLabelsJson(labelsJson ?? undefined).filter((l) => l.validAndes);
      const positions = labels.filter((l) => l.kind.toLowerCase().includes('position'));
      const items = labels.filter((l) => !l.kind.toLowerCase().includes('position'));
      if (positions.length >= 2 || items.length >= 2) {
        return 'AMBIGUOUS';
      }
      return expectedValidCount > 1 ? 'AMBIGUOUS' : 'MIXED_KEEP_VALID_REJECT_FALSE';
    }
    case 'multi_false':
      return 'CORRECT_REJECTION';
    default:
      return 'UNKNOWN';
  }
}

function setEq(a: ReadonlySet<string>, b: ReadonlySet<string>): boolean {
  if (a.size !== b.size) return false;
  for (const x of a) if (!b.has(x)) return false;
  return true;
}

export function classifyDetectionCorrectness(input: {
  readonly expectedPhysicalPayloads: readonly string[];
  readonly actualRawDetectedPayloads: readonly string[];
  readonly pipelineError?: string | null;
}): { readonly result: DetectionResultCode; readonly detail?: string } {
  if (input.pipelineError) {
    return { result: 'DETECTION_PIPELINE_ERROR', detail: String(input.pipelineError) };
  }
  const expected = new Set(input.expectedPhysicalPayloads.map((p) => p.trim()).filter(Boolean));
  const actual = new Set(input.actualRawDetectedPayloads.map((p) => p.trim()).filter(Boolean));
  if (setEq(expected, actual)) return { result: 'DETECTION_EXACT_MATCH' };
  const missing = [...expected].filter((p) => !actual.has(p));
  const extra = [...actual].filter((p) => !expected.has(p));
  if (missing.length && actual.size === 0) {
    return { result: 'DETECTION_FALSE_NEGATIVE', detail: missing.join('|') };
  }
  if (extra.length && missing.length === 0) {
    return { result: 'DETECTION_UNEXPECTED_EXTRA', detail: extra.join('|') };
  }
  if (missing.length) {
    return { result: 'DETECTION_PARTIAL', detail: `missing=${missing.join('|')};extra=${extra.join('|')}` };
  }
  return { result: 'DETECTION_UNEXPECTED_EXTRA', detail: extra.join('|') };
}

export function classifyDomainCorrectness(input: {
  readonly scenarioKind: BenchmarkManifestScenarioKind;
  readonly expectedOutcome: ExpectedDomainOutcome;
  readonly draftStatus: string | null | undefined;
  readonly errorCode: string | null | undefined;
  readonly expectedValidPayloads: readonly string[];
  readonly expectedFalsePayloads: readonly string[];
  readonly actualAcceptedPayloads: readonly string[];
  readonly actualRejectedPayloads: readonly string[];
  readonly expectedPosition: string | null;
  readonly actualPosition: string | null;
  readonly expectedItems: readonly { code: string; qty: number | null }[];
  readonly actualItems: readonly { code: string; qty: number | null }[];
  readonly pipelineError?: string | null;
}): { readonly result: DomainResultCode; readonly detail?: string } {
  if (input.pipelineError) {
    return { result: 'PIPELINE_ERROR', detail: String(input.pipelineError) };
  }

  const status = (input.draftStatus ?? '').toUpperCase();
  const err = (input.errorCode ?? '').toUpperCase();
  const accepted = new Set(input.actualAcceptedPayloads.map((p) => p.trim()).filter(Boolean));
  const falseAccepted = [...accepted].filter((p) =>
    input.expectedFalsePayloads.map((x) => x.trim()).includes(p),
  );

  if (falseAccepted.length) {
    return { result: 'FALSE_POSITIVE', detail: falseAccepted.join('|') };
  }

  if (input.expectedOutcome === 'AMBIGUOUS') {
    const isAmb =
      status === 'AMBIGUOUS' ||
      err === 'MULTIPLE_DISTINCT_CODES' ||
      err === 'AMBIGUOUS_LABEL_KIND';
    if (isAmb) return { result: 'AMBIGUOUS_CORRECT' };
    return {
      result: 'AMBIGUOUS_INCORRECT',
      detail: `status=${status||'null'};error=${err||'null'}`,
    };
  }

  if (input.expectedOutcome === 'CORRECT_REJECTION') {
    if (accepted.size === 0 && !input.actualPosition) {
      return { result: 'CORRECT_REJECTION' };
    }
    return { result: 'FALSE_POSITIVE', detail: [...accepted].join('|') || input.actualPosition || '' };
  }

  // Position + single item (Andes multi_true): domain applies both; draft may store
  // position separately from the accepted item product result.
  if (
    input.expectedOutcome === 'ITEM_APPLIED' &&
    input.expectedPosition &&
    input.expectedItems.length === 1
  ) {
    const expectedItem = input.expectedItems[0]!;
    const actualItem =
      input.actualItems[0] ??
      (input.actualAcceptedPayloads.find((p) => p.includes('|'))
        ? parseItemPayload(input.actualAcceptedPayloads.find((p) => p.includes('|'))!)
        : null);
    const posOk =
      !input.expectedPosition ||
      input.actualPosition === input.expectedPosition ||
      accepted.has(input.expectedPosition);
    if (!actualItem || !actualItem.code) {
      return { result: 'FALSE_NEGATIVE', detail: 'missing_actual_item' };
    }
    if (actualItem.code !== expectedItem.code) {
      return { result: 'WRONG_ITEM', detail: `${actualItem.code}!=${expectedItem.code}` };
    }
    if (expectedItem.qty != null && actualItem.qty !== expectedItem.qty) {
      return {
        result: 'WRONG_QUANTITY',
        detail: `${String(actualItem.qty)}!=${String(expectedItem.qty)}`,
      };
    }
    // Position may be session-applied without remaining in accepted payloads.
    if (!posOk && input.actualPosition && input.actualPosition !== input.expectedPosition) {
      return {
        result: 'WRONG_POSITION',
        detail: `${input.actualPosition}!=${input.expectedPosition}`,
      };
    }
    return { result: 'DOMAIN_EXACT_MATCH' };
  }

  // Reuse legacy classifier for single-label / mixed keep-valid paths.
  const legacy = classifyPhotoCorrectness({
    scenarioKind: input.scenarioKind,
    expectedValidPayloads: input.expectedValidPayloads,
    expectedFalsePayloads: input.expectedFalsePayloads,
    actualAcceptedPayloads: input.actualAcceptedPayloads,
    actualRejectedPayloads: input.actualRejectedPayloads,
    expectedPosition: input.expectedPosition,
    actualPosition: input.actualPosition,
    expectedItems: input.expectedItems,
    actualItems: input.actualItems,
    pipelineError: null,
  });

  const map: Record<CorrectnessResultCode, DomainResultCode> = {
    EXACT_MATCH: 'DOMAIN_EXACT_MATCH',
    CORRECT_REJECTION: 'CORRECT_REJECTION',
    PARTIAL_MATCH: 'PARTIAL_MATCH',
    FALSE_POSITIVE: 'FALSE_POSITIVE',
    FALSE_NEGATIVE: 'FALSE_NEGATIVE',
    UNEXPECTED_EXTRA_LABEL: 'FALSE_POSITIVE',
    WRONG_POSITION: 'WRONG_POSITION',
    WRONG_ITEM: 'WRONG_ITEM',
    WRONG_QUANTITY: 'WRONG_QUANTITY',
    PIPELINE_ERROR: 'PIPELINE_ERROR',
  };
  return {
    result: map[legacy.result],
    ...(legacy.detail != null ? { detail: legacy.detail } : {}),
  };
}

export interface DualCorrectnessRow {
  readonly benchmarkSequence: number;
  readonly originalSequence: number;
  readonly filename: string;
  readonly scenarioKind: BenchmarkManifestScenarioKind;
  readonly expectedValidPayloads: readonly string[];
  readonly expectedFalsePayloads: readonly string[];
  readonly actualRawDetectedPayloads: readonly string[];
  readonly actualAcceptedPayloads: readonly string[];
  readonly actualRejectedPayloads: readonly string[];
  readonly expectedPosition: string | null;
  readonly actualPosition: string | null;
  readonly expectedItems: string;
  readonly actualItems: string;
  readonly detectionResult: DetectionResultCode;
  readonly domainResult: DomainResultCode;
  readonly expectedDomainOutcome: ExpectedDomainOutcome;
  readonly pipelineError: string | null;
  readonly scannerProcessingMs: number | null;
  readonly detectionDetail?: string;
  readonly domainDetail?: string;
}

export interface DualCorrectnessSummary {
  readonly totalPhotos: number;
  readonly detectionExact: number;
  readonly detectionPartial: number;
  readonly detectionFalseNegative: number;
  readonly detectionUnexpectedExtra: number;
  readonly detectionExactAccuracy: number;
  readonly detectionRecall: number;
  readonly domainExact: number;
  readonly correctRejections: number;
  readonly falsePositives: number;
  readonly falseNegatives: number;
  readonly wrongPosition: number;
  readonly wrongItem: number;
  readonly wrongQuantity: number;
  readonly ambiguousExpected: number;
  readonly ambiguousCorrect: number;
  readonly pipelineErrors: number;
  readonly domainExactAccuracy: number;
  readonly byScenario: Readonly<
    Record<
      string,
      {
        readonly total: number;
        readonly detectionExact: number;
        readonly domainExact: number;
        readonly correctRejections: number;
      }
    >
  >;
}

export function summarizeDualCorrectness(
  rows: readonly DualCorrectnessRow[],
): DualCorrectnessSummary {
  const byScenario: Record<
    string,
    { total: number; detectionExact: number; domainExact: number; correctRejections: number }
  > = {};
  let detectionExact = 0;
  let detectionPartial = 0;
  let detectionFalseNegative = 0;
  let detectionUnexpectedExtra = 0;
  let domainExact = 0;
  let correctRejections = 0;
  let falsePositives = 0;
  let falseNegatives = 0;
  let wrongPosition = 0;
  let wrongItem = 0;
  let wrongQuantity = 0;
  let ambiguousExpected = 0;
  let ambiguousCorrect = 0;
  let pipelineErrors = 0;
  let expectedPhysical = 0;
  let foundPhysical = 0;

  for (const row of rows) {
    const sk = row.scenarioKind;
    if (!byScenario[sk]) {
      byScenario[sk] = { total: 0, detectionExact: 0, domainExact: 0, correctRejections: 0 };
    }
    byScenario[sk]!.total += 1;

    expectedPhysical += row.expectedValidPayloads.length + row.expectedFalsePayloads.length;
    const rawSet = new Set(row.actualRawDetectedPayloads);
    for (const p of [...row.expectedValidPayloads, ...row.expectedFalsePayloads]) {
      if (rawSet.has(p)) foundPhysical += 1;
    }

    if (row.detectionResult === 'DETECTION_EXACT_MATCH') {
      detectionExact += 1;
      byScenario[sk]!.detectionExact += 1;
    } else if (row.detectionResult === 'DETECTION_PARTIAL') detectionPartial += 1;
    else if (row.detectionResult === 'DETECTION_FALSE_NEGATIVE') detectionFalseNegative += 1;
    else if (row.detectionResult === 'DETECTION_UNEXPECTED_EXTRA') detectionUnexpectedExtra += 1;

    if (row.expectedDomainOutcome === 'AMBIGUOUS') ambiguousExpected += 1;
    if (row.domainResult === 'AMBIGUOUS_CORRECT') ambiguousCorrect += 1;

    if (
      row.domainResult === 'DOMAIN_EXACT_MATCH' ||
      row.domainResult === 'AMBIGUOUS_CORRECT' ||
      row.domainResult === 'CORRECT_REJECTION'
    ) {
      domainExact += 1;
      byScenario[sk]!.domainExact += 1;
      if (row.domainResult === 'CORRECT_REJECTION') {
        correctRejections += 1;
        byScenario[sk]!.correctRejections += 1;
      }
    } else if (row.domainResult === 'FALSE_POSITIVE') falsePositives += 1;
    else if (row.domainResult === 'FALSE_NEGATIVE') falseNegatives += 1;
    else if (row.domainResult === 'WRONG_POSITION') wrongPosition += 1;
    else if (row.domainResult === 'WRONG_ITEM') wrongItem += 1;
    else if (row.domainResult === 'WRONG_QUANTITY') wrongQuantity += 1;
    else if (row.domainResult === 'PIPELINE_ERROR') pipelineErrors += 1;
  }

  const n = rows.length || 1;
  return {
    totalPhotos: rows.length,
    detectionExact,
    detectionPartial,
    detectionFalseNegative,
    detectionUnexpectedExtra,
    detectionExactAccuracy: detectionExact / n,
    detectionRecall: expectedPhysical > 0 ? foundPhysical / expectedPhysical : 1,
    domainExact,
    correctRejections,
    falsePositives,
    falseNegatives,
    wrongPosition,
    wrongItem,
    wrongQuantity,
    ambiguousExpected,
    ambiguousCorrect,
    pipelineErrors,
    domainExactAccuracy: domainExact / n,
    byScenario,
  };
}

export function evaluateAbsoluteCorrectnessGate(
  summary: DualCorrectnessSummary,
  config: AbsoluteCorrectnessGateConfig = DEFAULT_ABSOLUTE_CORRECTNESS_GATE,
): CorrectnessRegressionGateResult {
  const failures: string[] = [];
  const pos = summary.byScenario.position;
  const item = summary.byScenario.item;
  const multiFalse = summary.byScenario.multi_false;

  if (pos && pos.total > 0) {
    const acc = pos.domainExact / pos.total;
    if (acc + 1e-9 < config.minSinglePositionAccuracy) {
      failures.push(`single_position_accuracy ${acc} < ${config.minSinglePositionAccuracy}`);
    }
  }
  if (item && item.total > 0) {
    const acc = item.domainExact / item.total;
    if (acc + 1e-9 < config.minSingleItemAccuracy) {
      failures.push(`single_item_accuracy ${acc} < ${config.minSingleItemAccuracy}`);
    }
  }
  if (multiFalse && multiFalse.total > 0) {
    const acc = multiFalse.correctRejections / multiFalse.total;
    if (acc + 1e-9 < config.minFalseOnlyRejectionAccuracy) {
      failures.push(
        `multi_false_rejection_accuracy ${acc} < ${config.minFalseOnlyRejectionAccuracy}`,
      );
    }
  }
  if (summary.domainExactAccuracy + 1e-9 < config.minOverallDomainExactAccuracy) {
    failures.push(
      `domainExactAccuracy ${summary.domainExactAccuracy} < ${config.minOverallDomainExactAccuracy}`,
    );
  }
  if (summary.detectionExactAccuracy + 1e-9 < config.minOverallDetectionExactAccuracy) {
    failures.push(
      `detectionExactAccuracy ${summary.detectionExactAccuracy} < ${config.minOverallDetectionExactAccuracy}`,
    );
  }
  return { pass: failures.length === 0, failures };
}

export function evaluateDualRegressionGate(
  c1: DualCorrectnessSummary,
  c2: DualCorrectnessSummary,
): CorrectnessRegressionGateResult {
  const failures: string[] = [];
  const worse = (label: string, a: number, b: number) => {
    if (b > a) failures.push(`${label} ${a}->${b}`);
  };
  const drop = (label: string, a: number, b: number) => {
    if (b + 1e-9 < a) failures.push(`${label} ${a}->${b}`);
  };
  worse('falsePositives', c1.falsePositives, c2.falsePositives);
  worse('falseNegatives', c1.falseNegatives, c2.falseNegatives);
  worse('wrongPosition', c1.wrongPosition, c2.wrongPosition);
  worse('wrongItem', c1.wrongItem, c2.wrongItem);
  worse('wrongQuantity', c1.wrongQuantity, c2.wrongQuantity);
  worse('pipelineErrors', c1.pipelineErrors, c2.pipelineErrors);
  worse('detectionFalseNegative', c1.detectionFalseNegative, c2.detectionFalseNegative);
  drop('totalPhotos', c1.totalPhotos, c2.totalPhotos);
  drop('detectionExactAccuracy', c1.detectionExactAccuracy, c2.detectionExactAccuracy);
  drop('domainExactAccuracy', c1.domainExactAccuracy, c2.domainExactAccuracy);
  return { pass: failures.length === 0, failures };
}

export function diffDualCorrectnessRuns(
  a: readonly DualCorrectnessRow[],
  b: readonly DualCorrectnessRow[],
): Array<{
  readonly filename: string;
  readonly aDetection: DetectionResultCode;
  readonly bDetection: DetectionResultCode;
  readonly aDomain: DomainResultCode;
  readonly bDomain: DomainResultCode;
}> {
  const mapB = new Map(b.map((r) => [r.filename, r]));
  const out: Array<{
    filename: string;
    aDetection: DetectionResultCode;
    bDetection: DetectionResultCode;
    aDomain: DomainResultCode;
    bDomain: DomainResultCode;
  }> = [];
  for (const r of a) {
    const o = mapB.get(r.filename);
    if (!o) {
      out.push({
        filename: r.filename,
        aDetection: r.detectionResult,
        bDetection: 'DETECTION_PIPELINE_ERROR',
        aDomain: r.domainResult,
        bDomain: 'PIPELINE_ERROR',
      });
      continue;
    }
    if (r.detectionResult !== o.detectionResult || r.domainResult !== o.domainResult) {
      out.push({
        filename: r.filename,
        aDetection: r.detectionResult,
        bDetection: o.detectionResult,
        aDomain: r.domainResult,
        bDomain: o.domainResult,
      });
    }
  }
  return out;
}

export function buildPhotoCorrectnessRow(input: {
  readonly benchmarkSequence: number;
  readonly originalSequence: number;
  readonly filename: string;
  readonly scenarioKind: BenchmarkManifestScenarioKind;
  readonly labelsJson?: string | null;
  readonly actualRawDetectedPayloads: readonly string[];
  readonly actualAcceptedPayloads: readonly string[];
  readonly actualRejectedPayloads: readonly string[];
  readonly actualPosition: string | null;
  readonly actualItems: readonly { code: string; qty: number | null }[];
  readonly draftStatus?: string | null;
  readonly errorCode?: string | null;
  readonly pipelineError?: string | null;
  readonly scannerProcessingMs?: number | null;
}): DualCorrectnessRow {
  const labels = parseLabelsJson(input.labelsJson ?? undefined);
  const expectedValid = labels.filter((l) => l.validAndes).map((l) => l.payload);
  const expectedFalse = labels.filter((l) => !l.validAndes).map((l) => l.payload);
  const expectedPhysical = [...expectedValid, ...expectedFalse];
  const expectedPosition =
    labels.find((l) => l.validAndes && l.kind.toLowerCase().includes('position'))?.payload ??
    (input.scenarioKind === 'position' ? expectedValid[0] ?? null : null);
  const expectedItems = expectedValid
    .filter((p) => p.includes('|'))
    .map((p) => parseItemPayload(p));

  const expectedOutcome = expectedDomainOutcomeForScenario(
    input.scenarioKind,
    expectedValid.length,
    input.labelsJson,
  );
  const detection = classifyDetectionCorrectness({
    expectedPhysicalPayloads: expectedPhysical,
    actualRawDetectedPayloads: input.actualRawDetectedPayloads,
    pipelineError: input.pipelineError ?? null,
  });
  const domain = classifyDomainCorrectness({
    scenarioKind: input.scenarioKind,
    expectedOutcome,
    draftStatus: input.draftStatus,
    errorCode: input.errorCode,
    expectedValidPayloads: expectedValid,
    expectedFalsePayloads: expectedFalse,
    actualAcceptedPayloads: input.actualAcceptedPayloads,
    actualRejectedPayloads: input.actualRejectedPayloads,
    expectedPosition,
    actualPosition: input.actualPosition,
    expectedItems,
    actualItems: input.actualItems,
    pipelineError: input.pipelineError ?? null,
  });

  return {
    benchmarkSequence: input.benchmarkSequence,
    originalSequence: input.originalSequence,
    filename: input.filename,
    scenarioKind: input.scenarioKind,
    expectedValidPayloads: expectedValid,
    expectedFalsePayloads: expectedFalse,
    actualRawDetectedPayloads: input.actualRawDetectedPayloads,
    actualAcceptedPayloads: input.actualAcceptedPayloads,
    actualRejectedPayloads: input.actualRejectedPayloads,
    expectedPosition,
    actualPosition: input.actualPosition,
    expectedItems: expectedItems.map((i) => `${i.code}|${i.qty ?? ''}`).join(';'),
    actualItems: input.actualItems.map((i) => `${i.code}|${i.qty ?? ''}`).join(';'),
    detectionResult: detection.result,
    domainResult: domain.result,
    expectedDomainOutcome: expectedOutcome,
    pipelineError: input.pipelineError ?? null,
    scannerProcessingMs: input.scannerProcessingMs ?? null,
    ...(detection.detail != null ? { detectionDetail: detection.detail } : {}),
    ...(domain.detail != null ? { domainDetail: domain.detail } : {}),
  };
}

/** Alias — preferred name in Phase 4 docs / runner. */
export const buildDualCorrectnessRow = buildPhotoCorrectnessRow;

/**
 * Reconstruct domain "actual" fields from a persisted local detection draft.
 * Detection actuals come separately from LocalCodeScanStrategy.getRawDetectedPayloads.
 */
export function reconstructActualFromDraft(draft: {
  readonly status?: string | null;
  readonly error_code?: string | null;
  readonly product_results_json?: string | null;
  readonly rejections_json?: string | null;
  readonly position_detected?: number | null;
  readonly position_snapshot_json?: string | null;
  readonly internal_code?: string | null;
  readonly quantity?: number | null;
  readonly label_id?: string | null;
} | null): {
  readonly actualAcceptedPayloads: readonly string[];
  readonly actualRejectedPayloads: readonly string[];
  readonly actualPosition: string | null;
  readonly actualItems: readonly { code: string; qty: number | null }[];
  readonly pipelineError: string | null;
  readonly draftStatus: string | null;
  readonly errorCode: string | null;
} {
  if (!draft) {
    return {
      actualAcceptedPayloads: [],
      actualRejectedPayloads: [],
      actualPosition: null,
      actualItems: [],
      pipelineError: 'MISSING_DRAFT',
      draftStatus: null,
      errorCode: null,
    };
  }

  const status = (draft.status ?? '').toUpperCase();
  const err = draft.error_code ?? null;
  const errUpper = (err ?? '').toUpperCase();
  const pipelineError =
    status === 'FAILED' ||
    status === 'FAILED_RETRYABLE' ||
    errUpper === 'LOCAL_SCAN_TIMEOUT' ||
    errUpper === 'LOCAL_SCAN_FAILED' ||
    errUpper === 'LOCAL_SCAN_BUSY'
      ? err ?? (status || 'PIPELINE_ERROR')
      : null;

  const actualPosition = positionPayloadFromSnapshot(
    draft.position_snapshot_json,
    Number(draft.position_detected) === 1 ||
      errUpper === 'POSITION_LABEL_DETECTED' ||
      errUpper === 'POSITION_LABEL_DUPLICATE',
  );

  const products = parseProductResultsLoose(draft.product_results_json);
  const actualItems = products
    .filter((p) => p.kind !== 'position')
    .map((p) => ({
      code: p.code,
      qty: p.qty,
    }));

  const acceptedFromProducts = products.map((p) => p.payload);
  const actualAcceptedPayloads =
    acceptedFromProducts.length > 0
      ? acceptedFromProducts
      : actualPosition
        ? [actualPosition]
        : legacyAcceptedFromDraft(draft);

  const actualRejectedPayloads = parseRejectionPayloads(draft.rejections_json);

  return {
    actualAcceptedPayloads,
    actualRejectedPayloads,
    actualPosition,
    actualItems,
    pipelineError,
    draftStatus: draft.status ?? null,
    errorCode: err,
  };
}

function positionPayloadFromSnapshot(
  snapshotJson: string | null | undefined,
  positionDetected: boolean,
): string | null {
  if (!positionDetected || !snapshotJson?.trim()) return null;
  try {
    const parsed = JSON.parse(snapshotJson) as Record<string, unknown>;
    const raw =
      (typeof parsed.rawPayload === 'string' && parsed.rawPayload.trim()) ||
      (typeof parsed.sourcePayload === 'string' && parsed.sourcePayload.trim()) ||
      (typeof parsed.rawCode === 'string' && parsed.rawCode.trim()) ||
      (typeof parsed.labelId === 'string' && parsed.labelId.trim()) ||
      '';
    return raw || null;
  } catch {
    return null;
  }
}

function parseProductResultsLoose(
  raw: string | null | undefined,
): Array<{ payload: string; code: string; qty: number | null; kind: 'item' | 'position' }> {
  if (!raw?.trim()) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    const out: Array<{
      payload: string;
      code: string;
      qty: number | null;
      kind: 'item' | 'position';
    }> = [];
    for (const item of parsed) {
      if (!item || typeof item !== 'object') continue;
      const row = item as Record<string, unknown>;
      const rawPayload =
        typeof row.rawPayload === 'string' && row.rawPayload.trim()
          ? row.rawPayload.trim()
          : null;
      const labelId = typeof row.labelId === 'string' ? row.labelId.trim() : '';
      const internalCode =
        typeof row.internalCode === 'string' && row.internalCode.trim()
          ? row.internalCode.trim()
          : null;
      let qty: number | null = null;
      if (typeof row.quantity === 'number' && Number.isFinite(row.quantity)) {
        qty = row.quantity;
      } else if (row.quantity != null) {
        const n = Number(row.quantity);
        qty = Number.isFinite(n) ? n : null;
      }
      const payload =
        rawPayload ||
        (internalCode != null && qty != null
          ? `${internalCode}|${qty}`
          : internalCode || labelId);
      if (!payload) continue;
      out.push({
        payload,
        code: internalCode || labelId || payload.split('|')[0] || payload,
        qty,
        kind: 'item',
      });
    }
    return out;
  } catch {
    return [];
  }
}

function parseRejectionPayloads(raw: string | null | undefined): string[] {
  if (!raw?.trim()) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    const out: string[] = [];
    for (const item of parsed) {
      if (!item || typeof item !== 'object') continue;
      const row = item as Record<string, unknown>;
      const preview =
        typeof row.rawValuePreview === 'string' && row.rawValuePreview.trim()
          ? row.rawValuePreview.trim()
          : '';
      const labelId =
        typeof row.labelId === 'string' && row.labelId.trim() ? row.labelId.trim() : '';
      const payload = preview || labelId;
      if (payload) out.push(payload);
    }
    return out;
  } catch {
    return [];
  }
}

function legacyAcceptedFromDraft(draft: {
  readonly internal_code?: string | null;
  readonly quantity?: number | null;
  readonly label_id?: string | null;
}): string[] {
  const code = (draft.internal_code ?? '').trim();
  const labelId = (draft.label_id ?? '').trim();
  if (code && draft.quantity != null && Number.isFinite(draft.quantity)) {
    return [`${code}|${draft.quantity}`];
  }
  if (code) return [code];
  if (labelId) return [labelId];
  return [];
}

export function dualCorrectnessToCsv(rows: readonly DualCorrectnessRow[]): string {
  const header = [
    'benchmark_sequence',
    'original_sequence',
    'filename',
    'scenario_kind',
    'expected_valid_payloads',
    'expected_false_payloads',
    'actual_raw_detected_payloads',
    'actual_accepted_payloads',
    'actual_rejected_payloads',
    'expected_position',
    'actual_position',
    'expected_items',
    'actual_items',
    'detection_result',
    'domain_result',
    'expected_domain_outcome',
    'pipeline_error',
    'scanner_processing_ms',
    'detection_detail',
    'domain_detail',
  ].join(',');
  const esc = (v: unknown) => {
    const s = v == null ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = rows.map((r) =>
    [
      r.benchmarkSequence,
      r.originalSequence,
      r.filename,
      r.scenarioKind,
      r.expectedValidPayloads.join('|'),
      r.expectedFalsePayloads.join('|'),
      r.actualRawDetectedPayloads.join('|'),
      r.actualAcceptedPayloads.join('|'),
      r.actualRejectedPayloads.join('|'),
      r.expectedPosition ?? '',
      r.actualPosition ?? '',
      r.expectedItems,
      r.actualItems,
      r.detectionResult,
      r.domainResult,
      r.expectedDomainOutcome,
      r.pipelineError ?? '',
      r.scannerProcessingMs ?? '',
      r.detectionDetail ?? '',
      r.domainDetail ?? '',
    ]
      .map(esc)
      .join(','),
  );
  return [header, ...lines].join('\n') + '\n';
}

// Re-exports for callers that already import from this module path preference
export {
  classifyPhotoCorrectness,
  summarizeCorrectness,
  diffCorrectnessRuns,
  evaluateCorrectnessRegressionGate,
  parseLabelsJson,
  parseItemPayload,
};
export type { CorrectnessRow, CorrectnessSummary, CorrectnessResultCode };
