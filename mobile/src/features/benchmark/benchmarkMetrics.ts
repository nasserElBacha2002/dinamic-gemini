import {
  AUTHORIZED_BENCHMARK_CLIENT_ID,
  AUTHORIZED_BENCHMARK_PROFILE_NAME,
  AUTHORIZED_BENCHMARK_SUPPLIER_ROUTE_ID,
  BENCHMARK_SCHEMA_VERSION,
} from './authorizedIds';
import type { BenchmarkPhotoOutcome } from './benchmarkOutcomes';
import { lookupBenchmarkFixture } from './benchmarkFixtureMap';

export type BenchmarkExecutionContext = 'js' | 'native' | 'unknown';

export interface BenchmarkEvent {
  readonly schemaVersion: typeof BENCHMARK_SCHEMA_VERSION;
  readonly benchmarkRunId: string;
  readonly processId: string;
  readonly sessionId: string | null;
  readonly clientId: string;
  readonly supplierRouteId: string;
  readonly resolvedClientSupplierId: string | null;
  readonly resolvedProfileName: string | null;
  readonly photoId: string | null;
  readonly sequence: number | null;
  readonly fixtureId: string | null;
  readonly stage: string;
  readonly wallTimeUtc: string;
  readonly monotonicStartMs: number;
  readonly durationMs: number;
  readonly inputBytes: number | null;
  readonly outputBytes: number | null;
  readonly queueDepth: number | null;
  readonly workerConcurrency: number | null;
  readonly executionContext: BenchmarkExecutionContext;
  readonly success: boolean;
  readonly outcome: BenchmarkPhotoOutcome | string | null;
  readonly errorCode: string | null;
  readonly extras?: Readonly<Record<string, number | string | boolean | null>>;
}

export type BenchmarkEventInput = {
  readonly sessionId: string | null;
  readonly photoId?: string | null;
  readonly sequence?: number | null;
  readonly fixtureId?: string | null;
  readonly stage: string;
  readonly wallTimeUtc?: string;
  readonly monotonicStartMs: number;
  readonly durationMs: number;
  readonly inputBytes?: number | null;
  readonly outputBytes?: number | null;
  readonly queueDepth?: number | null;
  readonly workerConcurrency?: number | null;
  readonly executionContext: BenchmarkExecutionContext;
  readonly success: boolean;
  readonly outcome?: BenchmarkPhotoOutcome | string | null;
  readonly errorCode?: string | null;
  readonly resolvedClientSupplierId?: string | null;
  readonly resolvedProfileName?: string | null;
  readonly extras?: Readonly<Record<string, number | string | boolean | null>>;
};

export interface BenchmarkMetricsSink {
  emit(event: BenchmarkEventInput): void;
  readonly events: readonly BenchmarkEvent[];
  toJsonl(): string;
}

function monoNow(): number {
  const p = (globalThis as { performance?: { now(): number } }).performance;
  return typeof p?.now === 'function' ? p.now() : Date.now();
}

export function createBenchmarkMetricsSink(input: {
  readonly benchmarkRunId: string;
  readonly processId: string;
  readonly resolvedClientSupplierId: string | null;
  readonly resolvedProfileName: string | null;
}): BenchmarkMetricsSink {
  const events: BenchmarkEvent[] = [];
  return {
    get events() {
      return events;
    },
    emit(partial) {
      const photoId = partial.photoId ?? null;
      const fixtureId =
        partial.fixtureId ??
        (photoId ? lookupBenchmarkFixture(input.benchmarkRunId, photoId) : null);
      const event: BenchmarkEvent = {
        schemaVersion: BENCHMARK_SCHEMA_VERSION,
        benchmarkRunId: input.benchmarkRunId,
        processId: input.processId,
        sessionId: partial.sessionId,
        clientId: AUTHORIZED_BENCHMARK_CLIENT_ID,
        supplierRouteId: AUTHORIZED_BENCHMARK_SUPPLIER_ROUTE_ID,
        resolvedClientSupplierId:
          partial.resolvedClientSupplierId ?? input.resolvedClientSupplierId,
        resolvedProfileName: partial.resolvedProfileName ?? input.resolvedProfileName,
        photoId,
        sequence: partial.sequence ?? null,
        fixtureId,
        stage: partial.stage,
        wallTimeUtc: partial.wallTimeUtc ?? new Date().toISOString(),
        monotonicStartMs: partial.monotonicStartMs,
        durationMs: partial.durationMs,
        inputBytes: partial.inputBytes ?? null,
        outputBytes: partial.outputBytes ?? null,
        queueDepth: partial.queueDepth ?? null,
        workerConcurrency: partial.workerConcurrency ?? null,
        executionContext: partial.executionContext,
        success: partial.success,
        outcome: partial.outcome ?? null,
        errorCode: partial.errorCode ?? null,
        ...(partial.extras ? { extras: partial.extras } : {}),
      };
      events.push(event);
    },
    toJsonl() {
      return events.map((e) => JSON.stringify(sanitizeEvent(e))).join('\n') + (events.length ? '\n' : '');
    },
  };
}

/** Strip accidental sensitive keys if callers attach extras. */
export function sanitizeEvent(event: BenchmarkEvent): BenchmarkEvent {
  // Normalized lowercase only — comparisons use k.toLowerCase().
  const blocked = new Set([
    'qr',
    'payload',
    'sku',
    'quantity',
    'uri',
    'path',
    'token',
    'prompt',
    'configuration_json',
    'codevalue',
    'rawvalue',
    'code_value',
    'raw_value',
  ]);
  const pathLike =
    /file:\/\/|content:\/\/|\/data\/|\/storage\/|\/Users\//i;
  if (!event.extras) return event;
  const extras: Record<string, number | string | boolean | null> = {};
  for (const [k, v] of Object.entries(event.extras)) {
    if (blocked.has(k.toLowerCase())) continue;
    if (typeof v === 'string' && pathLike.test(v)) {
      extras[k] = '[redacted]';
      continue;
    }
    extras[k] = v;
  }
  return { ...event, extras };
}

export async function measureStage<T>(
  sink: BenchmarkMetricsSink,
  base: {
    readonly sessionId: string | null;
    readonly photoId?: string | null;
    readonly sequence?: number | null;
    readonly fixtureId?: string | null;
    readonly stage: string;
    readonly executionContext: BenchmarkExecutionContext;
    readonly inputBytes?: number | null;
    readonly queueDepth?: number | null;
    readonly workerConcurrency?: number | null;
  },
  fn: () => Promise<T>,
): Promise<T> {
  const monotonicStartMs = monoNow();
  try {
    const result = await fn();
    sink.emit({
      sessionId: base.sessionId,
      photoId: base.photoId ?? null,
      sequence: base.sequence ?? null,
      fixtureId: base.fixtureId ?? null,
      stage: base.stage,
      monotonicStartMs,
      durationMs: monoNow() - monotonicStartMs,
      inputBytes: base.inputBytes ?? null,
      outputBytes: null,
      queueDepth: base.queueDepth ?? null,
      workerConcurrency: base.workerConcurrency ?? null,
      executionContext: base.executionContext,
      success: true,
      outcome: null,
      errorCode: null,
    });
    return result;
  } catch (error) {
    const code =
      error && typeof error === 'object' && 'code' in error
        ? String((error as { code?: unknown }).code ?? 'ERROR')
        : 'ERROR';
    sink.emit({
      sessionId: base.sessionId,
      photoId: base.photoId ?? null,
      sequence: base.sequence ?? null,
      fixtureId: base.fixtureId ?? null,
      stage: base.stage,
      monotonicStartMs,
      durationMs: monoNow() - monotonicStartMs,
      inputBytes: base.inputBytes ?? null,
      outputBytes: null,
      queueDepth: base.queueDepth ?? null,
      workerConcurrency: base.workerConcurrency ?? null,
      executionContext: base.executionContext,
      success: false,
      outcome: null,
      errorCode: code.slice(0, 80),
    });
    throw error;
  }
}

export function monoNowMs(): number {
  return monoNow();
}

export function expectedProfileName(): string {
  return AUTHORIZED_BENCHMARK_PROFILE_NAME;
}
