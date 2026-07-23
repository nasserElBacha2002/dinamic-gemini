import type { Logger } from '../core/logging';
import { sanitizeObservabilityEvent } from './sanitize';
import type { ObservabilityEvent, ObservabilityReporter } from './types';

/** Always-safe no-op. */
export class NoOpObservabilityReporter implements ObservabilityReporter {
  emit(_event: ObservabilityEvent): void {
    // intentionally empty
  }
}

/**
 * Wraps any reporter so emit failures never propagate to callers.
 * Principle: observability failure != operational failure.
 */
export class SafeObservabilityReporter implements ObservabilityReporter {
  constructor(
    private readonly inner: ObservabilityReporter,
    private readonly onError?: (error: unknown) => void,
  ) {}

  emit(event: ObservabilityEvent): void {
    try {
      const sanitized = sanitizeObservabilityEvent(event);
      const result = this.inner.emit(sanitized);
      if (result && typeof (result as Promise<void>).then === 'function') {
        void (result as Promise<void>).catch((err) => {
          this.onError?.(err);
        });
      }
    } catch (err) {
      this.onError?.(err);
    }
  }
}

/** Fan-out to multiple reporters (all wrapped safely by caller). */
export class CompositeObservabilityReporter implements ObservabilityReporter {
  constructor(private readonly reporters: readonly ObservabilityReporter[]) {}

  emit(event: ObservabilityEvent): void {
    for (const r of this.reporters) {
      r.emit(event);
    }
  }
}

/**
 * Emits structured log lines via existing Logger (redaction already applied upstream).
 * Uses a dedicated event name so LogEvent union stays unchanged — fields carry obs payload.
 */
export class StructuredLogObservabilityReporter implements ObservabilityReporter {
  constructor(private readonly logger: Logger) {}

  emit(event: ObservabilityEvent): void {
    this.logger.info('error', {
      obs: true,
      obs_name: event.name,
      sessionId: event.sessionId ?? null,
      serverJobId: event.serverJobId ?? null,
      clientFileId: event.clientFileId ?? null,
      batchId: event.batchId ?? null,
      attemptId: event.attemptId ?? null,
      durationMs: event.durationMs ?? null,
      ...(event.attributes ?? {}),
    });
  }
}

/**
 * Prefer a dedicated log path: extend LogEvent would be cleaner long-term;
 * for Phase 0 we use `recovery` as a non-error carrier when `obs: true` is set,
 * avoiding polluting `error` semantics. Override with optional event name via logger.info.
 */
export class StructuredObsLogReporter implements ObservabilityReporter {
  constructor(private readonly logger: Logger) {}

  emit(event: ObservabilityEvent): void {
    this.logger.info('recovery', {
      obs: true,
      obs_name: event.name,
      sessionId: event.sessionId ?? null,
      serverJobId: event.serverJobId ?? null,
      clientFileId: event.clientFileId ?? null,
      batchId: event.batchId ?? null,
      attemptId: event.attemptId ?? null,
      durationMs: event.durationMs ?? null,
      ...(event.attributes ?? {}),
    });
  }
}

/** Flag-gated reporter: when disabled, emit is a no-op. */
export class FlaggedObservabilityReporter implements ObservabilityReporter {
  constructor(
    private readonly enabled: () => boolean,
    private readonly inner: ObservabilityReporter,
  ) {}

  emit(event: ObservabilityEvent): void {
    if (!this.enabled()) {
      return;
    }
    this.inner.emit(event);
  }
}
