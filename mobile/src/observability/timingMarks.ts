import { createMonotonicClock, type MonotonicClock } from './clock';

/**
 * In-memory monotonic marks for correlation across prepare/upload/process within a process life.
 * Not a source of truth after kill — events in SQLite carry absolute timestamps for reconstruction.
 */
export class TimingMarkStore {
  private readonly marks = new Map<string, number>();

  constructor(private readonly clock: MonotonicClock = createMonotonicClock()) {}

  mark(key: string): number {
    const t = this.clock.nowMs();
    this.marks.set(key, t);
    return t;
  }

  get(key: string): number | undefined {
    return this.marks.get(key);
  }

  takeElapsedMs(key: string): number | null {
    const started = this.marks.get(key);
    if (started == null) {
      return null;
    }
    return Math.max(0, Math.round(this.clock.nowMs() - started));
  }

  clear(key: string): void {
    this.marks.delete(key);
  }

  clearPrefix(prefix: string): void {
    for (const key of [...this.marks.keys()]) {
      if (key.startsWith(prefix)) {
        this.marks.delete(key);
      }
    }
  }
}

export function photoMarkKey(sessionId: string, clientFileId: string, stage: string): string {
  return `photo:${sessionId}:${clientFileId}:${stage}`;
}

export function sessionMarkKey(sessionId: string, stage: string): string {
  return `session:${sessionId}:${stage}`;
}

export function batchMarkKey(batchId: string, stage: string): string {
  return `batch:${batchId}:${stage}`;
}
