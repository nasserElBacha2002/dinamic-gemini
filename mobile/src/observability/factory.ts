import type { Logger } from '../core/logging';
import type { SQLiteDatabase } from '../database/database';
import { createId } from '../shared/createId';
import {
  BufferedSqliteObservabilityReporter,
  SqliteObservabilityStore,
} from './sqliteStore';
import {
  CompositeObservabilityReporter,
  FlaggedObservabilityReporter,
  NoOpObservabilityReporter,
  SafeObservabilityReporter,
  StructuredObsLogReporter,
} from './reporters';
import { TimingMarkStore } from './timingMarks';
import type { ObservabilityReporter } from './types';

export interface ObservabilityStack {
  readonly reporter: ObservabilityReporter;
  readonly marks: TimingMarkStore;
  readonly store: SqliteObservabilityStore | null;
  dispose(): Promise<void>;
}

/**
 * Wire Phase 0 observability. When disabled, returns NoOp with zero overhead beyond a flag check.
 */
export function createObservabilityStack(input: {
  readonly enabled: boolean;
  readonly logger: Logger;
  readonly db: SQLiteDatabase;
}): ObservabilityStack {
  const marks = new TimingMarkStore();
  if (!input.enabled) {
    return {
      reporter: new NoOpObservabilityReporter(),
      marks,
      store: null,
      dispose: async () => undefined,
    };
  }

  const store = new SqliteObservabilityStore(input.db);
  const buffered = new BufferedSqliteObservabilityReporter(store, {
    createId,
    flushSize: 12,
    flushIntervalMs: 1500,
    onError: (err) => {
      input.logger.warn('recovery', {
        obs: true,
        obs_name: 'observability.flush_failed',
        message: err instanceof Error ? err.message : String(err),
      });
    },
  });
  const logReporter = new StructuredObsLogReporter(input.logger);
  const composite = new CompositeObservabilityReporter([buffered, logReporter]);
  const safe = new SafeObservabilityReporter(composite, (err) => {
    input.logger.warn('recovery', {
      obs: true,
      obs_name: 'observability.emit_failed',
      message: err instanceof Error ? err.message : String(err),
    });
  });
  const flagged = new FlaggedObservabilityReporter(() => true, safe);

  // Retention: prune events older than 14 days (best-effort, non-blocking).
  const cutoff = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000).toISOString();
  void store.pruneOlderThan(cutoff).catch(() => undefined);

  return {
    reporter: flagged,
    marks,
    store,
    dispose: () => buffered.dispose(),
  };
}
