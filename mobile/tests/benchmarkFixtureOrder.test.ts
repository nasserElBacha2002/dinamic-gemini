import {
  BENCHMARK_FIXTURE_ORDER_SEED,
  BENCHMARK_FIXTURE_ORDER_VERSION,
  BENCHMARK_FIXTURE_ORDER_V2,
  BENCHMARK_FIXTURE_ORDER_V2_SEED,
  assertSameOrder,
  buildInterleavedFixtureOrder,
  buildInterleavedFixtureOrderV2,
  classifyScenarioKind,
  createSeededRng,
  toOrderedManifestCsv,
  validateFixtureOrderGates,
  type BenchmarkOrderInputRow,
} from '../src/features/benchmark/benchmarkFixtureOrder';

function row(
  sequence: number,
  filename: string,
  scenario: string,
  category: string,
  extra?: Partial<BenchmarkOrderInputRow>,
): BenchmarkOrderInputRow {
  return { sequence, filename, scenario, category, ...extra };
}

function synthetic300(): BenchmarkOrderInputRow[] {
  const rows: BenchmarkOrderInputRow[] = [];
  let seq = 1;
  const push = (
    count: number,
    scenario: string,
    category: string,
    prefix: string,
  ) => {
    for (let i = 0; i < count; i += 1) {
      const filename = `${prefix}_${String(i + 1).padStart(3, '0')}.jpg`;
      rows.push(
        row(seq, filename, scenario, category, {
          sha256: `sha_${prefix}_${i + 1}`,
        }),
      );
      seq += 1;
    }
  };
  push(80, 'position_single_valid', 'position', 'pos');
  push(130, 'item_single_valid', 'item', 'item');
  push(30, 'multi_true_2', 'multi', 'mt');
  push(30, 'multi_mixed_2', 'multi', 'mm');
  push(30, 'multi_false_2', 'multi', 'mf');
  return rows;
}

describe('benchmarkFixtureOrder', () => {
  test('classifyScenarioKind maps position/item/multi prefixes', () => {
    expect(classifyScenarioKind('position_single_valid', 'position')).toBe('position');
    expect(classifyScenarioKind('item_single_valid', 'item')).toBe('item');
    expect(classifyScenarioKind('multi_true_2', 'multi')).toBe('multi_true');
    expect(classifyScenarioKind('multi_mixed_3', 'multi')).toBe('multi_mixed');
    expect(classifyScenarioKind('multi_false_2', 'multi')).toBe('multi_false');
    expect(classifyScenarioKind('weird', 'position')).toBe('position');
    expect(classifyScenarioKind('weird', 'item')).toBe('item');
    expect(classifyScenarioKind('unknown', 'other')).toBe('other');
  });

  test('mulberry32 is deterministic and in [0,1)', () => {
    const a = createSeededRng(BENCHMARK_FIXTURE_ORDER_SEED);
    const b = createSeededRng(BENCHMARK_FIXTURE_ORDER_SEED);
    const seqA = [a(), a(), a(), a(), a()];
    const seqB = [b(), b(), b(), b(), b()];
    expect(seqA).toEqual(seqB);
    for (const v of seqA) {
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });

  test('buildInterleavedFixtureOrder (v1) includes every row once and is stable', () => {
    const rows: BenchmarkOrderInputRow[] = [
      row(1, 'p1.jpg', 'position_single_valid', 'position'),
      row(2, 'p2.jpg', 'position_single_valid', 'position'),
      row(3, 'i1.jpg', 'item_single_valid', 'item'),
      row(4, 'i2.jpg', 'item_single_valid', 'item'),
      row(5, 'i3.jpg', 'item_single_valid', 'item'),
      row(6, 'i4.jpg', 'item_single_valid', 'item'),
      row(7, 'mt.jpg', 'multi_true_2', 'multi'),
      row(8, 'mm.jpg', 'multi_mixed_2', 'multi'),
      row(9, 'mf.jpg', 'multi_false_2', 'multi'),
      row(10, 'i5.jpg', 'item_single_valid', 'item'),
    ];

    const r1 = buildInterleavedFixtureOrder(rows);
    const r2 = buildInterleavedFixtureOrder(rows);
    expect(r1.version).toBe(BENCHMARK_FIXTURE_ORDER_VERSION);
    expect(r1.seed).toBe(BENCHMARK_FIXTURE_ORDER_SEED);
    expect(r1.ordered).toHaveLength(rows.length);
    expect(assertSameOrder(r1.ordered, r2.ordered)).toBe(true);

    const names = r1.ordered.map((o) => o.filename).sort();
    expect(names).toEqual([...rows.map((r) => r.filename)].sort());
    expect(new Set(r1.ordered.map((o) => o.benchmarkSequence)).size).toBe(rows.length);
    expect(r1.ordered.every((o) => o.originalSequence === o.sequence)).toBe(true);

    // Multis should not all be clustered at the end when singles exist.
    const multiIdx = r1.ordered
      .map((o, i) => (o.scenarioKind.startsWith('multi') ? i : -1))
      .filter((i) => i >= 0);
    expect(multiIdx.length).toBe(3);
    expect(Math.max(...multiIdx) - Math.min(...multiIdx)).toBeGreaterThan(1);
  });

  test('v2 same seed => same order; different seed can differ; both pass gates', () => {
    const rows = synthetic300();
    const a1 = buildInterleavedFixtureOrderV2(rows);
    const a2 = buildInterleavedFixtureOrderV2(rows, {
      seed: BENCHMARK_FIXTURE_ORDER_V2_SEED,
    });
    expect(a1.version).toBe(BENCHMARK_FIXTURE_ORDER_V2);
    expect(a1.seed).toBe(BENCHMARK_FIXTURE_ORDER_V2_SEED);
    expect(assertSameOrder(a1.ordered, a2.ordered)).toBe(true);
    expect(validateFixtureOrderGates(a1.ordered).ok).toBe(true);

    const b = buildInterleavedFixtureOrderV2(rows, { seed: 0xdeadbeef });
    expect(validateFixtureOrderGates(b.ordered).ok).toBe(true);
    // Different seeds are allowed to produce a different order (not required, but typical).
    const sameAsDefault = assertSameOrder(a1.ordered, b.ordered);
    if (sameAsDefault) {
      // Extremely unlikely for 300 rows; still gates must pass.
      expect(validateFixtureOrderGates(b.ordered).ok).toBe(true);
    } else {
      expect(sameAsDefault).toBe(false);
    }
  });

  test('v2 synthetic 300: no loss/dup, gates pass, no homogeneous tail, identity preserved', () => {
    const rows = synthetic300();
    const byFilename = new Map(rows.map((r) => [r.filename, r]));
    const result = buildInterleavedFixtureOrderV2(rows);
    expect(result.ordered).toHaveLength(300);

    const filenames = result.ordered.map((o) => o.filename);
    expect(new Set(filenames).size).toBe(300);
    expect([...filenames].sort()).toEqual([...rows.map((r) => r.filename)].sort());

    for (const o of result.ordered) {
      const orig = byFilename.get(o.filename)!;
      expect(o.sha256).toBe(orig.sha256);
      expect(o.filename).toBe(orig.filename);
      expect(o.originalSequence).toBe(orig.sequence);
    }

    // Each 50-band should track global share (not ITEM-starved or POSITION-starved).
    for (let b = 0; b < 6; b += 1) {
      const band = result.ordered.slice(b * 50, (b + 1) * 50);
      const pos = band.filter((r) => r.scenarioKind === 'position').length;
      const item = band.filter((r) => r.scenarioKind === 'item').length;
      expect(pos).toBeGreaterThanOrEqual(5);
      expect(item).toBeGreaterThanOrEqual(8);
    }

    const gates = validateFixtureOrderGates(result.ordered);
    expect(gates.failures).toEqual([]);
    expect(gates.ok).toBe(true);

    const tail = result.ordered.slice(-20);
    const tailKinds = new Set(tail.map((r) => r.scenarioKind));
    expect(tailKinds.size).toBeGreaterThan(1);

    const csv = toOrderedManifestCsv(result.ordered);
    expect(csv.split('\n')[0]).toContain('benchmark_sequence');
    expect(csv.split('\n').filter((l) => l.length > 0)).toHaveLength(301);
  });

  test('v2 seed stability and band composition gates for 300', () => {
    const rows = synthetic300();
    const a = buildInterleavedFixtureOrderV2(rows, { seed: BENCHMARK_FIXTURE_ORDER_V2_SEED });
    const b = buildInterleavedFixtureOrderV2(rows, { seed: BENCHMARK_FIXTURE_ORDER_V2_SEED });
    expect(assertSameOrder(a.ordered, b.ordered)).toBe(true);

    const bandSize = 50;
    for (let start = 0; start < 300; start += bandSize) {
      const band = a.ordered.slice(start, start + bandSize);
      const kinds = new Set(band.map((r) => r.scenarioKind));
      // Every full band should mix at least position + item when both remain globally.
      expect(kinds.has('position')).toBe(true);
      expect(kinds.has('item')).toBe(true);
    }

    // No homogeneous tail of 20+ identical kinds.
    const last20 = a.ordered.slice(-20);
    expect(new Set(last20.map((r) => r.scenarioKind)).size).toBeGreaterThan(1);
  });

  test('toOrderedManifestCsv has required columns', () => {
    const ordered = buildInterleavedFixtureOrder([
      {
        ...row(1, 'a.jpg', 'position_single_valid', 'position'),
        sha256: 'abc',
        validAndesCount: 1,
        falseLabelCount: 0,
        labelsJson: '[{"kind":"position"}]',
        sizeBytes: 10,
        width: 1,
        height: 2,
      },
    ]).ordered;
    const csv = toOrderedManifestCsv(ordered);
    expect(csv.split('\n')[0]).toBe(
      'benchmark_sequence,original_sequence,filename,scenario,category,sha256,valid_andes_count,false_label_count,labels_json,size_bytes,width,height',
    );
    expect(csv).toContain('a.jpg');
  });
});
