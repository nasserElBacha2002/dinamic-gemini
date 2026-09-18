import {
  classifyPhotoCorrectness,
  diffCorrectnessRuns,
  evaluateCorrectnessRegressionGate,
  parseItemPayload,
  parseLabelsJson,
  summarizeCorrectness,
  toCorrectnessCsv,
  type CorrectnessRow,
} from '../src/features/benchmark/benchmarkCorrectness';

describe('benchmarkCorrectness', () => {
  test('parseLabelsJson and parseItemPayload', () => {
    const labels = parseLabelsJson(
      JSON.stringify([
        { kind: 'position', valid_andes: true, payload: 'ASP-A01' },
        { kind: 'item', validAndes: false, payload: 'SKU|2' },
      ]),
    );
    expect(labels).toHaveLength(2);
    expect(labels[0]!.validAndes).toBe(true);
    expect(labels[1]!.validAndes).toBe(false);
    expect(parseItemPayload('ABC|3')).toEqual({ code: 'ABC', qty: 3 });
    expect(parseItemPayload('ABC')).toEqual({ code: 'ABC', qty: null });
  });

  test('pipeline error wins', () => {
    expect(
      classifyPhotoCorrectness({
        scenarioKind: 'position',
        expectedValidPayloads: ['ASP-A'],
        expectedFalsePayloads: [],
        actualAcceptedPayloads: ['ASP-A'],
        actualRejectedPayloads: [],
        actualPosition: 'ASP-A',
        expectedPosition: 'ASP-A',
        actualItems: [],
        expectedItems: [],
        pipelineError: 'LOCAL_SCAN_TIMEOUT',
      }).result,
    ).toBe('PIPELINE_ERROR');
  });

  test('multi_false correct rejection vs false positive', () => {
    expect(
      classifyPhotoCorrectness({
        scenarioKind: 'multi_false',
        expectedValidPayloads: [],
        expectedFalsePayloads: ['BAD|1'],
        actualAcceptedPayloads: [],
        actualRejectedPayloads: ['BAD|1'],
        actualPosition: null,
        expectedPosition: null,
        actualItems: [],
        expectedItems: [],
      }).result,
    ).toBe('CORRECT_REJECTION');

    expect(
      classifyPhotoCorrectness({
        scenarioKind: 'multi_false',
        expectedValidPayloads: [],
        expectedFalsePayloads: ['BAD|1'],
        actualAcceptedPayloads: ['BAD|1'],
        actualRejectedPayloads: [],
        actualPosition: null,
        expectedPosition: null,
        actualItems: [],
        expectedItems: [],
      }).result,
    ).toBe('FALSE_POSITIVE');
  });

  test('single position and item paths', () => {
    expect(
      classifyPhotoCorrectness({
        scenarioKind: 'position',
        expectedValidPayloads: ['ASP-A'],
        expectedFalsePayloads: [],
        actualAcceptedPayloads: ['ASP-A'],
        actualRejectedPayloads: [],
        actualPosition: 'ASP-A',
        expectedPosition: 'ASP-A',
        actualItems: [],
        expectedItems: [],
      }).result,
    ).toBe('EXACT_MATCH');

    expect(
      classifyPhotoCorrectness({
        scenarioKind: 'position',
        expectedValidPayloads: ['ASP-A'],
        expectedFalsePayloads: [],
        actualAcceptedPayloads: ['ASP-B'],
        actualRejectedPayloads: [],
        actualPosition: 'ASP-B',
        expectedPosition: 'ASP-A',
        actualItems: [],
        expectedItems: [],
      }).result,
    ).toBe('WRONG_POSITION');

    expect(
      classifyPhotoCorrectness({
        scenarioKind: 'item',
        expectedValidPayloads: ['SKU|2'],
        expectedFalsePayloads: [],
        actualAcceptedPayloads: ['SKU|2'],
        actualRejectedPayloads: [],
        actualPosition: null,
        expectedPosition: null,
        actualItems: [{ code: 'SKU', qty: 2 }],
        expectedItems: [{ code: 'SKU', qty: 2 }],
      }).result,
    ).toBe('EXACT_MATCH');

    expect(
      classifyPhotoCorrectness({
        scenarioKind: 'item',
        expectedValidPayloads: ['SKU|2'],
        expectedFalsePayloads: [],
        actualAcceptedPayloads: ['SKU|9'],
        actualRejectedPayloads: [],
        actualPosition: null,
        expectedPosition: null,
        actualItems: [{ code: 'SKU', qty: 9 }],
        expectedItems: [{ code: 'SKU', qty: 2 }],
      }).result,
    ).toBe('WRONG_QUANTITY');

    expect(
      classifyPhotoCorrectness({
        scenarioKind: 'item',
        expectedValidPayloads: ['SKU|2'],
        expectedFalsePayloads: [],
        actualAcceptedPayloads: ['OTHER|2'],
        actualRejectedPayloads: [],
        actualPosition: null,
        expectedPosition: null,
        actualItems: [{ code: 'OTHER', qty: 2 }],
        expectedItems: [{ code: 'SKU', qty: 2 }],
      }).result,
    ).toBe('WRONG_ITEM');
  });

  test('multi_true and multi_mixed', () => {
    expect(
      classifyPhotoCorrectness({
        scenarioKind: 'multi_true',
        expectedValidPayloads: ['A|1', 'B|1'],
        expectedFalsePayloads: [],
        actualAcceptedPayloads: ['B|1', 'A|1'],
        actualRejectedPayloads: [],
        actualPosition: null,
        expectedPosition: null,
        actualItems: [],
        expectedItems: [],
      }).result,
    ).toBe('EXACT_MATCH');

    expect(
      classifyPhotoCorrectness({
        scenarioKind: 'multi_true',
        expectedValidPayloads: ['A|1', 'B|1'],
        expectedFalsePayloads: [],
        actualAcceptedPayloads: ['A|1'],
        actualRejectedPayloads: [],
        actualPosition: null,
        expectedPosition: null,
        actualItems: [],
        expectedItems: [],
      }).result,
    ).toBe('PARTIAL_MATCH');

    expect(
      classifyPhotoCorrectness({
        scenarioKind: 'multi_mixed',
        expectedValidPayloads: ['A|1'],
        expectedFalsePayloads: ['BAD|1'],
        actualAcceptedPayloads: ['A|1'],
        actualRejectedPayloads: ['BAD|1'],
        actualPosition: null,
        expectedPosition: null,
        actualItems: [],
        expectedItems: [],
      }).result,
    ).toBe('EXACT_MATCH');

    expect(
      classifyPhotoCorrectness({
        scenarioKind: 'multi_mixed',
        expectedValidPayloads: ['A|1'],
        expectedFalsePayloads: ['BAD|1'],
        actualAcceptedPayloads: ['A|1', 'BAD|1'],
        actualRejectedPayloads: [],
        actualPosition: null,
        expectedPosition: null,
        actualItems: [],
        expectedItems: [],
      }).result,
    ).toBe('FALSE_POSITIVE');
  });

  test('summarize, diff, regression gate, csv', () => {
    const c1: CorrectnessRow[] = [
      { filename: 'a.jpg', scenarioKind: 'position', result: 'EXACT_MATCH' },
      { filename: 'b.jpg', scenarioKind: 'item', result: 'EXACT_MATCH' },
      { filename: 'c.jpg', scenarioKind: 'multi_false', result: 'CORRECT_REJECTION' },
    ];
    const c2: CorrectnessRow[] = [
      { filename: 'a.jpg', scenarioKind: 'position', result: 'WRONG_POSITION' },
      { filename: 'b.jpg', scenarioKind: 'item', result: 'EXACT_MATCH' },
      { filename: 'c.jpg', scenarioKind: 'multi_false', result: 'FALSE_POSITIVE' },
    ];
    const s1 = summarizeCorrectness(c1);
    const s2 = summarizeCorrectness(c2);
    expect(s1.exactMatches).toBe(2);
    expect(s1.overallExactAccuracy).toBeCloseTo(1);
    expect(s2.falsePositives).toBe(1);

    const diffs = diffCorrectnessRuns(c1, c2);
    expect(diffs.map((d) => d.filename).sort()).toEqual(['a.jpg', 'c.jpg']);

    const gate = evaluateCorrectnessRegressionGate(s1, s2, diffs);
    expect(gate.pass).toBe(false);
    expect(gate.failures.some((f) => f.includes('exact_match_regressed:a.jpg'))).toBe(true);
    expect(gate.failures.some((f) => f.includes('false_positives_increased'))).toBe(true);

    const csv = toCorrectnessCsv(c1);
    expect(csv.startsWith('filename,scenario_kind,result,detail')).toBe(true);
  });
});
