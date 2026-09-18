'use strict';

/**
 * Deterministic interleaved fixture order — must stay aligned with
 * mobile/src/features/benchmark/benchmarkFixtureOrder.ts
 */

const BENCHMARK_FIXTURE_ORDER_VERSION = 'andes_interleaved_v1';
const BENCHMARK_FIXTURE_ORDER_SEED = 0xa4de5300;

const BENCHMARK_FIXTURE_ORDER_V2 = 'andes_interleaved_v2';
const BENCHMARK_FIXTURE_ORDER_V2_SEED = 0xa4de5302;
const MAX_CONSECUTIVE_POSITION = 4;
const MAX_CONSECUTIVE_ITEM = 6;

/** Default for new benchmark runs. */
const BENCHMARK_FIXTURE_ORDER_DEFAULT_VERSION = BENCHMARK_FIXTURE_ORDER_V2;
const BENCHMARK_FIXTURE_ORDER_DEFAULT_SEED = BENCHMARK_FIXTURE_ORDER_V2_SEED;

const MULTI_KINDS = ['multi_true', 'multi_mixed', 'multi_false'];

function createSeededRng(seed) {
  let t = seed >>> 0;
  return function rng() {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

function classifyScenarioKind(scenario, category) {
  const s = String(scenario || '').toLowerCase();
  const c = String(category || '').toLowerCase();
  if (s.startsWith('multi_true') || c === 'multi_true') return 'multi_true';
  if (s.startsWith('multi_mixed') || c === 'multi_mixed') return 'multi_mixed';
  if (s.startsWith('multi_false') || c === 'multi_false') return 'multi_false';
  if (s.includes('position') || c === 'position') return 'position';
  if (s.includes('item') || c === 'item') return 'item';
  return 'other';
}

function shuffleInPlace(arr, rng) {
  for (let i = arr.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1));
    const tmp = arr[i];
    arr[i] = arr[j];
    arr[j] = tmp;
  }
  return arr;
}

function nextMultiThreshold(rng) {
  return 8 + Math.floor(rng() * 5) - 2;
}

function buildInterleavedFixtureOrder(rows, options = {}) {
  const version = options.version || BENCHMARK_FIXTURE_ORDER_VERSION;
  const seed = options.seed != null ? options.seed : BENCHMARK_FIXTURE_ORDER_SEED;
  const rng = createSeededRng(seed);

  const buckets = {
    position: [],
    item: [],
    multi_true: [],
    multi_mixed: [],
    multi_false: [],
    other: [],
  };
  for (const row of [...rows].sort((a, b) => Number(a.sequence) - Number(b.sequence))) {
    const kind = classifyScenarioKind(row.scenario || row.sourceTemplate, row.category || row.type);
    buckets[kind].push({ ...row, scenarioKind: kind });
  }

  const runLengths = shuffleInPlace([2, 3, 4, 5, 1, 3, 4, 2], rng);
  let runIdx = 0;
  const multiOrder = ['multi_true', 'multi_mixed', 'multi_false'];
  let multiIdx = 0;
  let singlesSinceMulti = 0;
  let multiThreshold = nextMultiThreshold(rng);

  const ordered = [];
  const emit = (row) => {
    if (!row) return;
    ordered.push({
      ...row,
      benchmarkSequence: ordered.length + 1,
      originalSequence: Number(row.sequence),
      scenarioKind: row.scenarioKind,
    });
  };

  const take = (kind) => {
    const q = buckets[kind];
    return q.length ? q.shift() : null;
  };

  const remainingMultis = () =>
    buckets.multi_true.length + buckets.multi_mixed.length + buckets.multi_false.length;
  const remainingSingles = () => buckets.position.length + buckets.item.length;

  const tryInjectMulti = () => {
    for (let attempt = 0; attempt < multiOrder.length; attempt += 1) {
      const kind = multiOrder[multiIdx % multiOrder.length];
      multiIdx += 1;
      const m = take(kind);
      if (m) {
        emit(m);
        singlesSinceMulti = 0;
        multiThreshold = nextMultiThreshold(rng);
        return true;
      }
    }
    return false;
  };

  const shouldInjectMultiNow = () => {
    const m = remainingMultis();
    if (m === 0) return false;
    const s = remainingSingles();
    if (s === 0) return true;
    const paced = Math.max(2, Math.floor(s / m));
    return singlesSinceMulti >= Math.min(multiThreshold, paced);
  };

  while (buckets.position.length || buckets.item.length) {
    if (shouldInjectMultiNow()) tryInjectMulti();

    const pos = take('position');
    if (pos) {
      emit(pos);
      singlesSinceMulti += 1;
    }

    const k = runLengths[runIdx % runLengths.length];
    runIdx += 1;
    for (let i = 0; i < k && buckets.item.length; i += 1) {
      if (shouldInjectMultiNow()) tryInjectMulti();
      const item = take('item');
      if (!item) break;
      emit(item);
      singlesSinceMulti += 1;
    }

    if (!pos && buckets.item.length === 0) break;
  }

  while (tryInjectMulti()) {
    /* drain remaining multis round-robin */
  }
  for (const kind of multiOrder) {
    while (buckets[kind].length) emit(take(kind));
  }
  while (buckets.other.length) emit(take('other'));

  if (ordered.length !== rows.length) {
    throw new Error(`interleave lost rows: ordered=${ordered.length} input=${rows.length}`);
  }
  return { version, seed, ordered };
}

function isMultiKind(kind) {
  return kind === 'multi_true' || kind === 'multi_mixed' || kind === 'multi_false';
}

function maxConsecutiveRuns(ordered) {
  let runKind = null;
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

function validateFixtureOrderGates(ordered, options = {}) {
  const bandSize = options.bandSize != null ? options.bandSize : 50;
  const maxPos =
    options.maxConsecutivePosition != null
      ? options.maxConsecutivePosition
      : MAX_CONSECUTIVE_POSITION;
  const maxItem =
    options.maxConsecutiveItem != null ? options.maxConsecutiveItem : MAX_CONSECUTIVE_ITEM;
  const failures = [];

  const { maxConsecutivePosition, maxConsecutiveItem } = maxConsecutiveRuns(ordered);
  if (maxConsecutivePosition > maxPos) {
    failures.push(
      `maxConsecutivePosition=${maxConsecutivePosition} exceeds limit ${maxPos}`,
    );
  }
  if (maxConsecutiveItem > maxItem) {
    failures.push(`maxConsecutiveItem=${maxConsecutiveItem} exceeds limit ${maxItem}`);
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
      if (leftoverMulti >= bandsFromHere && bandMulti === 0) {
        failures.push(`band ${bandLabel}: expected at least one multi`);
      }
    }
  }

  return { ok: failures.length === 0, failures };
}

function buildInterleavedFixtureOrderV2(rows, options = {}) {
  const version = options.version || BENCHMARK_FIXTURE_ORDER_V2;
  const seed = options.seed != null ? options.seed : BENCHMARK_FIXTURE_ORDER_V2_SEED;
  const rng = createSeededRng(seed);

  const queues = {
    position: [],
    item: [],
    multi_true: [],
    multi_mixed: [],
    multi_false: [],
    other: [],
  };
  for (const row of [...rows].sort((a, b) => Number(a.sequence) - Number(b.sequence))) {
    const kind = classifyScenarioKind(row.scenario || row.sourceTemplate, row.category || row.type);
    queues[kind].push({ ...row, scenarioKind: kind });
  }

  const remainingOf = (cat) => {
    if (cat === 'position') return queues.position.length;
    if (cat === 'item') return queues.item.length;
    if (cat === 'other') return queues.other.length;
    return queues.multi_true.length + queues.multi_mixed.length + queues.multi_false.length;
  };

  const totalOf = {
    position: remainingOf('position'),
    item: remainingOf('item'),
    multi: remainingOf('multi'),
    other: remainingOf('other'),
  };

  const preference = ['position', 'item', 'multi', 'other'];
  const rotateBy = Math.floor(rng() * preference.length);
  for (let i = 0; i < rotateBy; i += 1) {
    preference.push(preference.shift());
  }
  const posIdx = preference.indexOf('position');
  const itemIdx = preference.indexOf('item');
  if (posIdx > itemIdx && rng() < 0.5) {
    preference[itemIdx] = 'position';
    preference[posIdx] = 'item';
  }

  let multiRoundRobin = Math.floor(rng() * MULTI_KINDS.length);
  let consecutivePosition = 0;
  let consecutiveItem = 0;

  const ordered = [];
  const emit = (row, kind) => {
    ordered.push({
      ...row,
      benchmarkSequence: ordered.length + 1,
      originalSequence: Number(row.sequence),
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

  const take = (kind) => {
    const q = queues[kind];
    return q.length ? q.shift() : null;
  };

  const takeMulti = () => {
    for (let attempt = 0; attempt < MULTI_KINDS.length; attempt += 1) {
      const kind = MULTI_KINDS[multiRoundRobin % MULTI_KINDS.length];
      multiRoundRobin += 1;
      const next = take(kind);
      if (next) return { row: next, kind };
    }
    return null;
  };

  const bandSize =
    options.gateOptions && options.gateOptions.bandSize != null
      ? options.gateOptions.bandSize
      : 50;
  const totalN = rows.length;
  const numBands = totalN === 0 ? 0 : Math.ceil(totalN / bandSize);

  const canPick = (cat) => {
    if (remainingOf(cat) <= 0) return false;
    if (cat === 'position' && consecutivePosition >= MAX_CONSECUTIVE_POSITION) return false;
    if (cat === 'item' && consecutiveItem >= MAX_CONSECUTIVE_ITEM) return false;
    return true;
  };

  /** Under-representation vs global share (not largest-pile-first). */
  const scoreOf = (cat) => {
    const total = totalOf[cat];
    if (total <= 0) return -Infinity;
    const emittedOf = total - remainingOf(cat);
    const ideal = (total * (ordered.length + 1)) / totalN;
    let score = ideal - emittedOf;
    if (cat === 'item' && consecutivePosition > 0) {
      score += 0.15;
    } else if (cat === 'position' && consecutivePosition === 0 && consecutiveItem === 0) {
      score += 0.05;
    }
    return score;
  };

  const pickAmong = (candidates, enforceLimits) => {
    const eligible = candidates.filter((c) =>
      enforceLimits ? canPick(c) : remainingOf(c) > 0,
    );
    if (eligible.length === 0) return null;

    let bestScore = -Infinity;
    const tied = [];
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
    if (tied.length === 1) return tied[0];
    return tied[Math.floor(rng() * tied.length)];
  };

  const bandRequired = () => {
    const idx = ordered.length;
    const bandIndex = Math.floor(idx / bandSize);
    const bandStart = bandIndex * bandSize;
    const bandEnd = Math.min(totalN, bandStart + bandSize);
    const slotsLeftInBand = bandEnd - idx;
    const bandSoFar = ordered.slice(bandStart);
    const bandHasPos = bandSoFar.some((r) => r.scenarioKind === 'position');
    const bandHasItem = bandSoFar.some((r) => r.scenarioKind === 'item');
    const bandHasMulti = bandSoFar.some((r) => isMultiKind(r.scenarioKind));

    const leftoverPos = remainingOf('position');
    const leftoverItem = remainingOf('item');
    const leftoverMulti = remainingOf('multi');
    const bandsFromHere = numBands - bandIndex;

    const need = [];
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

  const pickCategory = () => {
    const required = bandRequired();
    if (required.length > 0) {
      const forced =
        pickAmong(required, true) ||
        (required.includes('multi') ? pickAmong(['multi'], false) : null) ||
        pickAmong(required, false);
      if (forced) return forced;
    }

    const all = ['position', 'item', 'multi', 'other'];
    return pickAmong(all, true) || pickAmong(all, false);
  };

  let remainingSlots = rows.length;
  while (remainingSlots > 0) {
    const cat = pickCategory();
    if (!cat) break;

    if (cat === 'position') {
      const row = take('position');
      if (!row) break;
      emit(row, 'position');
    } else if (cat === 'item') {
      const row = take('item');
      if (!row) break;
      emit(row, 'item');
    } else if (cat === 'multi') {
      const taken = takeMulti();
      if (!taken) break;
      emit(taken.row, taken.kind);
    } else {
      const row = take('other');
      if (!row) break;
      emit(row, 'other');
    }
    remainingSlots -= 1;
  }

  for (const kind of ['position', 'item', 'multi_true', 'multi_mixed', 'multi_false', 'other']) {
    while (queues[kind].length) emit(take(kind), kind);
  }

  if (ordered.length !== rows.length) {
    const err = new Error('BENCHMARK_FIXTURE_ORDER_INCOMPLETE');
    err.code = 'BENCHMARK_FIXTURE_ORDER_INCOMPLETE';
    err.expected = rows.length;
    err.actual = ordered.length;
    throw err;
  }

  const gates = validateFixtureOrderGates(ordered, options.gateOptions || {});
  if (!gates.ok) {
    const err = new Error('BENCHMARK_FIXTURE_ORDER_GATE_FAILED');
    err.code = 'BENCHMARK_FIXTURE_ORDER_GATE_FAILED';
    err.failures = gates.failures;
    throw err;
  }

  return { version, seed, ordered };
}

function csvEscape(value) {
  if (value == null) return '';
  const s = String(value);
  if (/[",\r\n]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

/** Mirror of toOrderedManifestCsv in benchmarkFixtureOrder.ts */
function toOrderedManifestCsv(ordered) {
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
      r.validAndesCount != null ? r.validAndesCount : '',
      r.falseLabelCount != null ? r.falseLabelCount : '',
      csvEscape(r.labelsJson),
      r.sizeBytes != null ? r.sizeBytes : '',
      r.width != null ? r.width : '',
      r.height != null ? r.height : '',
    ].join(','),
  );
  return [header, ...lines].join('\n') + '\n';
}

module.exports = {
  BENCHMARK_FIXTURE_ORDER_VERSION,
  BENCHMARK_FIXTURE_ORDER_SEED,
  BENCHMARK_FIXTURE_ORDER_V2,
  BENCHMARK_FIXTURE_ORDER_V2_SEED,
  BENCHMARK_FIXTURE_ORDER_DEFAULT_VERSION,
  BENCHMARK_FIXTURE_ORDER_DEFAULT_SEED,
  MAX_CONSECUTIVE_POSITION,
  MAX_CONSECUTIVE_ITEM,
  createSeededRng,
  classifyScenarioKind,
  buildInterleavedFixtureOrder,
  buildInterleavedFixtureOrderV2,
  validateFixtureOrderGates,
  toOrderedManifestCsv,
};
