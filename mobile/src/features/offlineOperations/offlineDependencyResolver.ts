/**
 * Phase 9 — dependency resolution (pure).
 */

import {
  isTerminalStatus,
  type OfflineOperationRow,
  type OfflineOperationStatus,
} from './offlineOperationTypes';

export type DependencyEdge = {
  readonly operation_id: string;
  readonly depends_on_operation_id: string;
};

export function dependenciesSatisfied(
  operationId: string,
  edges: readonly DependencyEdge[],
  byId: ReadonlyMap<string, OfflineOperationRow>,
): { readonly ok: boolean; readonly blockedBy: readonly string[] } {
  const deps = edges.filter((e) => e.operation_id === operationId);
  const blockedBy: string[] = [];
  for (const edge of deps) {
    const parent = byId.get(edge.depends_on_operation_id);
    if (!parent || parent.status !== 'COMPLETED') {
      blockedBy.push(edge.depends_on_operation_id);
    }
  }
  return { ok: blockedBy.length === 0, blockedBy };
}

export function selectEligibleOperations(input: {
  readonly operations: readonly OfflineOperationRow[];
  readonly edges: readonly DependencyEdge[];
  readonly nowIso: string;
  readonly hasNetwork: boolean;
  readonly hasAuth: boolean;
  readonly limit: number;
}): OfflineOperationRow[] {
  const byId = new Map(input.operations.map((o) => [o.operation_id, o]));
  const runnable = input.operations
    .filter((op) => {
      if (op.status === 'PENDING' || op.status === 'READY') {
        return true;
      }
      if (op.status === 'RETRY_WAIT') {
        return !op.next_retry_at || op.next_retry_at <= input.nowIso;
      }
      return false;
    })
    .filter((op) => {
      if (op.requires_network && !input.hasNetwork) {
        return false;
      }
      if (op.requires_auth && !input.hasAuth) {
        return false;
      }
      return true;
    })
    .filter((op) => dependenciesSatisfied(op.operation_id, input.edges, byId).ok)
    .sort((a, b) => {
      if (a.priority !== b.priority) {
        return a.priority - b.priority;
      }
      return a.created_at.localeCompare(b.created_at);
    });

  return runnable.slice(0, Math.max(0, input.limit));
}

export function recoverAbandonedRunningStatus(
  status: OfflineOperationStatus,
): OfflineOperationStatus | null {
  if (status === 'RUNNING') {
    return 'READY';
  }
  return null;
}

export function shouldBlockForDependency(
  operationId: string,
  edges: readonly DependencyEdge[],
  byId: ReadonlyMap<string, OfflineOperationRow>,
): boolean {
  const { ok } = dependenciesSatisfied(operationId, edges, byId);
  if (ok) {
    return false;
  }
  // If a dependency is terminal-failed, still block (caller may mark conflict/terminal).
  const deps = edges.filter((e) => e.operation_id === operationId);
  for (const edge of deps) {
    const parent = byId.get(edge.depends_on_operation_id);
    if (parent && isTerminalStatus(parent.status) && parent.status !== 'COMPLETED') {
      return true;
    }
  }
  return true;
}
