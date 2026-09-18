import {
  buildDualCorrectnessRow,
  classifyDetectionCorrectness,
  classifyDomainCorrectness,
  evaluateAbsoluteCorrectnessGate,
  evaluateDualRegressionGate,
  expectedDomainOutcomeForScenario,
  reconstructActualFromDraft,
  summarizeDualCorrectness,
  DEFAULT_ABSOLUTE_CORRECTNESS_GATE,
} from '../src/features/benchmark/benchmarkDualCorrectness';

describe('benchmarkDualCorrectness', () => {
  test('detection vs domain are independent axes', () => {
    const detection = classifyDetectionCorrectness({
      expectedPhysicalPayloads: ['ASP-A', 'BAD|1'],
      actualRawDetectedPayloads: ['ASP-A'], // missed BAD
    });
    expect(detection.result).toBe('DETECTION_PARTIAL');

    const domain = classifyDomainCorrectness({
      scenarioKind: 'multi_mixed',
      expectedOutcome: expectedDomainOutcomeForScenario('multi_mixed', 1),
      draftStatus: 'RESOLVED',
      errorCode: null,
      expectedValidPayloads: ['GOOD|1'],
      expectedFalsePayloads: ['BAD|1'],
      actualAcceptedPayloads: ['GOOD|1'],
      actualRejectedPayloads: ['BAD|1'],
      expectedPosition: null,
      actualPosition: null,
      expectedItems: [{ code: 'GOOD', qty: 1 }],
      actualItems: [{ code: 'GOOD', qty: 1 }],
    });
    // Domain can be exact even when detection missed a false label that was never accepted.
    expect(domain.result).toBe('DOMAIN_EXACT_MATCH');
  });

  test('absolute gate fails below thresholds', () => {
    const rows = [
      buildDualCorrectnessRow({
        benchmarkSequence: 1,
        originalSequence: 1,
        filename: 'p.jpg',
        scenarioKind: 'position',
        labelsJson: JSON.stringify([
          { kind: 'position', valid_andes: true, payload: 'ASP-A' },
        ]),
        actualRawDetectedPayloads: [],
        actualAcceptedPayloads: [],
        actualRejectedPayloads: [],
        actualPosition: null,
        actualItems: [],
        pipelineError: 'LOCAL_SCAN_TIMEOUT',
      }),
    ];
    const summary = summarizeDualCorrectness(rows);
    const gate = evaluateAbsoluteCorrectnessGate(summary, {
      ...DEFAULT_ABSOLUTE_CORRECTNESS_GATE,
      minSinglePositionAccuracy: 0.98,
      minOverallDomainExactAccuracy: 0.95,
      minOverallDetectionExactAccuracy: 0.95,
    });
    expect(gate.pass).toBe(false);
    expect(gate.failures.length).toBeGreaterThan(0);
  });

  test('absolute gate passes clean position+item set', () => {
    const rows = [
      buildDualCorrectnessRow({
        benchmarkSequence: 1,
        originalSequence: 1,
        filename: 'pos.jpg',
        scenarioKind: 'position',
        labelsJson: JSON.stringify([
          { kind: 'position', valid_andes: true, payload: 'ASP-A' },
        ]),
        actualRawDetectedPayloads: ['ASP-A'],
        actualAcceptedPayloads: ['ASP-A'],
        actualRejectedPayloads: [],
        actualPosition: 'ASP-A',
        actualItems: [],
      }),
      buildDualCorrectnessRow({
        benchmarkSequence: 2,
        originalSequence: 2,
        filename: 'item.jpg',
        scenarioKind: 'item',
        labelsJson: JSON.stringify([
          { kind: 'item', valid_andes: true, payload: 'SKU|2' },
        ]),
        actualRawDetectedPayloads: ['SKU|2'],
        actualAcceptedPayloads: ['SKU|2'],
        actualRejectedPayloads: [],
        actualPosition: null,
        actualItems: [{ code: 'SKU', qty: 2 }],
      }),
    ];
    const summary = summarizeDualCorrectness(rows);
    expect(evaluateAbsoluteCorrectnessGate(summary).pass).toBe(true);
  });

  test('regression gate detects accuracy drop', () => {
    const c1 = {
      totalPhotos: 2,
      detectionExact: 2,
      detectionPartial: 0,
      detectionFalseNegative: 0,
      detectionUnexpectedExtra: 0,
      detectionExactAccuracy: 1,
      detectionRecall: 1,
      domainExact: 2,
      correctRejections: 0,
      falsePositives: 0,
      falseNegatives: 0,
      wrongPosition: 0,
      wrongItem: 0,
      wrongQuantity: 0,
      ambiguousExpected: 0,
      ambiguousCorrect: 0,
      pipelineErrors: 0,
      domainExactAccuracy: 1,
      byScenario: {},
    };
    const c2 = { ...c1, detectionExactAccuracy: 0.5, domainExactAccuracy: 0.5, falsePositives: 1 };
    const gate = evaluateDualRegressionGate(c1, c2);
    expect(gate.pass).toBe(false);
    expect(gate.failures.some((f) => f.includes('falsePositives'))).toBe(true);
  });

  test('reconstructActualFromDraft maps products, rejections, position', () => {
    const actual = reconstructActualFromDraft({
      status: 'RESOLVED',
      error_code: null,
      product_results_json: JSON.stringify([
        { labelId: 'L1', internalCode: 'SKU', quantity: 2, rawPayload: 'SKU|2' },
      ]),
      rejections_json: JSON.stringify([
        { labelId: 'BAD', validationStatus: 'D1_MALFORMED', reason: 'bad', rawValuePreview: 'BAD|9' },
      ]),
      position_detected: 1,
      position_snapshot_json: JSON.stringify({ rawPayload: 'ASP-A', labelId: 'ASP-A' }),
    });
    expect(actual.actualAcceptedPayloads).toEqual(['SKU|2']);
    expect(actual.actualRejectedPayloads).toEqual(['BAD|9']);
    expect(actual.actualPosition).toBe('ASP-A');
    expect(actual.actualItems).toEqual([{ code: 'SKU', qty: 2 }]);
    expect(actual.pipelineError).toBeNull();
  });

  test('missing draft yields PIPELINE_ERROR via reconstruct', () => {
    const actual = reconstructActualFromDraft(null);
    expect(actual.pipelineError).toBe('MISSING_DRAFT');
  });
});
