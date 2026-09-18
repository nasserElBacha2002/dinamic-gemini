/**
 * Deterministic interleaved fixture order for Andes benchmark runs (A/B stable).
 */

export const BENCHMARK_FIXTURE_ORDER_VERSION = 'andes_interleaved_v1';
export const BENCHMARK_FIXTURE_ORDER_SEED = 0xa4de5300;

/** Global proportional planner (avoids homogeneous POSITION tails). */
export const BENCHMARK_FIXTURE_ORDER_V2 = 'andes_interleaved_v2';
export const BENCHMARK_FIXTURE_ORDER_V2_SEED = 0xa4de5302;
export const MAX_CONSECUTIVE_POSITION = 4;
export const MAX_CONSECUTIVE_ITEM = 6;

/** Default for new benchmark runs. */
export const BENCHMARK_FIXTURE_ORDER_DEFAULT_VERSION = BENCHMARK_FIXTURE_ORDER_V2;
export const BENCHMARK_FIXTURE_ORDER_DEFAULT_SEED = BENCHMARK_FIXTURE_ORDER_V2_SEED;

export type BenchmarkManifestScenarioKind =
  | 'position'
  | 'item'
  | 'multi_true'
  | 'multi_mixed'
  | 'multi_false'
  | 'other';

export interface BenchmarkOrderInputRow {
  readonly sequence: number;
  readonly filename: string;
  readonly scenario: string;
  readonly category: string;
  readonly validAndesCount?: number;
  readonly falseLabelCount?: number;
  readonly labelsJson?: string;
  readonly sha256?: string;
  readonly sizeBytes?: number;
  readonly width?: number;
  readonly height?: number;
  readonly type?: string;
}

export type BenchmarkOrderedRow = BenchmarkOrderInputRow & {
  readonly benchmarkSequence: number;
  readonly originalSequence: number;
  readonly scenarioKind: BenchmarkManifestScenarioKind;
};

export type BuildInterleavedFixtureOrderResult = {
  readonly version: string;
  readonly seed: number;
  readonly ordered: readonly BenchmarkOrderedRow[];
};

export type FixtureOrderGateOptions = {
  readonly bandSize?: number;
  readonly maxConsecutivePosition?: number;
  readonly maxConsecutiveItem?: number;
};

export type FixtureOrderGateResult = {
  readonly ok: boolean;
  readonly failures: readonly string[];
};

type PlannerCategory = 'position' | 'item' | 'multi' | 'other';

const ITEM_RUN_LENGTHS = [2, 3, 4, 5, 1, 3, 4, 2] as const;
const MULTI_KINDS: readonly BenchmarkManifestScenarioKind[] = [
  'multi_true',
  'multi_mixed',
  'multi_false',
];

export function classifyScenarioKind(
  scenario: string,
  category: string,
): BenchmarkManifestScenarioKind {
  const s = scenario.trim().toLowerCase();
  const c = category.trim().toLowerCase();
  if (s.startsWith('multi_true')) return 'multi_true';
  if (s.startsWith('multi_mixed')) return 'multi_mixed';
  if (s.startsWith('multi_false')) return 'multi_false';
  if (s === 'position_single_valid' || c === 'position') return 'position';
  if (s === 'item_single_valid' || c === 'item') return 'item';
  return 'other';
}

/** mulberry32 — returns values in [0, 1). */
export function createSeededRng(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function shuffleInPlace<T>(arr: T[], rng: () => number): void {
  for (let i = arr.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1));
    const tmp = arr[i]!;
    arr[i] = arr[j]!;
    arr[j] = tmp;
  }
}

function sortBySequence(rows: readonly BenchmarkOrderInputRow[]): BenchmarkOrderInputRow[] {
  return [...rows].sort((a, b) => a.sequence - b.sequence);
}

function takeNext(
  queue: BenchmarkOrderInputRow[],
): BenchmarkOrderInputRow | undefined {
  return queue.shift();
}

function nextMultiThreshold(rng: () => number): number {
  // ~8 singles between multis, jitter ±2 → [6, 10]
  return 8 + Math.floor(rng() * 5) - 2;
}

export function buildInterleavedFixtureOrder(
  rows: readonly BenchmarkOrderInputRow[],
  options?: { readonly seed?: number; readonly version?: string },
): BuildInterleavedFixtureOrderResult {
  const seed = options?.seed ?? BENCHMARK_FIXTURE_ORDER_SEED;
  const version = options?.version ?? BENCHMARK_FIXTURE_ORDER_VERSION;
  const rng = createSeededRng(seed);

  const queues: Record<BenchmarkManifestScenarioKind, BenchmarkOrderInputRow[]> = {
    position: [],
    item: [],
    multi_true: [],
    multi_mixed: [],
    multi_false: [],
    other: [],
  };

  for (const row of sortBySequence(rows)) {
    const kind = classifyScenarioKind(row.scenario, row.category);
    queues[kind].push(row);
  }

  const itemRunLengths = [...ITEM_RUN_LENGTHS];
  shuffleInPlace(itemRunLengths, rng);
  let runIdx = 0;

  let multiRoundRobin = 0;
  let singlesSinceMulti = 0;
  let multiThreshold = nextMultiThreshold(rng);

  const emitted: BenchmarkOrderedRow[] = [];

  const emit = (row: BenchmarkOrderInputRow, kind: BenchmarkManifestScenarioKind): void => {
    emitted.push({
      ...row,
      benchmarkSequence: emitted.length + 1,
      originalSequence: row.sequence,
      scenarioKind: kind,
    });
  };

  const tryInjectMulti = (): boolean => {
    for (let attempt = 0; attempt < MULTI_KINDS.length; attempt += 1) {
      const kind = MULTI_KINDS[multiRoundRobin % MULTI_KINDS.length]!;
      multiRoundRobin += 1;
      const next = takeNext(queues[kind]);
      if (next) {
        emit(next, kind);
        singlesSinceMulti = 0;
        multiThreshold = nextMultiThreshold(rng);
        return true;
      }
    }
    return false;
  };

  const remainingMultis = (): number =>
    queues.multi_true.length + queues.multi_mixed.length + queues.multi_false.length;

  const remainingSingles = (): number => queues.position.length + queues.item.length;

  /** Keep multis from clustering at the end: pace injections by remaining ratio. */
  const shouldInjectMultiNow = (): boolean => {
    const m = remainingMultis();
    if (m === 0) return false;
    const s = remainingSingles();
    if (s === 0) return true;
    // Target spacing ≈ singles/multis; also honor seeded threshold.
    const paced = Math.max(2, Math.floor(s / m));
    return singlesSinceMulti >= Math.min(multiThreshold, paced);
  };

  while (queues.position.length > 0 || queues.item.length > 0) {
    if (shouldInjectMultiNow()) {
      tryInjectMulti();
    }

    const pos = takeNext(queues.position);
    if (pos) {
      emit(pos, 'position');
      singlesSinceMulti += 1;
    }

    const k = itemRunLengths[runIdx % itemRunLengths.length]!;
    runIdx += 1;
    for (let i = 0; i < k && queues.item.length > 0; i += 1) {
      if (shouldInjectMultiNow()) {
        tryInjectMulti();
      }
      const item = takeNext(queues.item);
      if (item) {
        emit(item, 'item');
        singlesSinceMulti += 1;
      }
    }

    if (!pos && queues.item.length === 0) {
      break;
    }
  }

  while (tryInjectMulti()) {
    // drain remaining multis in round-robin order
  }

  for (const kind of MULTI_KINDS) {
    while (queues[kind].length > 0) {
      emit(takeNext(queues[kind])!, kind);
    }
  }

  while (queues.other.length > 0) {
    emit(takeNext(queues.other)!, 'other');
  }

  if (emitted.length !== rows.length) {
    throw Object.assign(new Error('BENCHMARK_FIXTURE_ORDER_INCOMPLETE'), {
      code: 'BENCHMARK_FIXTURE_ORDER_INCOMPLETE',
      expected: rows.length,
      actual: emitted.length,
    });
  }

  return { version, seed, ordered: emitted };
}

function isMultiKind(kind: BenchmarkManifestScenarioKind): boolean {
  return kind === 'multi_true' || kind === 'multi_mixed' || kind === 'multi_false';
}

function maxConsecutiveRuns(
  ordered: readonly Pick<BenchmarkOrderedRow, 'scenarioKind'>[],
): { maxConsecutivePosition: number; maxConsecutiveItem: number } {
  let runKind: 'position' | 'item' | null = null;
  let runLen = 0;
  let maxConsecutivePosition = 0;
  let maxConsecutiveItem = 0;
  for (const row of ordered) {
    if (row.scenarioKind === 'position') {
      runLen = runKind === 'position' ? runLen + 1 : 1;
      runKind = 'position';
      maxConsecutivePosition = Math.max(maxConsecutivePosition, runLen);
    } else if (row.scenarioKind === 'item') {
      runLen = runKind === 'item' ? runLen + 1 : 1;
      runKind = 'item';
      maxConsecutiveItem = Math.max(maxConsecutiveItem, runLen);
    } else {
      runKind = null;
      runLen = 0;
    }
  }
  return { maxConsecutivePosition, maxConsecutiveItem };
}

/**
 * Soft gates for interleaved fixture order (bands + consecutive limits).
 * Invalid % of global leftover: a band that still has both position and item
 * remaining from its start to the end must include at least one of each.
 */
export function validateFixtureOrderGates(
  ordered: readonly BenchmarkOrderedRow[],
  options?: FixtureOrderGateOptions,
): FixtureOrderGateResult {
  const bandSize = options?.bandSize ?? 50;
  const maxPos = options?.maxConsecutivePosition ?? MAX_CONSECUTIVE_POSITION;
  const maxItem = options?.maxConsecutiveItem ?? MAX_CONSECUTIVE_ITEM;
  const failures: string[] = [];

  const { maxConsecutivePosition, maxConsecutiveItem } = maxConsecutiveRuns(ordered);
  if (maxConsecutivePosition > maxPos) {
    failures.push(
      `maxConsecutivePosition=${maxConsecutivePosition} exceeds limit ${maxPos}`,
    );
  }
  if (maxConsecutiveItem > maxItem) {
    failures.push(
      `maxConsecutiveItem=${maxConsecutiveItem} exceeds limit ${maxItem}`,
    );
  }

  const n = ordered.length;
  const globalMultis = ordered.filter((r) => isMultiKind(r.scenarioKind)).length;
  const numBands = n === 0 ? 0 : Math.ceil(n / bandSize);

  for (let b = 0; b < numBands; b += 1) {
    const start = b * bandSize;
    const end = Math.min(n, start + bandSize);
    const band = ordered.slice(start, end);
    if (band.length === 0) continue;
    const bandLabel = `${start + 1}-${end}`;

    const leftover = ordered.slice(start);
    const leftoverPos = leftover.filter((r) => r.scenarioKind === 'position').length;
    const leftoverItem = leftover.filter((r) => r.scenarioKind === 'item').length;
    const leftoverMulti = leftover.filter((r) => isMultiKind(r.scenarioKind)).length;

    const bandPos = band.filter((r) => r.scenarioKind === 'position').length;
    const bandItem = band.filter((r) => r.scenarioKind === 'item').length;
    const bandMulti = band.filter((r) => isMultiKind(r.scenarioKind)).length;

    if (leftoverPos > 0 && leftoverItem > 0 && (bandPos === 0 || bandItem === 0)) {
      failures.push(
        `band ${bandLabel}: expected both position and item when leftover has both`,
      );
    }

    // Soft proportional floors: each full band should track global share (not just non-zero).
    // Floor = max(1, floor(expected * 0.45)) for position/item when leftover still has both.
    if (band.length >= bandSize && leftoverPos > 0 && leftoverItem > 0) {
      const globalPos = ordered.filter((r) => r.scenarioKind === 'position').length;
      const globalItem = ordered.filter((r) => r.scenarioKind === 'item').length;
      const expectedPos = (globalPos * band.length) / n;
      const expectedItem = (globalItem * band.length) / n;
      const minPos = Math.max(1, Math.floor(expectedPos * 0.45));
      const minItem = Math.max(1, Math.floor(expectedItem * 0.45));
      if (bandPos < minPos) {
        failures.push(
          `band ${bandLabel}: position=${bandPos} below proportional floor ${minPos} (expected~${expectedPos.toFixed(1)})`,
        );
      }
      if (bandItem < minItem) {
        failures.push(
          `band ${bandLabel}: item=${bandItem} below proportional floor ${minItem} (expected~${expectedItem.toFixed(1)})`,
        );
      }
    }

    if (globalMultis > 0) {
      const bandsFromHere = numBands - b;
      // Require a multi when remaining multis can still cover every band from here.
      if (leftoverMulti >= bandsFromHere && bandMulti === 0) {
        failures.push(`band ${bandLabel}: expected at least one multi`);
      }
    }
  }

  return { ok: failures.length === 0, failures };
}

/**
 * V2: global proportional (deficit) planner.
 * Preserves relative order within each scenario bucket; places every row once.
 */
export function buildInterleavedFixtureOrderV2(
  rows: readonly BenchmarkOrderInputRow[],
  options?: {
    readonly seed?: number;
    readonly version?: string;
    readonly gateOptions?: FixtureOrderGateOptions;
  },
): BuildInterleavedFixtureOrderResult {
  const seed = options?.seed ?? BENCHMARK_FIXTURE_ORDER_V2_SEED;
  const version = options?.version ?? BENCHMARK_FIXTURE_ORDER_V2;
  const rng = createSeededRng(seed);

  const queues: Record<BenchmarkManifestScenarioKind, BenchmarkOrderInputRow[]> = {
    position: [],
    item: [],
    multi_true: [],
    multi_mixed: [],
    multi_false: [],
    other: [],
  };

  for (const row of sortBySequence(rows)) {
    const kind = classifyScenarioKind(row.scenario, row.category);
    queues[kind].push(row);
  }

  const remainingOf = (cat: PlannerCategory): number => {
    if (cat === 'position') return queues.position.length;
    if (cat === 'item') return queues.item.length;
    if (cat === 'other') return queues.other.length;
    return queues.multi_true.length + queues.multi_mixed.length + queues.multi_false.length;
  };

  const totalOf: Record<PlannerCategory, number> = {
    position: remainingOf('position'),
    item: remainingOf('item'),
    multi: remainingOf('multi'),
    other: remainingOf('other'),
  };

  // Seeded tie-break preference; leans toward position-then-item by starting order.
  const preference: PlannerCategory[] = ['position', 'item', 'multi', 'other'];
  // Light seed influence: rotate preference so different seeds can differ on ties.
  const rotateBy = Math.floor(rng() * preference.length);
  for (let i = 0; i < rotateBy; i += 1) {
    preference.push(preference.shift()!);
  }
  // Soft lean: ensure position stays ahead of item when both remain in the rotated list
  // unless seed rotated item before position — then swap back only half the time.
  const posIdx = preference.indexOf('position');
  const itemIdx = preference.indexOf('item');
  if (posIdx > itemIdx && rng() < 0.5) {
    preference[itemIdx] = 'position';
    preference[posIdx] = 'item';
  }

  let multiRoundRobin = Math.floor(rng() * MULTI_KINDS.length);
  let consecutivePosition = 0;
  let consecutiveItem = 0;

  const emitted: BenchmarkOrderedRow[] = [];

  const emit = (row: BenchmarkOrderInputRow, kind: BenchmarkManifestScenarioKind): void => {
    emitted.push({
      ...row,
      benchmarkSequence: emitted.length + 1,
      originalSequence: row.sequence,
      scenarioKind: kind,
    });
    if (kind === 'position') {
      consecutivePosition += 1;
      consecutiveItem = 0;
    } else if (kind === 'item') {
      consecutiveItem += 1;
      consecutivePosition = 0;
    } else {
      consecutivePosition = 0;
      consecutiveItem = 0;
    }
  };

  const takeMulti = (): { row: BenchmarkOrderInputRow; kind: BenchmarkManifestScenarioKind } | null => {
    for (let attempt = 0; attempt < MULTI_KINDS.length; attempt += 1) {
      const kind = MULTI_KINDS[multiRoundRobin % MULTI_KINDS.length]!;
      multiRoundRobin += 1;
      const next = takeNext(queues[kind]);
      if (next) return { row: next, kind };
    }
    return null;
  };

  const bandSize = options?.gateOptions?.bandSize ?? 50;
  const totalN = rows.length;
  const numBands = totalN === 0 ? 0 : Math.ceil(totalN / bandSize);

  const canPick = (cat: PlannerCategory): boolean => {
    if (remainingOf(cat) <= 0) return false;
    if (cat === 'position' && consecutivePosition >= MAX_CONSECUTIVE_POSITION) return false;
    if (cat === 'item' && consecutiveItem >= MAX_CONSECUTIVE_ITEM) return false;
    return true;
  };

  /**
   * Under-representation vs global share (not "largest pile first").
   * ideal_so_far = totalOf(cat) * (emitted + 1) / N; deficit = ideal - emitted_of_cat.
   * Highest deficit → most behind its global proportion → pick next.
   */
  const scoreOf = (cat: PlannerCategory): number => {
    const total = totalOf[cat];
    if (total <= 0) return -Infinity;
    const emittedOf = total - remainingOf(cat);
    const ideal = (total * (emitted.length + 1)) / totalN;
    let score = ideal - emittedOf;
    // Soft lean: after a POSITION, prefer ITEM next (P→I→I… cadence).
    if (cat === 'item' && consecutivePosition > 0) {
      score += 0.15;
    } else if (cat === 'position' && consecutivePosition === 0 && consecutiveItem === 0) {
      score += 0.05;
    }
    return score;
  };

  const pickAmong = (
    candidates: readonly PlannerCategory[],
    enforceLimits: boolean,
  ): PlannerCategory | null => {
    const eligible = candidates.filter((c) =>
      enforceLimits ? canPick(c) : remainingOf(c) > 0,
    );
    if (eligible.length === 0) return null;

    let bestScore = -Infinity;
    const tied: PlannerCategory[] = [];
    for (const cat of eligible) {
      const score = scoreOf(cat);
      if (score > bestScore + 1e-15) {
        bestScore = score;
        tied.length = 0;
        tied.push(cat);
      } else if (Math.abs(score - bestScore) <= 1e-15) {
        tied.push(cat);
      }
    }

    tied.sort((a, b) => preference.indexOf(a) - preference.indexOf(b));
    if (tied.length === 1) return tied[0]!;
    return tied[Math.floor(rng() * tied.length)]!;
  };

  /** Categories that must still appear in this band to satisfy gates. */
  const bandRequired = (): PlannerCategory[] => {
    const idx = emitted.length;
    const bandIndex = Math.floor(idx / bandSize);
    const bandStart = bandIndex * bandSize;
    const bandEnd = Math.min(totalN, bandStart + bandSize);
    const slotsLeftInBand = bandEnd - idx;
    const bandSoFar = emitted.slice(bandStart);
    const bandHasPos = bandSoFar.some((r) => r.scenarioKind === 'position');
    const bandHasItem = bandSoFar.some((r) => r.scenarioKind === 'item');
    const bandHasMulti = bandSoFar.some((r) => isMultiKind(r.scenarioKind));

    const leftoverPos = remainingOf('position');
    const leftoverItem = remainingOf('item');
    const leftoverMulti = remainingOf('multi');
    const bandsFromHere = numBands - bandIndex;

    const need: PlannerCategory[] = [];
    if (leftoverPos > 0 && leftoverItem > 0) {
      if (!bandHasPos) need.push('position');
      if (!bandHasItem) need.push('item');
    }
    if (leftoverMulti > 0 && leftoverMulti >= bandsFromHere && !bandHasMulti) {
      need.push('multi');
    }

    if (need.length === 0) return [];
    if (slotsLeftInBand > need.length) return [];
    return need;
  };

  const pickCategory = (_remainingSlots: number): PlannerCategory | null => {
    const required = bandRequired();
    if (required.length > 0) {
      const forced =
        pickAmong(required, true) ??
        (required.includes('multi') ? pickAmong(['multi'], false) : null) ??
        pickAmong(required, false);
      if (forced) return forced;
    }

    const all: PlannerCategory[] = ['position', 'item', 'multi', 'other'];
    return pickAmong(all, true) ?? pickAmong(all, false);
  };

  let remainingSlots = rows.length;
  while (remainingSlots > 0) {
    const cat = pickCategory(remainingSlots);
    if (!cat) {
      break;
    }

    if (cat === 'position') {
      const row = takeNext(queues.position);
      if (!row) break;
      emit(row, 'position');
    } else if (cat === 'item') {
      const row = takeNext(queues.item);
      if (!row) break;
      emit(row, 'item');
    } else if (cat === 'multi') {
      const taken = takeMulti();
      if (!taken) break;
      emit(taken.row, taken.kind);
    } else {
      const row = takeNext(queues.other);
      if (!row) break;
      emit(row, 'other');
    }
    remainingSlots -= 1;
  }

  // Safety drain (should be empty if planner is complete).
  for (const kind of [
    'position',
    'item',
    'multi_true',
    'multi_mixed',
    'multi_false',
    'other',
  ] as const) {
    while (queues[kind].length > 0) {
      emit(takeNext(queues[kind])!, kind);
    }
  }

  if (emitted.length !== rows.length) {
    throw Object.assign(new Error('BENCHMARK_FIXTURE_ORDER_INCOMPLETE'), {
      code: 'BENCHMARK_FIXTURE_ORDER_INCOMPLETE',
      expected: rows.length,
      actual: emitted.length,
    });
  }

  const gates = validateFixtureOrderGates(emitted, options?.gateOptions);
  if (!gates.ok) {
    throw Object.assign(new Error('BENCHMARK_FIXTURE_ORDER_GATE_FAILED'), {
      code: 'BENCHMARK_FIXTURE_ORDER_GATE_FAILED',
      failures: gates.failures,
    });
  }

  return { version, seed, ordered: emitted };
}

export function assertSameOrder(
  a: readonly Pick<BenchmarkOrderedRow, 'filename' | 'benchmarkSequence'>[],
  b: readonly Pick<BenchmarkOrderedRow, 'filename' | 'benchmarkSequence'>[],
): boolean {
  if (a.length !== b.length) return false;
  const bySeqA = [...a].sort((x, y) => x.benchmarkSequence - y.benchmarkSequence);
  const bySeqB = [...b].sort((x, y) => x.benchmarkSequence - y.benchmarkSequence);
  for (let i = 0; i < bySeqA.length; i += 1) {
    if (bySeqA[i]!.filename !== bySeqB[i]!.filename) return false;
    if (bySeqA[i]!.benchmarkSequence !== bySeqB[i]!.benchmarkSequence) return false;
  }
  return true;
}

function csvEscape(value: string | number | undefined | null): string {
  if (value == null) return '';
  const s = String(value);
  if (/[",\r\n]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export function toOrderedManifestCsv(ordered: readonly BenchmarkOrderedRow[]): string {
  const header = [
    'benchmark_sequence',
    'original_sequence',
    'filename',
    'scenario',
    'category',
    'sha256',
    'valid_andes_count',
    'false_label_count',
    'labels_json',
    'size_bytes',
    'width',
    'height',
  ].join(',');
  const lines = ordered.map((r) =>
    [
      r.benchmarkSequence,
      r.originalSequence,
      csvEscape(r.filename),
      csvEscape(r.scenario),
      csvEscape(r.category),
      csvEscape(r.sha256),
      r.validAndesCount ?? '',
      r.falseLabelCount ?? '',
      csvEscape(r.labelsJson),
      r.sizeBytes ?? '',
      r.width ?? '',
      r.height ?? '',
    ].join(','),
  );
  return [header, ...lines].join('\n') + '\n';
}
