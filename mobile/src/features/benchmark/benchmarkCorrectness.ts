/**
 * Benchmark correctness classification: expected (manifest) vs actual (draft/outcomes).
 */

import type { BenchmarkManifestScenarioKind } from './benchmarkFixtureOrder';

export type CorrectnessResultCode =
  | 'EXACT_MATCH'
  | 'CORRECT_REJECTION'
  | 'PARTIAL_MATCH'
  | 'FALSE_POSITIVE'
  | 'FALSE_NEGATIVE'
  | 'UNEXPECTED_EXTRA_LABEL'
  | 'WRONG_POSITION'
  | 'WRONG_ITEM'
  | 'WRONG_QUANTITY'
  | 'PIPELINE_ERROR';

export interface BenchmarkLabelExpectation {
  readonly kind: string;
  readonly validAndes: boolean;
  readonly payload: string;
}

export interface BenchmarkItemExpectation {
  readonly code: string;
  readonly qty: number | null;
}

export interface ClassifyPhotoCorrectnessInput {
  readonly scenarioKind: BenchmarkManifestScenarioKind;
  readonly expectedValidPayloads: readonly string[];
  readonly expectedFalsePayloads: readonly string[];
  readonly actualAcceptedPayloads: readonly string[];
  readonly actualRejectedPayloads: readonly string[];
  readonly actualPosition: string | null;
  readonly expectedPosition: string | null;
  readonly actualItems: readonly BenchmarkItemExpectation[];
  readonly expectedItems: readonly BenchmarkItemExpectation[];
  readonly pipelineError?: string | null;
}

export interface ClassifyPhotoCorrectnessResult {
  readonly result: CorrectnessResultCode;
  readonly detail?: string;
}

export interface CorrectnessRow {
  readonly filename: string;
  readonly scenarioKind: BenchmarkManifestScenarioKind;
  readonly result: CorrectnessResultCode;
  readonly detail?: string;
}

export interface CorrectnessScenarioBucket {
  readonly total: number;
  readonly exactMatches: number;
  readonly correctRejections: number;
  readonly falsePositives: number;
  readonly falseNegatives: number;
  readonly partialMatches: number;
  readonly pipelineErrors: number;
  readonly wrongPositions: number;
  readonly wrongItems: number;
  readonly wrongQuantities: number;
  readonly unexpectedExtras: number;
}

export interface CorrectnessSummary {
  readonly totalPhotos: number;
  readonly exactMatches: number;
  readonly correctRejections: number;
  readonly falsePositives: number;
  readonly falseNegatives: number;
  readonly partialMatches: number;
  readonly pipelineErrors: number;
  readonly wrongPositions: number;
  readonly wrongItems: number;
  readonly wrongQuantities: number;
  readonly unexpectedExtras: number;
  readonly overallExactAccuracy: number;
  readonly byScenario: Readonly<Record<string, CorrectnessScenarioBucket>>;
}

export interface CorrectnessRunDiff {
  readonly filename: string;
  readonly c1Result: CorrectnessResultCode;
  readonly c2Result: CorrectnessResultCode;
  readonly c1Detail?: string;
  readonly c2Detail?: string;
  readonly scenarioKind?: BenchmarkManifestScenarioKind;
}

export interface CorrectnessRegressionGateResult {
  readonly pass: boolean;
  readonly failures: readonly string[];
}

const WORSE_THAN_EXACT: ReadonlySet<CorrectnessResultCode> = new Set([
  'PARTIAL_MATCH',
  'FALSE_POSITIVE',
  'FALSE_NEGATIVE',
  'UNEXPECTED_EXTRA_LABEL',
  'WRONG_POSITION',
  'WRONG_ITEM',
  'WRONG_QUANTITY',
  'PIPELINE_ERROR',
]);

function normalizePayload(p: string): string {
  return p.trim();
}

function setOf(payloads: readonly string[]): Set<string> {
  return new Set(payloads.map(normalizePayload).filter(Boolean));
}

function itemKey(item: BenchmarkItemExpectation): string {
  return `${item.code.trim()}|${item.qty == null ? '' : String(item.qty)}`;
}

export function parseLabelsJson(
  json: string | undefined,
): Array<{ kind: string; validAndes: boolean; payload: string }> {
  if (!json || !json.trim()) return [];
  try {
    const parsed = JSON.parse(json) as unknown;
    if (!Array.isArray(parsed)) return [];
    const out: Array<{ kind: string; validAndes: boolean; payload: string }> = [];
    for (const entry of parsed) {
      if (!entry || typeof entry !== 'object') continue;
      const row = entry as Record<string, unknown>;
      const payload = typeof row.payload === 'string' ? row.payload : '';
      if (!payload) continue;
      out.push({
        kind: typeof row.kind === 'string' ? row.kind : 'other',
        validAndes: row.valid_andes === true || row.validAndes === true,
        payload,
      });
    }
    return out;
  } catch {
    return [];
  }
}

/** Split ITEM payloads of the form CODE|QTY (qty optional / non-numeric → null). */
export function parseItemPayload(payload: string): BenchmarkItemExpectation {
  const parts = payload.split('|');
  const code = (parts[0] ?? '').trim();
  if (parts.length < 2) {
    return { code, qty: null };
  }
  const rawQty = (parts[1] ?? '').trim();
  if (!rawQty) return { code, qty: null };
  const n = Number(rawQty);
  return { code, qty: Number.isFinite(n) ? n : null };
}

export function isPositionPayload(payload: string): boolean {
  return /^ASP-.+/i.test(payload.trim());
}

export function classifyPhotoCorrectness(
  input: ClassifyPhotoCorrectnessInput,
): ClassifyPhotoCorrectnessResult {
  if (input.pipelineError) {
    return { result: 'PIPELINE_ERROR', detail: input.pipelineError };
  }

  const accepted = setOf(input.actualAcceptedPayloads);
  const expectedValid = setOf(input.expectedValidPayloads);
  const expectedFalse = setOf(input.expectedFalsePayloads);

  if (
    input.scenarioKind === 'multi_false' ||
    (expectedValid.size === 0 && expectedFalse.size > 0)
  ) {
    if (accepted.size === 0) {
      return { result: 'CORRECT_REJECTION' };
    }
    return {
      result: 'FALSE_POSITIVE',
      detail: `accepted_false_or_unexpected:${[...accepted].join(',')}`,
    };
  }

  if (input.scenarioKind === 'position') {
    const expected =
      input.expectedPosition?.trim() ||
      input.expectedValidPayloads[0]?.trim() ||
      null;
    const actual =
      input.actualPosition?.trim() ||
      input.actualAcceptedPayloads[0]?.trim() ||
      null;
    if (!expected) {
      return { result: 'FALSE_NEGATIVE', detail: 'missing_expected_position' };
    }
    if (!actual) {
      return { result: 'FALSE_NEGATIVE', detail: 'missing_actual_position' };
    }
    if (actual === expected) {
      return { result: 'EXACT_MATCH' };
    }
    return { result: 'WRONG_POSITION', detail: `${actual}!=${expected}` };
  }

  if (input.scenarioKind === 'item') {
    const expected =
      input.expectedItems[0] ??
      (input.expectedValidPayloads[0]
        ? parseItemPayload(input.expectedValidPayloads[0])
        : null);
    const actual =
      input.actualItems[0] ??
      (input.actualAcceptedPayloads[0]
        ? parseItemPayload(input.actualAcceptedPayloads[0])
        : null);
    if (!expected || !expected.code) {
      return { result: 'FALSE_NEGATIVE', detail: 'missing_expected_item' };
    }
    if (!actual || !actual.code) {
      return { result: 'FALSE_NEGATIVE', detail: 'missing_actual_item' };
    }
    if (actual.code !== expected.code) {
      return { result: 'WRONG_ITEM', detail: `${actual.code}!=${expected.code}` };
    }
    if (expected.qty != null && actual.qty !== expected.qty) {
      return {
        result: 'WRONG_QUANTITY',
        detail: `${String(actual.qty)}!=${String(expected.qty)}`,
      };
    }
    return { result: 'EXACT_MATCH' };
  }

  if (input.scenarioKind === 'multi_true') {
    return classifyMultiSet(expectedValid, accepted);
  }

  if (input.scenarioKind === 'multi_mixed') {
    const falseAccepted = [...accepted].filter((p) => expectedFalse.has(p));
    if (falseAccepted.length > 0) {
      return {
        result: 'FALSE_POSITIVE',
        detail: `false_accepted:${falseAccepted.join(',')}`,
      };
    }
    const extras = [...accepted].filter(
      (p) => !expectedValid.has(p) && !expectedFalse.has(p),
    );
    if (extras.length > 0) {
      return {
        result: 'UNEXPECTED_EXTRA_LABEL',
        detail: extras.join(','),
      };
    }
    const acceptedValidOnly = new Set(
      [...accepted].filter((p) => expectedValid.has(p)),
    );
    return classifyMultiSet(expectedValid, acceptedValidOnly);
  }

  // other / fallback: set equality on expected valid
  if (expectedValid.size === 0 && accepted.size === 0) {
    return { result: 'CORRECT_REJECTION' };
  }
  return classifyMultiSet(expectedValid, accepted);
}

function classifyMultiSet(
  expectedValid: Set<string>,
  accepted: Set<string>,
): ClassifyPhotoCorrectnessResult {
  if (expectedValid.size === 0) {
    if (accepted.size === 0) return { result: 'CORRECT_REJECTION' };
    return { result: 'FALSE_POSITIVE', detail: [...accepted].join(',') };
  }
  let missing = 0;
  for (const p of expectedValid) {
    if (!accepted.has(p)) missing += 1;
  }
  let extras = 0;
  for (const p of accepted) {
    if (!expectedValid.has(p)) extras += 1;
  }
  if (missing === 0 && extras === 0) {
    return { result: 'EXACT_MATCH' };
  }
  if (extras > 0 && missing === 0) {
    return {
      result: 'UNEXPECTED_EXTRA_LABEL',
      detail: [...accepted].filter((p) => !expectedValid.has(p)).join(','),
    };
  }
  if (extras > 0 && missing > 0) {
    return {
      result: 'FALSE_POSITIVE',
      detail: `missing=${missing};extras=${extras}`,
    };
  }
  if (missing > 0 && accepted.size > 0) {
    return { result: 'PARTIAL_MATCH', detail: `missing=${missing}` };
  }
  return { result: 'FALSE_NEGATIVE', detail: `missing=${missing}` };
}

function emptyBucket(): CorrectnessScenarioBucket {
  return {
    total: 0,
    exactMatches: 0,
    correctRejections: 0,
    falsePositives: 0,
    falseNegatives: 0,
    partialMatches: 0,
    pipelineErrors: 0,
    wrongPositions: 0,
    wrongItems: 0,
    wrongQuantities: 0,
    unexpectedExtras: 0,
  };
}

function bump(bucket: CorrectnessScenarioBucket, result: CorrectnessResultCode): void {
  const mutable = bucket as {
    -readonly [K in keyof CorrectnessScenarioBucket]: CorrectnessScenarioBucket[K];
  };
  mutable.total += 1;
  switch (result) {
    case 'EXACT_MATCH':
      mutable.exactMatches += 1;
      break;
    case 'CORRECT_REJECTION':
      mutable.correctRejections += 1;
      break;
    case 'FALSE_POSITIVE':
      mutable.falsePositives += 1;
      break;
    case 'FALSE_NEGATIVE':
      mutable.falseNegatives += 1;
      break;
    case 'PARTIAL_MATCH':
      mutable.partialMatches += 1;
      break;
    case 'PIPELINE_ERROR':
      mutable.pipelineErrors += 1;
      break;
    case 'WRONG_POSITION':
      mutable.wrongPositions += 1;
      break;
    case 'WRONG_ITEM':
      mutable.wrongItems += 1;
      break;
    case 'WRONG_QUANTITY':
      mutable.wrongQuantities += 1;
      break;
    case 'UNEXPECTED_EXTRA_LABEL':
      mutable.unexpectedExtras += 1;
      break;
    default:
      break;
  }
}

export function summarizeCorrectness(rows: readonly CorrectnessRow[]): CorrectnessSummary {
  const byScenario: Record<string, CorrectnessScenarioBucket> = {};
  const totals = emptyBucket();
  for (const row of rows) {
    bump(totals, row.result);
    const key = row.scenarioKind;
    if (!byScenario[key]) byScenario[key] = emptyBucket();
    bump(byScenario[key]!, row.result);
  }
  const terminalOk = totals.exactMatches + totals.correctRejections;
  return {
    totalPhotos: totals.total,
    exactMatches: totals.exactMatches,
    correctRejections: totals.correctRejections,
    falsePositives: totals.falsePositives,
    falseNegatives: totals.falseNegatives,
    partialMatches: totals.partialMatches,
    pipelineErrors: totals.pipelineErrors,
    wrongPositions: totals.wrongPositions,
    wrongItems: totals.wrongItems,
    wrongQuantities: totals.wrongQuantities,
    unexpectedExtras: totals.unexpectedExtras,
    overallExactAccuracy: totals.total === 0 ? 0 : terminalOk / totals.total,
    byScenario,
  };
}

export function diffCorrectnessRuns(
  c1: readonly CorrectnessRow[],
  c2: readonly CorrectnessRow[],
): CorrectnessRunDiff[] {
  const map2 = new Map(c2.map((r) => [r.filename, r]));
  const diffs: CorrectnessRunDiff[] = [];
  const seen = new Set<string>();
  for (const r1 of c1) {
    seen.add(r1.filename);
    const r2 = map2.get(r1.filename);
    if (!r2) {
      diffs.push({
        filename: r1.filename,
        c1Result: r1.result,
        c2Result: 'PIPELINE_ERROR',
        ...(r1.detail != null ? { c1Detail: r1.detail } : {}),
        c2Detail: 'missing_in_c2',
        scenarioKind: r1.scenarioKind,
      });
      continue;
    }
    if (r1.result !== r2.result || (r1.detail ?? '') !== (r2.detail ?? '')) {
      diffs.push({
        filename: r1.filename,
        c1Result: r1.result,
        c2Result: r2.result,
        ...(r1.detail != null ? { c1Detail: r1.detail } : {}),
        ...(r2.detail != null ? { c2Detail: r2.detail } : {}),
        scenarioKind: r1.scenarioKind,
      });
    }
  }
  for (const r2 of c2) {
    if (seen.has(r2.filename)) continue;
    diffs.push({
      filename: r2.filename,
      c1Result: 'PIPELINE_ERROR',
      c2Result: r2.result,
      c1Detail: 'missing_in_c1',
      ...(r2.detail != null ? { c2Detail: r2.detail } : {}),
      scenarioKind: r2.scenarioKind,
    });
  }
  return diffs;
}

export function evaluateCorrectnessRegressionGate(
  c1Summary: CorrectnessSummary,
  c2Summary: CorrectnessSummary,
  diffs: readonly CorrectnessRunDiff[],
): CorrectnessRegressionGateResult {
  const failures: string[] = [];
  if (c2Summary.falsePositives > c1Summary.falsePositives) {
    failures.push(
      `false_positives_increased:${c1Summary.falsePositives}->${c2Summary.falsePositives}`,
    );
  }
  if (c2Summary.falseNegatives > c1Summary.falseNegatives) {
    failures.push(
      `false_negatives_increased:${c1Summary.falseNegatives}->${c2Summary.falseNegatives}`,
    );
  }
  if (c2Summary.pipelineErrors > c1Summary.pipelineErrors) {
    failures.push(
      `pipeline_errors_increased:${c1Summary.pipelineErrors}->${c2Summary.pipelineErrors}`,
    );
  }
  const c1Terminal = c1Summary.exactMatches + c1Summary.correctRejections;
  const c2Terminal = c2Summary.exactMatches + c2Summary.correctRejections;
  if (c2Terminal < c1Terminal) {
    failures.push(`terminal_photos_decreased:${c1Terminal}->${c2Terminal}`);
  }
  for (const d of diffs) {
    if (d.c1Result === 'EXACT_MATCH' && WORSE_THAN_EXACT.has(d.c2Result)) {
      failures.push(`exact_match_regressed:${d.filename}:${d.c1Result}->${d.c2Result}`);
    }
  }
  return { pass: failures.length === 0, failures };
}

function csvEscape(value: string | number | undefined | null): string {
  if (value == null) return '';
  const s = String(value);
  if (/[",\r\n]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export function toCorrectnessCsv(rows: readonly CorrectnessRow[]): string {
  const header = 'filename,scenario_kind,result,detail';
  const lines = rows.map((r) =>
    [csvEscape(r.filename), r.scenarioKind, r.result, csvEscape(r.detail)].join(','),
  );
  return [header, ...lines].join('\n') + '\n';
}

/** Convenience: build expected item list from CODE|QTY payloads. */
export function expectedItemsFromPayloads(
  payloads: readonly string[],
): BenchmarkItemExpectation[] {
  return payloads.map(parseItemPayload);
}

/** Stable key helper exported for tests. */
export function itemExpectationKey(item: BenchmarkItemExpectation): string {
  return itemKey(item);
}
