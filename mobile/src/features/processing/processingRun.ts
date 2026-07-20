/**
 * Local processing-run entity for mobile process-aisle idempotency.
 *
 * Key shape: `mobile-process:{sessionId}:{runId}`
 * - Double-tap / network retry → same run (stable key)
 * - Mode change → new run
 * - Explicit new execution after terminal → new run
 * - App restart hydrates active runs from AsyncStorage
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

import { createUuid } from '../../core/uuid';
import type { AisleIdentificationMode } from './processingMode';
import { sanitizeIdentificationModeSelection } from './processingMode';

export type ProcessingRunStatus =
  | 'starting'
  | 'active'
  | 'succeeded'
  | 'failed'
  | 'cancelled';

export interface ProcessingRun {
  readonly id: string;
  readonly sessionId: string;
  /** null = inherited / omit identification_mode on the wire. */
  readonly identificationMode: AisleIdentificationMode | null;
  readonly idempotencyKey: string;
  readonly backendJobId: string | null;
  readonly status: ProcessingRunStatus;
  readonly createdAt: string;
  readonly updatedAt: string;
}

const ACTIVE: ReadonlySet<ProcessingRunStatus> = new Set(['starting', 'active']);
const STORAGE_KEY = 'dinamic.processing_runs.v1';

export function buildProcessRunIdempotencyKey(sessionId: string, runId: string): string {
  return `mobile-process:${sessionId}:${runId}`;
}

function modeKey(mode: AisleIdentificationMode | null | undefined): string {
  const sanitized = sanitizeIdentificationModeSelection(mode);
  return sanitized ?? 'inherited';
}

type Snapshot = {
  byId: Record<string, ProcessingRun>;
  activeBySession: Record<string, string>;
};

/** In-memory + AsyncStorage durable store. Cleared on logout. */
export class ProcessingRunStore {
  private readonly byId = new Map<string, ProcessingRun>();
  private readonly activeBySession = new Map<string, string>();
  private hydratePromise: Promise<void> | null = null;

  async ensureHydrated(): Promise<void> {
    if (!this.hydratePromise) {
      this.hydratePromise = this._hydrate();
    }
    await this.hydratePromise;
  }

  private async _hydrate(): Promise<void> {
    try {
      const raw = await AsyncStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const snap = JSON.parse(raw) as Snapshot;
      this.byId.clear();
      this.activeBySession.clear();
      for (const [id, run] of Object.entries(snap.byId || {})) {
        this.byId.set(id, run);
      }
      for (const [sessionId, runId] of Object.entries(snap.activeBySession || {})) {
        this.activeBySession.set(sessionId, runId);
      }
    } catch {
      // best-effort hydrate
    }
  }

  private async _persist(): Promise<void> {
    const snap: Snapshot = {
      byId: Object.fromEntries(this.byId.entries()),
      activeBySession: Object.fromEntries(this.activeBySession.entries()),
    };
    try {
      await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(snap));
    } catch {
      // best-effort persist
    }
  }

  clear(): void {
    this.byId.clear();
    this.activeBySession.clear();
    this.hydratePromise = Promise.resolve();
    void AsyncStorage.removeItem(STORAGE_KEY).catch(() => undefined);
  }

  get(runId: string): ProcessingRun | null {
    return this.byId.get(runId) ?? null;
  }

  getActiveForSession(sessionId: string): ProcessingRun | null {
    const id = this.activeBySession.get(sessionId);
    if (!id) return null;
    const run = this.byId.get(id);
    if (!run || !ACTIVE.has(run.status)) {
      this.activeBySession.delete(sessionId);
      return null;
    }
    return run;
  }

  /**
   * Reuse active run when mode matches; otherwise open a new run.
   * Does not mint a new UUID on every HTTP attempt — only when creating a run.
   */
  async getOrCreateForStart(
    sessionId: string,
    identificationMode: AisleIdentificationMode | null | undefined,
  ): Promise<ProcessingRun> {
    await this.ensureHydrated();
    const mode = sanitizeIdentificationModeSelection(identificationMode) ?? null;
    const existing = this.getActiveForSession(sessionId);
    if (existing && modeKey(existing.identificationMode) === modeKey(mode)) {
      return existing;
    }
    if (existing) {
      await this.markTerminal(existing.id, 'cancelled');
    }
    const now = new Date().toISOString();
    const id = createUuid();
    const run: ProcessingRun = {
      id,
      sessionId,
      identificationMode: mode,
      idempotencyKey: buildProcessRunIdempotencyKey(sessionId, id),
      backendJobId: null,
      status: 'starting',
      createdAt: now,
      updatedAt: now,
    };
    this.byId.set(id, run);
    this.activeBySession.set(sessionId, id);
    await this._persist();
    return run;
  }

  async attachBackendJob(runId: string, backendJobId: string): Promise<ProcessingRun | null> {
    await this.ensureHydrated();
    const current = this.byId.get(runId);
    if (!current) return null;
    const next: ProcessingRun = {
      ...current,
      backendJobId,
      status: 'active',
      updatedAt: new Date().toISOString(),
    };
    this.byId.set(runId, next);
    this.activeBySession.set(current.sessionId, runId);
    await this._persist();
    return next;
  }

  async markTerminal(
    runId: string,
    status: 'succeeded' | 'failed' | 'cancelled',
  ): Promise<ProcessingRun | null> {
    await this.ensureHydrated();
    const current = this.byId.get(runId);
    if (!current) return null;
    const next: ProcessingRun = {
      ...current,
      status,
      updatedAt: new Date().toISOString(),
    };
    this.byId.set(runId, next);
    if (this.activeBySession.get(current.sessionId) === runId) {
      this.activeBySession.delete(current.sessionId);
    }
    await this._persist();
    return next;
  }
}

/** Singleton used by ProcessingService (reset on logout / user change). */
export const processingRunStore = new ProcessingRunStore();
