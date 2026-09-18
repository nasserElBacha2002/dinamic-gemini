'use strict';

/**
 * Lightweight correctness helpers for Mac-side Phase 4 reports.
 * Aligned with mobile/src/features/benchmark/benchmarkCorrectness.ts concepts.
 */

function parseLabelsJson(raw) {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map((x) => ({
      kind: String(x.kind || ''),
      validAndes: x.valid_andes === true || x.validAndes === true,
      payload: String(x.payload || ''),
    }));
  } catch {
    return [];
  }
}

function parseItemPayload(payload) {
  const s = String(payload || '');
  const pipe = s.indexOf('|');
  if (pipe < 0) return { code: s, qty: null };
  const qty = Number(s.slice(pipe + 1));
  return { code: s.slice(0, pipe), qty: Number.isFinite(qty) ? qty : null };
}

function setEq(a, b) {
  if (a.size !== b.size) return false;
  for (const x of a) if (!b.has(x)) return false;
  return true;
}

function classifyPhotoCorrectness(input) {
  if (input.pipelineError) {
    return { result: 'PIPELINE_ERROR', detail: String(input.pipelineError) };
  }
  const expectedValid = new Set(input.expectedValidPayloads || []);
  const expectedFalse = new Set(input.expectedFalsePayloads || []);
  const accepted = new Set(input.actualAcceptedPayloads || []);
  const kind = input.scenarioKind;

  const acceptedFalse = [...accepted].filter((p) => expectedFalse.has(p));
  if (acceptedFalse.length) {
    return { result: 'FALSE_POSITIVE', detail: acceptedFalse.join('|') };
  }

  if (kind === 'multi_false') {
    if (accepted.size === 0) return { result: 'CORRECT_REJECTION' };
    return { result: 'FALSE_POSITIVE', detail: [...accepted].join('|') };
  }

  if (kind === 'position') {
    const exp = input.expectedPosition || [...expectedValid][0] || null;
    const act = input.actualPosition || null;
    if (!exp && !act) return { result: 'CORRECT_REJECTION' };
    if (!act) return { result: 'FALSE_NEGATIVE', detail: 'missing_position' };
    if (exp && act !== exp) return { result: 'WRONG_POSITION', detail: `${act}!=${exp}` };
    return { result: 'EXACT_MATCH' };
  }

  if (kind === 'item') {
    const expPayload = [...expectedValid][0] || null;
    const exp = expPayload ? parseItemPayload(expPayload) : null;
    const actItems = input.actualItems || [];
    if (!exp && actItems.length === 0) return { result: 'CORRECT_REJECTION' };
    if (!actItems.length) return { result: 'FALSE_NEGATIVE', detail: 'missing_item' };
    const act = actItems[0];
    if (exp && act.code !== exp.code) return { result: 'WRONG_ITEM', detail: `${act.code}!=${exp.code}` };
    if (exp && exp.qty != null && act.qty != null && act.qty !== exp.qty) {
      return { result: 'WRONG_QUANTITY', detail: `${act.qty}!=${exp.qty}` };
    }
    return { result: 'EXACT_MATCH' };
  }

  // multi_true / multi_mixed / other: payload set comparison
  if (setEq(accepted, expectedValid)) return { result: 'EXACT_MATCH' };
  const missing = [...expectedValid].filter((p) => !accepted.has(p));
  const extra = [...accepted].filter((p) => !expectedValid.has(p));
  if (extra.length) return { result: 'UNEXPECTED_EXTRA_LABEL', detail: extra.join('|') };
  if (missing.length && accepted.size > 0) {
    return { result: 'PARTIAL_MATCH', detail: missing.join('|') };
  }
  if (missing.length) return { result: 'FALSE_NEGATIVE', detail: missing.join('|') };
  return { result: 'PARTIAL_MATCH' };
}

function summarizeCorrectness(rows) {
  const out = {
    totalPhotos: rows.length,
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
    byScenario: {},
  };
  for (const row of rows) {
    const r = row.result;
    if (r === 'EXACT_MATCH') out.exactMatches += 1;
    else if (r === 'CORRECT_REJECTION') out.correctRejections += 1;
    else if (r === 'FALSE_POSITIVE') out.falsePositives += 1;
    else if (r === 'FALSE_NEGATIVE') out.falseNegatives += 1;
    else if (r === 'PARTIAL_MATCH') out.partialMatches += 1;
    else if (r === 'PIPELINE_ERROR') out.pipelineErrors += 1;
    else if (r === 'WRONG_POSITION') out.wrongPositions += 1;
    else if (r === 'WRONG_ITEM') out.wrongItems += 1;
    else if (r === 'WRONG_QUANTITY') out.wrongQuantities += 1;
    else if (r === 'UNEXPECTED_EXTRA_LABEL') out.unexpectedExtras += 1;
    const sk = row.scenarioKind || 'other';
    if (!out.byScenario[sk]) {
      out.byScenario[sk] = { total: 0, exactMatches: 0, correctRejections: 0, errors: 0 };
    }
    out.byScenario[sk].total += 1;
    if (r === 'EXACT_MATCH') out.byScenario[sk].exactMatches += 1;
    else if (r === 'CORRECT_REJECTION') out.byScenario[sk].correctRejections += 1;
    else out.byScenario[sk].errors += 1;
  }
  const good = out.exactMatches + out.correctRejections;
  out.overallExactAccuracy = out.totalPhotos ? good / out.totalPhotos : 0;
  return out;
}

function evaluateCorrectnessRegressionGate(c1, c2) {
  const failures = [];
  if (c2.falsePositives > c1.falsePositives) {
    failures.push(`falsePositives ${c1.falsePositives}->${c2.falsePositives}`);
  }
  if (c2.falseNegatives > c1.falseNegatives) {
    failures.push(`falseNegatives ${c1.falseNegatives}->${c2.falseNegatives}`);
  }
  if (c2.pipelineErrors > c1.pipelineErrors) {
    failures.push(`pipelineErrors ${c1.pipelineErrors}->${c2.pipelineErrors}`);
  }
  if (c2.totalPhotos < c1.totalPhotos) {
    failures.push(`totalPhotos ${c1.totalPhotos}->${c2.totalPhotos}`);
  }
  if (c2.overallExactAccuracy + 1e-9 < c1.overallExactAccuracy) {
    failures.push(
      `overallExactAccuracy ${c1.overallExactAccuracy}->${c2.overallExactAccuracy}`,
    );
  }
  return { pass: failures.length === 0, failures };
}

module.exports = {
  parseLabelsJson,
  parseItemPayload,
  classifyPhotoCorrectness,
  summarizeCorrectness,
  evaluateCorrectnessRegressionGate,
};
