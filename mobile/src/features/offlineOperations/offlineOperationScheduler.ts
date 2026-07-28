/**
 * Phase 9 corrections — central offline scheduler with claim/lease, aisle serialization,
 * terminal dependency propagation, and parallel independent ops.
 */

import type { Logger } from '../../core/logging';
import { createId } from '../../shared/createId';
import type { OfflineOperationRepository } from '../../database/repositories/offlineOperationRepository';
import { decodePayloadForOperation } from './offlinePayloads';
import {
  classifyHttpOrNetworkError,
  type OfflineOperationRow,
  type OfflineOperationType,
} from './offlineOperationTypes';
import { nextRetryIso } from './offlineRetryPolicy';

export type OfflineExecutorResult =
  | { readonly outcome: 'completed' }
  | {
      readonly outcome: 'retryable' | 'terminal' | 'conflict' | 'auth' | 'dependency';
      readonly code: string;
      readonly message: string;
    };

export type OfflineOperationExecutor = {
  readonly type: OfflineOperationType;
  execute(op: OfflineOperationRow): Promise<OfflineExecutorResult>;
};

export type OfflineSchedulerDeps = {
  readonly repo: OfflineOperationRepository;
  readonly logger: Logger;
  readonly executors: ReadonlyMap<OfflineOperationType, OfflineOperationExecutor>;
  readonly getHasNetwork: () => boolean;
  readonly getHasAuth: () => Promise<boolean>;
  readonly concurrency?: number;
  readonly tickIntervalMs?: number;
  readonly onWakeNative?: () => Promise<void>;
};

function aisleKey(op: OfflineOperationRow): string {
  return `${op.inventory_id ?? ''}:${op.aisle_id ?? ''}`;
}

const AISLE_SERIAL_TYPES = new Set<OfflineOperationType>([
  'APPLY_LOCAL_RESULTS',
  'FINALIZE_AISLE',
  'START_SERVER_PROCESSING',
  'APPLY_AISLE_REVISION',
  'ADOPT_SERVER_PROPOSALS',
]);

export class OfflineOperationScheduler {
  private timer: ReturnType<typeof setInterval> | null = null;
  private running = false;
  private readonly concurrency: number;
  private readonly tickIntervalMs: number;
  private readonly aisleLocks = new Set<string>();

  constructor(private readonly deps: OfflineSchedulerDeps) {
    this.concurrency = deps.concurrency ?? 2;
    this.tickIntervalMs = deps.tickIntervalMs ?? 5_000;
  }

  start(): void {
    if (this.timer) {
      return;
    }
    this.timer = setInterval(() => {
      void this.tick();
    }, this.tickIntervalMs);
    void this.recoverAndTick();
  }

  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  async recoverAndTick(): Promise<void> {
    const nowIso = new Date().toISOString();
    const recovered = await this.deps.repo.recoverExpiredLeases(nowIso);
    await this.propagateTerminalDependencies(nowIso);
    if (recovered > 0) {
      this.deps.logger.info('recovery', {
        obs: true,
        obs_name: 'offline_recovery_completed',
        recovered,
      });
      await this.deps.onWakeNative?.();
    }
    await this.tick();
  }

  async onAuthRestored(): Promise<void> {
    const nowIso = new Date().toISOString();
    await this.deps.repo.unblockAuth(nowIso);
    this.deps.logger.info('recovery', {
      obs: true,
      obs_name: 'AUTH_STATE_AUTHENTICATED',
    });
    await this.tick();
  }

  async onAuthMissing(): Promise<void> {
    const nowIso = new Date().toISOString();
    await this.deps.repo.blockAuthWithoutToken(nowIso);
  }

  async tick(): Promise<void> {
    if (this.running) {
      return;
    }
    this.running = true;
    try {
      const nowIso = new Date().toISOString();
      await this.propagateTerminalDependencies(nowIso);
      const hasNetwork = this.deps.getHasNetwork();
      const hasAuth = await this.deps.getHasAuth();
      if (!hasAuth) {
        await this.deps.repo.blockAuthWithoutToken(nowIso);
      }

      const eligible = await this.deps.repo.listEligibleRunnable({
        nowIso,
        hasNetwork,
        hasAuth,
        limit: this.concurrency * 4,
      });

      const selected: OfflineOperationRow[] = [];
      const usedAisles = new Set<string>();
      for (const op of eligible) {
        if (selected.length >= this.concurrency) {
          break;
        }
        if (AISLE_SERIAL_TYPES.has(op.operation_type)) {
          const key = aisleKey(op);
          if (usedAisles.has(key) || this.aisleLocks.has(key)) {
            continue;
          }
          usedAisles.add(key);
        }
        selected.push(op);
      }

      await Promise.all(selected.map((op) => this.runOne(op, nowIso)));
    } catch (error) {
      this.deps.logger.warn('recovery', {
        obs: true,
        obs_name: 'offline_operation_retry',
        message: error instanceof Error ? error.message : String(error),
      });
    } finally {
      this.running = false;
    }
  }

  private async propagateTerminalDependencies(nowIso: string): Promise<void> {
    const broken = await this.deps.repo.listBlockedByBrokenDependencies();
    for (const item of broken) {
      if (item.parentStatus === null) {
        await this.deps.repo.updateStatus(item.child.operation_id, 'FAILED_TERMINAL', nowIso, {
          lastErrorCode: 'DEPENDENCY_DATA_CORRUPT',
          lastErrorMessage: `Missing parent ${item.parentId}`,
          completed: true,
        });
        continue;
      }
      if (item.parentStatus === 'FAILED_TERMINAL') {
        await this.deps.repo.updateStatus(item.child.operation_id, 'FAILED_TERMINAL', nowIso, {
          lastErrorCode: 'DEPENDENCY_FAILED_TERMINAL',
          lastErrorMessage: `Parent ${item.parentId} failed`,
          completed: true,
        });
        continue;
      }
      if (item.parentStatus === 'CANCELED') {
        await this.deps.repo.updateStatus(item.child.operation_id, 'CANCELED', nowIso, {
          lastErrorCode: 'DEPENDENCY_CANCELED',
          lastErrorMessage: `Parent ${item.parentId} canceled`,
          completed: true,
        });
      }
    }
  }

  private async runOne(op: OfflineOperationRow, nowIso: string): Promise<void> {
    const lockKey = AISLE_SERIAL_TYPES.has(op.operation_type) ? aisleKey(op) : null;
    if (lockKey) {
      if (this.aisleLocks.has(lockKey)) {
        return;
      }
      this.aisleLocks.add(lockKey);
    }
    const ownerToken = createId();
    try {
      try {
        decodePayloadForOperation(op.operation_type, op.payload_version, op.payload_json);
      } catch {
        await this.deps.repo.updateStatus(op.operation_id, 'FAILED_TERMINAL', nowIso, {
          lastErrorCode: 'UNSUPPORTED_PAYLOAD_VERSION',
          lastErrorMessage: `Unsupported payload v${op.payload_version}`,
          completed: true,
        });
        return;
      }

      const claimed = await this.deps.repo.claim(op.operation_id, ownerToken, nowIso);
      if (!claimed) {
        return;
      }

      const executor = this.deps.executors.get(op.operation_type);
      if (!executor) {
        await this.deps.repo.updateStatus(op.operation_id, 'FAILED_TERMINAL', nowIso, {
          lastErrorCode: 'NO_EXECUTOR',
          lastErrorMessage: `No executor for ${op.operation_type}`,
          completed: true,
        });
        return;
      }

      await this.deps.repo.appendEvent(
        op.operation_id,
        'offline_operation_started',
        null,
        nowIso,
      );

      const startedAt = nowIso;
      const attemptNumber = op.attempt_count + 1;
      let result: OfflineExecutorResult;
      try {
        result = await executor.execute(op);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        const klass = classifyHttpOrNetworkError({ message });
        result = { outcome: klass, code: 'EXECUTOR_THREW', message };
      }
      const finishedAt = new Date().toISOString();
      await this.deps.repo.recordAttempt({
        attemptId: createId(),
        operationId: op.operation_id,
        attemptNumber,
        startedAt,
        finishedAt,
        outcome: result.outcome,
        errorCode: result.outcome === 'completed' ? null : result.code,
        errorMessage: result.outcome === 'completed' ? null : result.message,
      });

      if (result.outcome === 'completed') {
        await this.deps.repo.updateStatus(op.operation_id, 'COMPLETED', finishedAt, {
          completed: true,
        });
        await this.deps.repo.appendEvent(
          op.operation_id,
          'offline_operation_completed',
          null,
          finishedAt,
        );
        return;
      }

      if (result.outcome === 'auth') {
        await this.deps.repo.updateStatus(op.operation_id, 'BLOCKED_AUTH', finishedAt, {
          lastErrorCode: result.code,
          lastErrorMessage: result.message,
        });
        return;
      }

      if (result.outcome === 'conflict') {
        await this.deps.repo.updateStatus(op.operation_id, 'BLOCKED_CONFLICT', finishedAt, {
          lastErrorCode: result.code,
          lastErrorMessage: result.message,
        });
        await this.deps.repo.appendEvent(
          op.operation_id,
          'offline_operation_conflict',
          JSON.stringify({ code: result.code }),
          finishedAt,
        );
        return;
      }

      if (result.outcome === 'dependency') {
        await this.deps.repo.updateStatus(op.operation_id, 'BLOCKED_DEPENDENCY', finishedAt, {
          lastErrorCode: result.code,
          lastErrorMessage: result.message,
        });
        return;
      }

      if (result.outcome === 'terminal' || attemptNumber >= op.max_attempts) {
        await this.deps.repo.updateStatus(op.operation_id, 'FAILED_TERMINAL', finishedAt, {
          lastErrorCode: result.code,
          lastErrorMessage: result.message,
          completed: true,
        });
        await this.deps.repo.appendEvent(
          op.operation_id,
          'offline_operation_terminal_failed',
          JSON.stringify({ code: result.code }),
          finishedAt,
        );
        return;
      }

      const retryAt = nextRetryIso(Date.now(), attemptNumber);
      await this.deps.repo.updateStatus(op.operation_id, 'RETRY_WAIT', finishedAt, {
        nextRetryAt: retryAt,
        lastErrorCode: result.code,
        lastErrorMessage: result.message,
      });
      await this.deps.repo.appendEvent(
        op.operation_id,
        'offline_operation_retry',
        JSON.stringify({ next_retry_at: retryAt }),
        finishedAt,
      );
    } finally {
      if (lockKey) {
        this.aisleLocks.delete(lockKey);
      }
    }
  }
}
