'use strict';

/**
 * Mac-side dual correctness helpers — aligned with
 * mobile/src/features/benchmark/benchmarkDualCorrectness.ts
 */

const DEFAULT_ABSOLUTE_CORRECTNESS_GATE = {
  minSinglePositionAccuracy: 0.98,
  minSingleItemAccuracy: 0.98,
  minFalseOnlyRejectionAccuracy: 0.98,
  minOverallDomainExactAccuracy: 0.95,
  minOverallDetectionExactAccuracy: 0.95,
};

function summarizeDualCorrectness(rows) {
  const byScenario = {};
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
    const sk = row.scenarioKind || row.scenario_kind || 'other';
    if (!byScenario[sk]) {
      byScenario[sk] = { total: 0, detectionExact: 0, domainExact: 0, correctRejections: 0 };
    }
    byScenario[sk].total += 1;

    const expectedValid = asList(row.expectedValidPayloads || row.expected_valid_payloads);
    const expectedFalse = asList(row.expectedFalsePayloads || row.expected_false_payloads);
    const raw = asList(row.actualRawDetectedPayloads || row.actual_raw_detected_payloads);
    expectedPhysical += expectedValid.length + expectedFalse.length;
    const rawSet = new Set(raw);
    for (const p of [...expectedValid, ...expectedFalse]) {
      if (rawSet.has(p)) foundPhysical += 1;
    }

    const det = row.detectionResult || row.detection_result;
    if (det === 'DETECTION_EXACT_MATCH') {
      detectionExact += 1;
      byScenario[sk].detectionExact += 1;
    } else if (det === 'DETECTION_PARTIAL') detectionPartial += 1;
    else if (det === 'DETECTION_FALSE_NEGATIVE') detectionFalseNegative += 1;
    else if (det === 'DETECTION_UNEXPECTED_EXTRA') detectionUnexpectedExtra += 1;

    if ((row.expectedDomainOutcome || row.expected_domain_outcome) === 'AMBIGUOUS') {
      ambiguousExpected += 1;
    }
    const dom = row.domainResult || row.domain_result;
    if (dom === 'AMBIGUOUS_CORRECT') ambiguousCorrect += 1;

    if (
      dom === 'DOMAIN_EXACT_MATCH' ||
      dom === 'AMBIGUOUS_CORRECT' ||
      dom === 'CORRECT_REJECTION'
    ) {
      domainExact += 1;
      byScenario[sk].domainExact += 1;
      if (dom === 'CORRECT_REJECTION') {
        correctRejections += 1;
        byScenario[sk].correctRejections += 1;
      }
    } else if (dom === 'FALSE_POSITIVE') falsePositives += 1;
    else if (dom === 'FALSE_NEGATIVE') falseNegatives += 1;
    else if (dom === 'WRONG_POSITION') wrongPosition += 1;
    else if (dom === 'WRONG_ITEM') wrongItem += 1;
    else if (dom === 'WRONG_QUANTITY') wrongQuantity += 1;
    else if (dom === 'PIPELINE_ERROR') pipelineErrors += 1;
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

function asList(v) {
  if (Array.isArray(v)) return v.map(String).filter(Boolean);
  if (v == null || v === '') return [];
  return String(v)
    .split('|')
    .map((s) => s.trim())
    .filter(Boolean);
}

function evaluateAbsoluteCorrectnessGate(summary, config = DEFAULT_ABSOLUTE_CORRECTNESS_GATE) {
  const failures = [];
  const pos = summary.byScenario && summary.byScenario.position;
  const item = summary.byScenario && summary.byScenario.item;
  const multiFalse = summary.byScenario && summary.byScenario.multi_false;

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

function evaluateDualRegressionGate(c1, c2) {
  const failures = [];
  const worse = (label, a, b) => {
    if (b > a) failures.push(`${label} ${a}->${b}`);
  };
  const drop = (label, a, b) => {
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

function dualCorrectnessToCsv(rows) {
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
  const esc = (v) => {
    const s = v == null ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = rows.map((r) =>
    [
      r.benchmarkSequence ?? r.benchmark_sequence ?? '',
      r.originalSequence ?? r.original_sequence ?? '',
      r.filename ?? '',
      r.scenarioKind ?? r.scenario_kind ?? '',
      asList(r.expectedValidPayloads || r.expected_valid_payloads).join('|'),
      asList(r.expectedFalsePayloads || r.expected_false_payloads).join('|'),
      asList(r.actualRawDetectedPayloads || r.actual_raw_detected_payloads).join('|'),
      asList(r.actualAcceptedPayloads || r.actual_accepted_payloads).join('|'),
      asList(r.actualRejectedPayloads || r.actual_rejected_payloads).join('|'),
      r.expectedPosition ?? r.expected_position ?? '',
      r.actualPosition ?? r.actual_position ?? '',
      r.expectedItems ?? r.expected_items ?? '',
      r.actualItems ?? r.actual_items ?? '',
      r.detectionResult ?? r.detection_result ?? '',
      r.domainResult ?? r.domain_result ?? '',
      r.expectedDomainOutcome ?? r.expected_domain_outcome ?? '',
      r.pipelineError ?? r.pipeline_error ?? '',
      r.scannerProcessingMs ?? r.scanner_processing_ms ?? '',
      r.detectionDetail ?? r.detection_detail ?? '',
      r.domainDetail ?? r.domain_detail ?? '',
    ]
      .map(esc)
      .join(','),
  );
  return [header, ...lines].join('\n') + '\n';
}

function extractDualRowsFromEvents(events) {
  return (events || [])
    .filter((e) => e && e.stage === 'dual_correctness_row' && e.extras)
    .map((e) => e.extras);
}

function extractDualRowsFromStatus(status) {
  const rows = status && status.extras && status.extras.dualCorrectnessRows;
  return Array.isArray(rows) ? rows : [];
}

function buildSequenceBandsCsv(ordered, bandSize = 50) {
  const header = [
    'band',
    'start',
    'end',
    'position',
    'item',
    'multi_true',
    'multi_mixed',
    'multi_false',
    'other',
  ].join(',');
  const n = ordered.length;
  const numBands = n === 0 ? 0 : Math.ceil(n / bandSize);
  const lines = [];
  for (let b = 0; b < numBands; b += 1) {
    const start = b * bandSize;
    const end = Math.min(n, start + bandSize);
    const band = ordered.slice(start, end);
    const count = (kind) => band.filter((r) => (r.scenarioKind || r.scenario_kind) === kind).length;
    lines.push(
      [
        b + 1,
        start + 1,
        end,
        count('position'),
        count('item'),
        count('multi_true'),
        count('multi_mixed'),
        count('multi_false'),
        count('other'),
      ].join(','),
    );
  }
  return [header, ...lines].join('\n') + '\n';
}

module.exports = {
  DEFAULT_ABSOLUTE_CORRECTNESS_GATE,
  summarizeDualCorrectness,
  evaluateAbsoluteCorrectnessGate,
  evaluateDualRegressionGate,
  dualCorrectnessToCsv,
  extractDualRowsFromEvents,
  extractDualRowsFromStatus,
  buildSequenceBandsCsv,
};
