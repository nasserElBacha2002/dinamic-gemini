import type { FeatureFlags } from '../../core/featureFlags';
import type { LocalDetectionDraftRepository } from '../../database/repositories/localDetectionDraftRepository';
import type { Logger } from '../../core/logging';
import {
  emitObservability,
  type ObservabilityReporter,
} from '../../observability';
import type { PreliminaryReconciliationApi } from './preliminaryReconciliationApi';

export interface ReconciliationSummary {
  readonly total: number;
  readonly comparable: number;
  readonly notComparable: number;
  readonly serverAgreementRate: number | null;
  readonly authorityNotice: string;
  readonly byOutcome: Readonly<Record<string, number>>;
}

export interface ReconciliationQueryServiceOptions {
  readonly api: PreliminaryReconciliationApi;
  readonly drafts: LocalDetectionDraftRepository;
  readonly flags: FeatureFlags;
  readonly logger: Logger;
  readonly observability?: ObservabilityReporter | null;
}

/**
 * Mobile diagnostic query — never computes authoritative outcomes locally.
 * Server comparison is the only source of truth for reconciliation rows.
 */
export class ReconciliationQueryService {
  constructor(private readonly options: ReconciliationQueryServiceOptions) {}

  isViewEnabled(): boolean {
    return this.options.flags.mobilePreliminaryReconciliationView === true;
  }

  /** UI-only; reconcile may run server-side without this. */
  isEnabled(): boolean {
    return this.isViewEnabled();
  }

  canTrigger(): boolean {
    return this.options.flags.mobilePreliminaryReconciliationTrigger === true;
  }

  async fetchForAisle(
    inventoryId: string,
    aisleId: string,
    jobId?: string,
  ): Promise<ReconciliationSummary | null> {
    if (!this.isViewEnabled()) {
      return null;
    }
    const res = await this.options.api.listForAisle(inventoryId, aisleId, {
      ...(jobId ? { jobId } : {}),
      limit: 200,
    });
    const byOutcome: Record<string, number> = {};
    for (const item of res.items) {
      byOutcome[item.outcome] = (byOutcome[item.outcome] ?? 0) + 1;
    }
    return {
      total: res.total,
      comparable: res.metrics.mapping_comparable ?? res.metrics.total_comparable ?? 0,
      notComparable: res.metrics.total_not_comparable,
      serverAgreementRate:
        res.metrics.server_code_agreement_rate ?? res.metrics.server_agreement_rate ?? null,
      authorityNotice: res.authority_notice,
      byOutcome,
    };
  }

  /**
   * Optional mobile trigger (flag separate from view). Prefer server-side enqueue on job terminal.
   * Associates by server_preliminary_id / preliminary_detection_id — never aisle-wide client_file_id Map.
   */
  async syncAfterJobTerminal(input: {
    readonly inventoryId: string;
    readonly aisleId: string;
    readonly jobId: string;
    readonly sessionId: string;
  }): Promise<void> {
    if (!this.canTrigger() && !this.isViewEnabled()) {
      return;
    }
    if (!this.canTrigger()) {
      // View-only: fetch without enqueue
      return;
    }
    const { inventoryId, aisleId, jobId, sessionId } = input;
    try {
      emitObservability(this.options.observability, {
        name: 'reconciliation_enqueued',
        sessionId,
        serverJobId: jobId,
        attributes: {},
      });
      const accepted = await this.options.api.triggerReconcile(inventoryId, aisleId, {
        job_id: jobId,
        enqueue_limit: 200,
      });
      const list = await this.options.api.listForAisle(inventoryId, aisleId, {
        jobId,
        limit: 200,
      });
      const byPreliminary = new Map(
        list.items.map((i) => [i.preliminary_detection_id, i] as const),
      );
      const drafts = await this.options.drafts.listForSession(sessionId);
      for (const draft of drafts) {
        if (draft.status === 'NOT_APPLICABLE') {
          continue;
        }
        const serverId = draft.server_preliminary_id;
        if (!serverId) {
          continue;
        }
        const row = byPreliminary.get(serverId);
        if (!row) {
          continue;
        }
        if (
          accepted.reconciliation_ids.length > 0 &&
          !accepted.reconciliation_ids.includes(row.id)
        ) {
          // Prefer rows from this enqueue when IDs returned
        }
        await this.options.drafts.markCompared(draft.id, row.outcome);
        emitObservability(this.options.observability, {
          name: 'reconciliation_completed',
          sessionId,
          clientFileId: draft.client_file_id ?? undefined,
          attributes: {
            outcome: row.outcome,
            reason: row.not_comparable_reason,
            reconciliation_id: row.id,
            preliminary_detection_id: row.preliminary_detection_id,
          },
        });
      }
    } catch (e) {
      this.options.logger.warn('error', {
        code: 'PRELIMINARY_RECONCILIATION_SYNC_FAILED',
        sessionId,
        message: String(e),
      });
      emitObservability(this.options.observability, {
        name: 'reconciliation_failed',
        sessionId,
        serverJobId: jobId,
        attributes: { message: String(e).slice(0, 120) },
      });
    }
  }
}

/** Spanish diagnostic labels — read-only. */
export function reconciliationOutcomeLabel(outcome: string): string {
  switch (outcome) {
    case 'MATCH_CODE_AND_QUANTITY':
    case 'MATCH_CODE_BOTH_QUANTITY_MISSING':
      return 'Coincide con servidor';
    case 'MATCH_CODE_LOCAL_QUANTITY_MISSING':
    case 'MATCH_CODE_REMOTE_QUANTITY_MISSING':
    case 'MATCH_CODE_QUANTITY_DIFFERENT':
    case 'MATCH_CODE_QUANTITY_MISSING_LOCAL':
      return 'Cantidad diferente';
    case 'CODE_MISMATCH':
      return 'Código diferente';
    case 'LOCAL_ONLY':
      return 'Solo detectado localmente';
    case 'REMOTE_ONLY':
    case 'SERVER_ONLY':
      return 'Solo detectado por servidor';
    case 'BOTH_UNRESOLVED':
      return 'Ambos sin código';
    case 'LOCAL_AMBIGUOUS':
    case 'REMOTE_AMBIGUOUS':
    case 'BOTH_AMBIGUOUS':
      return 'Resultado ambiguo';
    case 'NOT_COMPARABLE':
      return 'No comparable';
    default:
      return 'Comparación pendiente';
  }
}
