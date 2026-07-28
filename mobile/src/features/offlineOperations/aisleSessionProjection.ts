/**
 * Phase 9 — aisle session projection + primary action (UI-facing).
 */

import type { OfflineOperationRow } from './offlineOperationTypes';

export type AisleSessionProjection = {
  readonly sessionId: string | null;
  readonly inventoryId: string | null;
  readonly aisleId: string | null;
  readonly pendingUploads: number;
  readonly pendingSyncs: number;
  readonly pendingFinalizations: number;
  readonly pendingRevisions: number;
  readonly blockedAuth: number;
  readonly conflicts: number;
  readonly terminalFailures: number;
  readonly completedOps: number;
  readonly oldestPendingAgeMs: number | null;
  readonly userStatusLabel: string;
  readonly primaryAction: PrimaryAisleAction;
};

export type PrimaryAisleAction =
  | { readonly kind: 'continue_capture'; readonly label: string }
  | { readonly kind: 'retry_uploads'; readonly label: string; readonly count: number }
  | { readonly kind: 'review_results'; readonly label: string; readonly count: number }
  | { readonly kind: 'resolve_conflict'; readonly label: string }
  | { readonly kind: 'login_required'; readonly label: string }
  | { readonly kind: 'start_server_processing'; readonly label: string }
  | { readonly kind: 'finalize_aisle'; readonly label: string }
  | { readonly kind: 'wait_connection'; readonly label: string }
  | { readonly kind: 'attention'; readonly label: string }
  | { readonly kind: 'idle'; readonly label: string };

const PENDING_ACTIVE = ['PENDING', 'READY', 'RETRY_WAIT', 'BLOCKED_DEPENDENCY'] as const;
const UPLOAD_RETRYABLE = ['PENDING', 'READY', 'RETRY_WAIT'] as const;

function countType(
  ops: readonly OfflineOperationRow[],
  type: string,
  statuses: readonly string[],
): number {
  return ops.filter((o) => o.operation_type === type && statuses.includes(o.status)).length;
}

export function buildAisleSessionProjection(input: {
  readonly sessionId: string | null;
  readonly inventoryId: string | null;
  readonly aisleId: string | null;
  readonly operations: readonly OfflineOperationRow[];
  readonly nowMs: number;
  readonly hasNetwork: boolean;
  readonly pendingLocalReviewCount?: number;
  readonly captureActive?: boolean;
}): AisleSessionProjection {
  const ops = input.operations;
  const pendingUploads = countType(ops, 'UPLOAD_ASSET', PENDING_ACTIVE);
  const retryableUploads = countType(ops, 'UPLOAD_ASSET', UPLOAD_RETRYABLE);
  const pendingSyncs = countType(ops, 'SYNC_AUTHORITATIVE_RESULT', PENDING_ACTIVE);
  const pendingFinalizations = countType(ops, 'FINALIZE_AISLE', PENDING_ACTIVE);
  const pendingRevisions =
    countType(ops, 'SYNC_AISLE_REVISION', PENDING_ACTIVE) +
    countType(ops, 'APPLY_AISLE_REVISION', PENDING_ACTIVE);
  const blockedAuth = ops.filter((o) => o.status === 'BLOCKED_AUTH').length;
  const conflicts = ops.filter((o) => o.status === 'BLOCKED_CONFLICT').length;
  const terminalFailures = ops.filter((o) => o.status === 'FAILED_TERMINAL').length;
  const completedOps = ops.filter((o) => o.status === 'COMPLETED').length;
  const runningUploads = ops.filter(
    (o) => o.operation_type === 'UPLOAD_ASSET' && o.status === 'RUNNING',
  ).length;

  let oldestPendingAgeMs: number | null = null;
  for (const op of ops) {
    if (
      !PENDING_ACTIVE.includes(op.status as (typeof PENDING_ACTIVE)[number]) &&
      op.status !== 'BLOCKED_AUTH' &&
      op.status !== 'BLOCKED_CONFLICT'
    ) {
      continue;
    }
    const age = input.nowMs - Date.parse(op.created_at);
    if (Number.isFinite(age)) {
      oldestPendingAgeMs = oldestPendingAgeMs == null ? age : Math.max(oldestPendingAgeMs, age);
    }
  }

  const reviewCount = input.pendingLocalReviewCount ?? 0;
  const primaryAction = getPrimaryAisleAction({
    captureActive: Boolean(input.captureActive),
    hasNetwork: input.hasNetwork,
    pendingUploads: retryableUploads,
    runningUploads,
    pendingSyncs,
    pendingFinalizations,
    blockedAuth,
    conflicts,
    terminalFailures,
    reviewCount,
    hasStartServerOp: ops.some(
      (o) =>
        o.operation_type === 'START_SERVER_PROCESSING' &&
        (PENDING_ACTIVE.includes(o.status as (typeof PENDING_ACTIVE)[number]) ||
          o.status === 'BLOCKED_DEPENDENCY'),
    ),
  });

  let userStatusLabel = 'Completado';
  if (input.captureActive) {
    userStatusLabel = 'Capturando';
  } else if (terminalFailures > 0) {
    userStatusLabel = 'Falló';
  } else if (conflicts > 0) {
    userStatusLabel = 'Necesita atención';
  } else if (blockedAuth > 0) {
    userStatusLabel = 'Esperando autenticación';
  } else if (!input.hasNetwork && (pendingUploads > 0 || pendingSyncs > 0)) {
    userStatusLabel = 'Pendiente de conexión';
  } else if (runningUploads > 0 || pendingUploads > 0) {
    userStatusLabel = 'Subiendo';
  } else if (pendingSyncs > 0 || pendingFinalizations > 0) {
    userStatusLabel = 'Procesando';
  } else if (ops.some((o) => o.status === 'RETRY_WAIT')) {
    userStatusLabel = 'Reintento disponible';
  } else if (ops.length === 0) {
    userStatusLabel = 'Guardado en el dispositivo';
  } else if (
    terminalFailures === 0 &&
    conflicts === 0 &&
    blockedAuth === 0 &&
    pendingUploads === 0 &&
    pendingSyncs === 0 &&
    pendingFinalizations === 0
  ) {
    userStatusLabel = 'Completado';
  } else {
    userStatusLabel = 'Necesita atención';
  }

  return {
    sessionId: input.sessionId,
    inventoryId: input.inventoryId,
    aisleId: input.aisleId,
    pendingUploads,
    pendingSyncs,
    pendingFinalizations,
    pendingRevisions,
    blockedAuth,
    conflicts,
    terminalFailures,
    completedOps,
    oldestPendingAgeMs,
    userStatusLabel,
    primaryAction,
  };
}

export function getPrimaryAisleAction(input: {
  readonly captureActive: boolean;
  readonly hasNetwork: boolean;
  readonly pendingUploads: number;
  readonly runningUploads?: number;
  readonly pendingSyncs: number;
  readonly pendingFinalizations: number;
  readonly blockedAuth: number;
  readonly conflicts: number;
  readonly terminalFailures?: number;
  readonly reviewCount: number;
  readonly hasStartServerOp: boolean;
}): PrimaryAisleAction {
  if (input.captureActive) {
    return { kind: 'continue_capture', label: 'Continuar captura' };
  }
  if ((input.terminalFailures ?? 0) > 0) {
    return { kind: 'attention', label: 'Revisar fallos' };
  }
  if (input.blockedAuth > 0) {
    return { kind: 'login_required', label: 'Iniciar sesión para continuar' };
  }
  if (input.conflicts > 0) {
    return { kind: 'resolve_conflict', label: 'Resolver conflicto' };
  }
  if (input.reviewCount > 0) {
    return {
      kind: 'review_results',
      label: `Revisar ${input.reviewCount} resultado${input.reviewCount === 1 ? '' : 's'}`,
      count: input.reviewCount,
    };
  }
  if (!input.hasNetwork && (input.pendingUploads > 0 || input.pendingSyncs > 0)) {
    return { kind: 'wait_connection', label: 'Esperando conexión' };
  }
  // Do not offer retry while uploads are RUNNING.
  if (input.pendingUploads > 0 && (input.runningUploads ?? 0) === 0) {
    return {
      kind: 'retry_uploads',
      label: `Reintentar ${input.pendingUploads} carga${input.pendingUploads === 1 ? '' : 's'}`,
      count: input.pendingUploads,
    };
  }
  if (input.hasStartServerOp) {
    return { kind: 'start_server_processing', label: 'Iniciar procesamiento servidor' };
  }
  if (input.pendingFinalizations > 0) {
    return { kind: 'finalize_aisle', label: 'Finalizar pasillo' };
  }
  return { kind: 'idle', label: 'Sin acciones pendientes' };
}
