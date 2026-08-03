import type { SQLiteDatabase } from 'expo-sqlite';

import type { DependencyEdge } from '../../features/offlineOperations/offlineDependencyResolver';
import { computeOfflinePayloadHash } from '../../features/offlineOperations/offlinePayloadHash';
import type {
  OfflineOperationRow,
  OfflineOperationStatus,
  OfflineOperationType,
} from '../../features/offlineOperations/offlineOperationTypes';
import { runExclusiveDbWriteWithBusyRetry } from '../sqliteWriteGate';

export type EnqueueOfflineOperationInput = {
  readonly operationId: string;
  readonly operationType: OfflineOperationType;
  readonly entityType: string;
  readonly entityId: string;
  readonly inventoryId?: string | null;
  readonly aisleId?: string | null;
  readonly assetId?: string | null;
  readonly sessionId?: string | null;
  readonly payloadJson: string;
  readonly payloadVersion?: number;
  readonly idempotencyKey: string;
  readonly status?: OfflineOperationStatus;
  readonly priority?: number;
  readonly maxAttempts?: number;
  readonly requiresNetwork?: boolean;
  readonly requiresAuth?: boolean;
  readonly dependsOnOperationIds?: readonly string[];
  readonly nowIso: string;
  readonly leaseMs?: number;
};

export type EnqueueResult =
  | { readonly kind: 'created'; readonly operationId: string }
  | { readonly kind: 'existing'; readonly operationId: string }
  | {
      readonly kind: 'payload_conflict';
      readonly operationId: string;
      readonly code: 'IDEMPOTENCY_PAYLOAD_CONFLICT';
    };

export const DEFAULT_OFFLINE_LEASE_MS = 90_000;

export class OfflineOperationRepository {
  constructor(private readonly db: SQLiteDatabase) {}

  async enqueue(input: EnqueueOfflineOperationInput): Promise<EnqueueResult> {
    const payloadVersion = input.payloadVersion ?? 1;
    const deps = [...(input.dependsOnOperationIds ?? [])];
    const payloadHash = computeOfflinePayloadHash({
      operationType: input.operationType,
      entityType: input.entityType,
      entityId: input.entityId,
      payloadVersion,
      payloadJson: input.payloadJson,
      dependsOnOperationIds: deps,
    });

    if (deps.includes(input.operationId)) {
      throw new Error('SELF_DEPENDENCY');
    }

    for (const depId of deps) {
      const parent = await this.getById(depId);
      if (!parent) {
        throw new Error(`DEPENDENCY_MISSING:${depId}`);
      }
      if (
        input.sessionId &&
        parent.session_id &&
        parent.session_id !== input.sessionId
      ) {
        throw new Error('DEPENDENCY_SESSION_MISMATCH');
      }
    }

    let result: EnqueueResult = { kind: 'created', operationId: input.operationId };

    await runExclusiveDbWriteWithBusyRetry(async () => {
      await this.db.withExclusiveTransactionAsync(async (txn) => {
        const existing = await txn.getFirstAsync<{
          operation_id: string;
          payload_hash: string | null;
        }>(
          `SELECT operation_id, payload_hash FROM offline_operations
           WHERE idempotency_key = ? LIMIT 1;`,
          input.idempotencyKey,
        );
        if (existing) {
          if (existing.payload_hash && existing.payload_hash !== payloadHash) {
            result = {
              kind: 'payload_conflict',
              operationId: existing.operation_id,
              code: 'IDEMPOTENCY_PAYLOAD_CONFLICT',
            };
            return;
          }
          result = { kind: 'existing', operationId: existing.operation_id };
          return;
        }

        const insert = await txn.runAsync(
          `INSERT OR IGNORE INTO offline_operations (
             operation_id, operation_type, entity_type, entity_id,
             inventory_id, aisle_id, asset_id, session_id,
             payload_json, payload_version, payload_hash, idempotency_key, status, priority,
             attempt_count, max_attempts, next_retry_at, last_attempt_at,
             last_error_code, last_error_message, requires_network, requires_auth,
             owner_token, lease_expires_at, heartbeat_at,
             created_at, updated_at, completed_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, NULL, NULL, NULL, NULL, ?, ?, NULL, NULL, NULL, ?, ?, NULL);`,
          input.operationId,
          input.operationType,
          input.entityType,
          input.entityId,
          input.inventoryId ?? null,
          input.aisleId ?? null,
          input.assetId ?? null,
          input.sessionId ?? null,
          input.payloadJson,
          payloadVersion,
          payloadHash,
          input.idempotencyKey,
          input.status ?? 'READY',
          input.priority ?? 100,
          input.maxAttempts ?? 12,
          input.requiresNetwork === false ? 0 : 1,
          input.requiresAuth === false ? 0 : 1,
          input.nowIso,
          input.nowIso,
        );

        if ((insert?.changes ?? 0) === 0) {
          const raced = await txn.getFirstAsync<{
            operation_id: string;
            payload_hash: string | null;
          }>(
            `SELECT operation_id, payload_hash FROM offline_operations
             WHERE idempotency_key = ? LIMIT 1;`,
            input.idempotencyKey,
          );
          if (raced?.payload_hash && raced.payload_hash !== payloadHash) {
            result = {
              kind: 'payload_conflict',
              operationId: raced.operation_id,
              code: 'IDEMPOTENCY_PAYLOAD_CONFLICT',
            };
            return;
          }
          result = {
            kind: 'existing',
            operationId: raced?.operation_id ?? input.operationId,
          };
          return;
        }

        for (const dep of deps) {
          await txn.runAsync(
            `INSERT OR IGNORE INTO offline_operation_dependencies
               (operation_id, depends_on_operation_id, created_at)
             VALUES (?, ?, ?);`,
            input.operationId,
            dep,
            input.nowIso,
          );
        }

        const eventId = `${input.operationId}:offline_operation_created:${input.nowIso}`;
        await txn.runAsync(
          `INSERT INTO offline_operation_events (event_id, operation_id, event_name, detail_json, created_at)
           VALUES (?, ?, ?, ?, ?);`,
          eventId,
          input.operationId,
          'offline_operation_created',
          null,
          input.nowIso,
        );
        result = { kind: 'created', operationId: input.operationId };
      });
    });

    return result;
  }

  async getById(operationId: string): Promise<OfflineOperationRow | null> {
    return (
      (await this.db.getFirstAsync<OfflineOperationRow>(
        `SELECT * FROM offline_operations WHERE operation_id = ? LIMIT 1;`,
        operationId,
      )) ?? null
    );
  }

  async getByIdempotencyKey(key: string): Promise<OfflineOperationRow | null> {
    return (
      (await this.db.getFirstAsync<OfflineOperationRow>(
        `SELECT * FROM offline_operations WHERE idempotency_key = ? LIMIT 1;`,
        key,
      )) ?? null
    );
  }

  async listActive(limit = 500): Promise<OfflineOperationRow[]> {
    const rows = await this.db.getAllAsync<OfflineOperationRow>(
      `SELECT * FROM offline_operations
       WHERE status NOT IN ('COMPLETED', 'FAILED_TERMINAL', 'CANCELED')
       ORDER BY priority ASC, created_at ASC
       LIMIT ?;`,
      limit,
    );
    return rows ?? [];
  }

  /**
   * Eligible children whose parents are COMPLETED (SQL joins completed parents).
   */
  async listEligibleRunnable(input: {
    readonly nowIso: string;
    readonly hasNetwork: boolean;
    readonly hasAuth: boolean;
    readonly limit: number;
  }): Promise<OfflineOperationRow[]> {
    const rows = await this.db.getAllAsync<OfflineOperationRow>(
      `SELECT child.*
       FROM offline_operations child
       WHERE child.status IN ('PENDING', 'READY', 'RETRY_WAIT', 'BLOCKED_DEPENDENCY')
         AND (child.next_retry_at IS NULL OR child.next_retry_at <= ?)
         AND (? = 1 OR child.requires_network = 0)
         AND (? = 1 OR child.requires_auth = 0)
         AND NOT EXISTS (
           SELECT 1
           FROM offline_operation_dependencies dependency
           LEFT JOIN offline_operations parent
             ON parent.operation_id = dependency.depends_on_operation_id
           WHERE dependency.operation_id = child.operation_id
             AND (
               parent.operation_id IS NULL
               OR parent.status <> 'COMPLETED'
             )
         )
       ORDER BY child.priority ASC, child.created_at ASC
       LIMIT ?;`,
      input.nowIso,
      input.hasNetwork ? 1 : 0,
      input.hasAuth ? 1 : 0,
      input.limit,
    );
    return rows ?? [];
  }

  async listBlockedByBrokenDependencies(): Promise<
    Array<{
      readonly child: OfflineOperationRow;
      readonly parentStatus: string | null;
      readonly parentId: string;
    }>
  > {
    const rows = await this.db.getAllAsync<{
      child_id: string;
      parent_id: string;
      parent_status: string | null;
    }>(
      `SELECT child.operation_id AS child_id,
              dependency.depends_on_operation_id AS parent_id,
              parent.status AS parent_status
       FROM offline_operations child
       INNER JOIN offline_operation_dependencies dependency
         ON dependency.operation_id = child.operation_id
       LEFT JOIN offline_operations parent
         ON parent.operation_id = dependency.depends_on_operation_id
       WHERE child.status NOT IN ('COMPLETED', 'FAILED_TERMINAL', 'CANCELED')
         AND (
           parent.operation_id IS NULL
           OR parent.status IN ('FAILED_TERMINAL', 'CANCELED')
         );`,
    );
    const out: Array<{
      child: OfflineOperationRow;
      parentStatus: string | null;
      parentId: string;
    }> = [];
    for (const row of rows ?? []) {
      const child = await this.getById(row.child_id);
      if (child) {
        out.push({
          child,
          parentStatus: row.parent_status,
          parentId: row.parent_id,
        });
      }
    }
    return out;
  }

  async listForSession(sessionId: string): Promise<OfflineOperationRow[]> {
    const rows = await this.db.getAllAsync<OfflineOperationRow>(
      `SELECT * FROM offline_operations WHERE session_id = ? ORDER BY created_at ASC;`,
      sessionId,
    );
    return rows ?? [];
  }

  async listForAisle(inventoryId: string, aisleId: string): Promise<OfflineOperationRow[]> {
    const rows = await this.db.getAllAsync<OfflineOperationRow>(
      `SELECT * FROM offline_operations
       WHERE inventory_id = ? AND aisle_id = ?
       ORDER BY created_at ASC;`,
      inventoryId,
      aisleId,
    );
    return rows ?? [];
  }

  async listDependencies(operationIds: readonly string[]): Promise<DependencyEdge[]> {
    if (operationIds.length === 0) {
      return [];
    }
    const placeholders = operationIds.map(() => '?').join(',');
    const rows = await this.db.getAllAsync<DependencyEdge>(
      `SELECT operation_id, depends_on_operation_id
       FROM offline_operation_dependencies
       WHERE operation_id IN (${placeholders});`,
      ...operationIds,
    );
    return rows ?? [];
  }

  async claim(
    operationId: string,
    ownerToken: string,
    nowIso: string,
    leaseMs = DEFAULT_OFFLINE_LEASE_MS,
  ): Promise<boolean> {
    const leaseExpires = new Date(Date.parse(nowIso) + leaseMs).toISOString();
    const result = await this.db.runAsync(
      `UPDATE offline_operations
       SET status = 'RUNNING',
           owner_token = ?,
           lease_expires_at = ?,
           heartbeat_at = ?,
           attempt_count = attempt_count + 1,
           last_attempt_at = ?,
           updated_at = ?
       WHERE operation_id = ?
         AND status IN ('PENDING', 'READY', 'RETRY_WAIT', 'BLOCKED_DEPENDENCY')
         AND (
           lease_expires_at IS NULL
           OR lease_expires_at < ?
         );`,
      ownerToken,
      leaseExpires,
      nowIso,
      nowIso,
      nowIso,
      operationId,
      nowIso,
    );
    return (result?.changes ?? 0) === 1;
  }

  async releaseLease(operationId: string, ownerToken: string, nowIso: string): Promise<void> {
    await this.db.runAsync(
      `UPDATE offline_operations
       SET owner_token = NULL, lease_expires_at = NULL, heartbeat_at = NULL, updated_at = ?
       WHERE operation_id = ? AND owner_token = ?;`,
      nowIso,
      operationId,
      ownerToken,
    );
  }

  async updateStatus(
    operationId: string,
    status: OfflineOperationStatus,
    nowIso: string,
    patch?: {
      readonly nextRetryAt?: string | null;
      readonly lastErrorCode?: string | null;
      readonly lastErrorMessage?: string | null;
      readonly incrementAttempt?: boolean;
      readonly completed?: boolean;
      readonly clearLease?: boolean;
    },
  ): Promise<void> {
    await this.db.runAsync(
      `UPDATE offline_operations
       SET status = ?,
           next_retry_at = ?,
           last_error_code = ?,
           last_error_message = ?,
           attempt_count = attempt_count + ?,
           last_attempt_at = CASE WHEN ? = 1 THEN ? ELSE last_attempt_at END,
           completed_at = CASE WHEN ? = 1 THEN ? ELSE completed_at END,
           owner_token = CASE WHEN ? = 1 THEN NULL ELSE owner_token END,
           lease_expires_at = CASE WHEN ? = 1 THEN NULL ELSE lease_expires_at END,
           heartbeat_at = CASE WHEN ? = 1 THEN NULL ELSE heartbeat_at END,
           updated_at = ?
       WHERE operation_id = ?;`,
      status,
      patch?.nextRetryAt ?? null,
      patch?.lastErrorCode ?? null,
      patch?.lastErrorMessage ?? null,
      patch?.incrementAttempt ? 1 : 0,
      patch?.incrementAttempt ? 1 : 0,
      nowIso,
      patch?.completed ? 1 : 0,
      nowIso,
      patch?.clearLease !== false ? 1 : 0,
      patch?.clearLease !== false ? 1 : 0,
      patch?.clearLease !== false ? 1 : 0,
      nowIso,
      operationId,
    );
  }

  /** Recover RUNNING only when lease expired (or null lease on legacy rows). */
  async recoverExpiredLeases(nowIso: string): Promise<number> {
    const result = await this.db.runAsync(
      `UPDATE offline_operations
       SET status = 'READY',
           owner_token = NULL,
           lease_expires_at = NULL,
           heartbeat_at = NULL,
           updated_at = ?,
           last_error_code = 'RECOVERED_EXPIRED_LEASE'
       WHERE status = 'RUNNING'
         AND (lease_expires_at IS NULL OR lease_expires_at < ?);`,
      nowIso,
      nowIso,
    );
    return result?.changes ?? 0;
  }

  async blockAuthWithoutToken(nowIso: string): Promise<number> {
    const result = await this.db.runAsync(
      `UPDATE offline_operations
       SET status = 'BLOCKED_AUTH', updated_at = ?, last_error_code = 'AUTH_REQUIRED'
       WHERE requires_auth = 1
         AND status IN ('PENDING', 'READY', 'RETRY_WAIT', 'RUNNING');`,
      nowIso,
    );
    return result?.changes ?? 0;
  }

  async unblockAuth(nowIso: string): Promise<number> {
    const result = await this.db.runAsync(
      `UPDATE offline_operations
       SET status = 'READY', updated_at = ?, last_error_code = NULL, last_error_message = NULL
       WHERE status = 'BLOCKED_AUTH';`,
      nowIso,
    );
    return result?.changes ?? 0;
  }

  async cancel(operationId: string, nowIso: string): Promise<void> {
    await this.updateStatus(operationId, 'CANCELED', nowIso, { completed: true });
    await this.appendEvent(operationId, 'offline_operation_canceled', null, nowIso);
  }

  async recordAttempt(input: {
    readonly attemptId: string;
    readonly operationId: string;
    readonly attemptNumber: number;
    readonly startedAt: string;
    readonly finishedAt: string;
    readonly outcome: string;
    readonly errorCode?: string | null;
    readonly errorMessage?: string | null;
  }): Promise<void> {
    await this.db.runAsync(
      `INSERT INTO offline_operation_attempts (
         attempt_id, operation_id, attempt_number, started_at, finished_at,
         outcome, error_code, error_message
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);`,
      input.attemptId,
      input.operationId,
      input.attemptNumber,
      input.startedAt,
      input.finishedAt,
      input.outcome,
      input.errorCode ?? null,
      input.errorMessage ?? null,
    );
  }

  async appendEvent(
    operationId: string,
    eventName: string,
    detailJson: string | null,
    nowIso: string,
  ): Promise<void> {
    const eventId = `${operationId}:${eventName}:${nowIso}:${Math.random().toString(36).slice(2, 8)}`;
    await this.db.runAsync(
      `INSERT INTO offline_operation_events (event_id, operation_id, event_name, detail_json, created_at)
       VALUES (?, ?, ?, ?, ?);`,
      eventId,
      operationId,
      eventName,
      detailJson,
      nowIso,
    );
  }

  async purgeRetention(input: {
    readonly completedBeforeIso: string;
    readonly failedBeforeIso: string;
    readonly eventBeforeIso: string;
  }): Promise<{ operations: number; events: number; attempts: number }> {
    const ops = await this.db.runAsync(
      `DELETE FROM offline_operations
       WHERE (
         (status IN ('COMPLETED', 'CANCELED') AND completed_at IS NOT NULL AND completed_at < ?)
         OR (status = 'FAILED_TERMINAL' AND updated_at < ?)
       )
       AND operation_id NOT IN (
         SELECT depends_on_operation_id FROM offline_operation_dependencies
       )
       AND operation_id NOT IN (
         SELECT operation_id FROM offline_operation_dependencies
       );`,
      input.completedBeforeIso,
      input.failedBeforeIso,
    );
    const events = await this.db.runAsync(
      `DELETE FROM offline_operation_events WHERE created_at < ?;`,
      input.eventBeforeIso,
    );
    const attempts = await this.db.runAsync(
      `DELETE FROM offline_operation_attempts
       WHERE finished_at IS NOT NULL AND finished_at < ?;`,
      input.eventBeforeIso,
    );
    return {
      operations: ops?.changes ?? 0,
      events: events?.changes ?? 0,
      attempts: attempts?.changes ?? 0,
    };
  }
}
