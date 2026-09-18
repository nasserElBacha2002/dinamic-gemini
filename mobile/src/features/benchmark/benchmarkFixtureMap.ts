/**
 * Debug-only fixture correlation for a benchmark run.
 * Keyed by `${benchmarkRunId}::${photoId}` — cleaned when the run finishes.
 */

const fixtureByRunPhoto = new Map<string, string>();

function key(runId: string, photoId: string): string {
  return `${runId}::${photoId}`;
}

export function registerBenchmarkFixture(
  benchmarkRunId: string,
  photoId: string,
  fixtureId: string,
): void {
  if (!benchmarkRunId || !photoId || !fixtureId) {
    throw Object.assign(new Error('BENCHMARK_FIXTURE_MAP_INVALID'), {
      code: 'BENCHMARK_FIXTURE_MAP_INVALID',
    });
  }
  fixtureByRunPhoto.set(key(benchmarkRunId, photoId), fixtureId);
}

export function lookupBenchmarkFixture(
  benchmarkRunId: string,
  photoId: string | null | undefined,
): string | null {
  if (!photoId) return null;
  return fixtureByRunPhoto.get(key(benchmarkRunId, photoId)) ?? null;
}

export function requireBenchmarkFixture(
  benchmarkRunId: string,
  photoId: string,
): string {
  const id = lookupBenchmarkFixture(benchmarkRunId, photoId);
  if (!id) {
    throw Object.assign(new Error('BENCHMARK_FIXTURE_ID_MISSING'), {
      code: 'BENCHMARK_FIXTURE_ID_MISSING',
      photoId,
    });
  }
  return id;
}

export function clearBenchmarkFixtures(benchmarkRunId: string): void {
  const prefix = `${benchmarkRunId}::`;
  for (const k of [...fixtureByRunPhoto.keys()]) {
    if (k.startsWith(prefix)) {
      fixtureByRunPhoto.delete(k);
    }
  }
}

export function countBenchmarkFixtures(benchmarkRunId: string): number {
  const prefix = `${benchmarkRunId}::`;
  let n = 0;
  for (const k of fixtureByRunPhoto.keys()) {
    if (k.startsWith(prefix)) n += 1;
  }
  return n;
}

/** Test helper — wipe all runs. */
export function resetAllBenchmarkFixturesForTests(): void {
  fixtureByRunPhoto.clear();
}
