/**
 * Per-session barrier for capture producers (onPhotoStable / enqueue work).
 * Does not mix sessions on a single global Promise.
 */

export class SessionProducerBarrierError extends Error {
  readonly code: 'PRODUCER_BARRIER_TIMEOUT' | 'PRODUCER_BARRIER_CLOSED';
  constructor(
    code: SessionProducerBarrierError['code'],
    message: string,
  ) {
    super(message);
    this.name = 'SessionProducerBarrierError';
    this.code = code;
  }
}

interface SessionBarrierState {
  active: number;
  closed: boolean;
  waiters: Array<{
    resolve: () => void;
    reject: (error: Error) => void;
    timer: ReturnType<typeof setTimeout> | null;
  }>;
}

/**
 * Tracks in-flight producer work per capture_session_id.
 * begin → work → end (finally). After closeAdmission, new begin() throws.
 */
export class SessionProducerBarrier {
  private readonly sessions = new Map<string, SessionBarrierState>();

  private state(sessionId: string): SessionBarrierState {
    let s = this.sessions.get(sessionId);
    if (!s) {
      s = { active: 0, closed: false, waiters: [] };
      this.sessions.set(sessionId, s);
    }
    return s;
  }

  /**
   * Register producer work. Must pair with end() in finally when true.
   * Returns false if admission is already closed (caller should skip new work).
   */
  begin(sessionId: string): boolean {
    const s = this.state(sessionId);
    if (s.closed) {
      return false;
    }
    s.active += 1;
    return true;
  }

  end(sessionId: string): void {
    const s = this.sessions.get(sessionId);
    if (!s || s.active <= 0) {
      return;
    }
    s.active -= 1;
    if (s.active === 0) {
      this.flushWaiters(s);
    }
  }

  /** Prevent new producers; in-flight work may still complete. */
  closeAdmission(sessionId: string): void {
    const s = this.state(sessionId);
    s.closed = true;
    if (s.active === 0) {
      this.flushWaiters(s);
    }
  }

  isClosed(sessionId: string): boolean {
    return this.sessions.get(sessionId)?.closed === true;
  }

  activeCount(sessionId: string): number {
    return this.sessions.get(sessionId)?.active ?? 0;
  }

  /**
   * Wait until active producers for this session reach zero.
   * Uses monotonic Date.now() delta for timeout (best available on RN).
   */
  async waitUntilIdle(
    sessionId: string,
    timeoutMs: number,
  ): Promise<void> {
    const s = this.state(sessionId);
    if (s.active === 0) {
      return;
    }
    await new Promise<void>((resolve, reject) => {
      const timer =
        timeoutMs > 0
          ? setTimeout(() => {
              const idx = s.waiters.findIndex((w) => w.resolve === resolve);
              if (idx >= 0) s.waiters.splice(idx, 1);
              reject(
                new SessionProducerBarrierError(
                  'PRODUCER_BARRIER_TIMEOUT',
                  `Producer barrier timeout after ${timeoutMs}ms (${s.active} active)`,
                ),
              );
            }, timeoutMs)
          : null;
      s.waiters.push({ resolve, reject, timer });
      if (s.active === 0) {
        this.flushWaiters(s);
      }
    });
  }

  /** Drop barrier state when a session is deleted / purged. */
  clear(sessionId: string): void {
    const s = this.sessions.get(sessionId);
    if (!s) return;
    for (const w of s.waiters) {
      if (w.timer) clearTimeout(w.timer);
      w.resolve();
    }
    this.sessions.delete(sessionId);
  }

  /** Re-open admission (tests / recovery after failed finish). */
  reopen(sessionId: string): void {
    const s = this.state(sessionId);
    s.closed = false;
  }

  private flushWaiters(s: SessionBarrierState): void {
    const waiters = s.waiters.splice(0, s.waiters.length);
    for (const w of waiters) {
      if (w.timer) clearTimeout(w.timer);
      w.resolve();
    }
  }
}
