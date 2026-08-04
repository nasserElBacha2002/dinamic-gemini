/**
 * Compare local confirmed/draft results vs server-side summaries (Phase 6).
 * Does not delete local values; only classifies outcomes.
 */

export type LocalRemoteReconcileOutcome =
  | 'MATCHED'
  | 'SERVER_CONFIRMED'
  | 'LOCAL_ONLY'
  | 'SERVER_ONLY'
  | 'CONFLICT'
  | 'MANUAL_RESOLUTION_REQUIRED';

export interface LocalRemoteSide {
  readonly internalCode: string | null;
  readonly quantity: number | null;
  readonly source: string | null;
}

export interface LocalRemoteReconcileItem {
  readonly capturePhotoId: string;
  readonly clientFileId: string | null;
  readonly local: LocalRemoteSide | null;
  readonly server: LocalRemoteSide | null;
  readonly outcome: LocalRemoteReconcileOutcome;
  readonly notes: string | null;
}

function normalizeCode(code: string | null | undefined): string | null {
  if (code == null) return null;
  const t = code.trim();
  return t.length === 0 ? null : t;
}

export function classifyLocalRemotePair(
  local: LocalRemoteSide | null,
  server: LocalRemoteSide | null,
): { outcome: LocalRemoteReconcileOutcome; notes: string | null } {
  if (!local && !server) {
    return { outcome: 'MANUAL_RESOLUTION_REQUIRED', notes: 'both_empty' };
  }
  if (local && !server) {
    return { outcome: 'LOCAL_ONLY', notes: null };
  }
  if (!local && server) {
    return { outcome: 'SERVER_ONLY', notes: null };
  }
  const lc = normalizeCode(local!.internalCode);
  const sc = normalizeCode(server!.internalCode);
  const lq = local!.quantity;
  const sq = server!.quantity;
  if (lc === sc && lq === sq) {
    return { outcome: 'MATCHED', notes: null };
  }
  if (lc === sc && lq !== sq) {
    return { outcome: 'CONFLICT', notes: 'quantity_mismatch' };
  }
  if (lc !== sc) {
    return { outcome: 'CONFLICT', notes: 'code_mismatch' };
  }
  return { outcome: 'MANUAL_RESOLUTION_REQUIRED', notes: 'unclassified' };
}

export function reconcileLocalRemoteResults(
  items: readonly {
    readonly capturePhotoId: string;
    readonly clientFileId: string | null;
    readonly local: LocalRemoteSide | null;
    readonly server: LocalRemoteSide | null;
  }[],
): LocalRemoteReconcileItem[] {
  return items.map((item) => {
    const { outcome, notes } = classifyLocalRemotePair(item.local, item.server);
    return {
      capturePhotoId: item.capturePhotoId,
      clientFileId: item.clientFileId,
      local: item.local,
      server: item.server,
      outcome,
      notes,
    };
  });
}
