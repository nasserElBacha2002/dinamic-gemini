import {
  BENCHMARK_AISLE_CODE_PREFIX,
  BENCHMARK_ASSET_PREFIX,
  BENCHMARK_NAMESPACE_PREFIX,
  BENCHMARK_SESSION_PREFIX,
  isBenchmarkNamespacePath,
} from './authorizedIds';

export interface BenchmarkResourceRegistry {
  readonly benchmarkRunId: string;
  sessionId: string | null;
  aisleId: string | null;
  inventoryId: string | null;
  sandboxRelativePaths: string[];
  exportIds: string[];
}

export function createResourceRegistry(benchmarkRunId: string): BenchmarkResourceRegistry {
  return {
    benchmarkRunId,
    sessionId: null,
    aisleId: null,
    inventoryId: null,
    sandboxRelativePaths: [],
    exportIds: [],
  };
}

export function buildBenchmarkSessionId(runId: string): string {
  return `${BENCHMARK_SESSION_PREFIX}${runId}`;
}

export function buildBenchmarkAisleCode(runId: string): string {
  const short = runId.replace(/[^a-zA-Z0-9]/g, '').slice(0, 8).toUpperCase() || 'RUN';
  return `${BENCHMARK_AISLE_CODE_PREFIX}${short}`;
}

export function buildBenchmarkAssetId(sequence: number): string {
  return `${BENCHMARK_ASSET_PREFIX}${String(sequence).padStart(3, '0')}`;
}

export function buildBenchmarkSandboxRelative(runId: string, ...parts: string[]): string {
  return [BENCHMARK_NAMESPACE_PREFIX, runId, ...parts].join('/');
}

/**
 * Guard before any delete: path must belong to this run's namespace.
 */
export function assertDeletableBenchmarkPath(path: string, runId: string): void {
  if (!path || !path.trim()) {
    throw Object.assign(new Error('BENCHMARK_CLEANUP_EMPTY_PATH'), {
      code: 'BENCHMARK_CLEANUP_EMPTY_PATH',
    });
  }
  if (!runId || !runId.trim()) {
    throw Object.assign(new Error('BENCHMARK_CLEANUP_EMPTY_RUN'), {
      code: 'BENCHMARK_CLEANUP_EMPTY_RUN',
    });
  }
  if (!isBenchmarkNamespacePath(path, runId)) {
    throw Object.assign(new Error('BENCHMARK_CLEANUP_NAMESPACE_ESCAPE'), {
      code: 'BENCHMARK_CLEANUP_NAMESPACE_ESCAPE',
    });
  }
  const forbidden = ['/DCIM', '/Download', 'MediaStore', '..'];
  for (const f of forbidden) {
    if (path.includes(f)) {
      throw Object.assign(new Error('BENCHMARK_CLEANUP_FORBIDDEN_TARGET'), {
        code: 'BENCHMARK_CLEANUP_FORBIDDEN_TARGET',
      });
    }
  }
}

export function assertSessionOwnedByRun(sessionId: string, runId: string): void {
  if (!sessionId.startsWith(BENCHMARK_SESSION_PREFIX) || !sessionId.includes(runId)) {
    throw Object.assign(new Error('BENCHMARK_CLEANUP_SESSION_MISMATCH'), {
      code: 'BENCHMARK_CLEANUP_SESSION_MISMATCH',
    });
  }
}
