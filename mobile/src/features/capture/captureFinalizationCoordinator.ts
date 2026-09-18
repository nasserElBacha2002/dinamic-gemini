/**
 * Application-layer coordinator: single UI entry point for capture finalization + export-prep drain.
 * Composes CaptureService.finish() and ExportPrepQueue.waitUntilExportable() — does not reimplement them.
 */

import type { CaptureService } from '../capture/captureService';
import type { CaptureFinishCommit } from '../capture/captureFinishCommit';
import type { Logger } from '../../core/logging';
import {
  classifySessionExportPolicy,
} from '../exportPrep/sessionExportPolicy';
import type {
  ExportPrepDrainResult,
  ExportPrepQueue,
} from '../exportPrep/exportPrepQueue';

export type CapturePreparationStatus =
  | 'READY'
  | 'IN_PROGRESS'
  | 'TERMINAL_FAILURE'
  | 'STRUCTURAL_FAILURE';

export interface CaptureFinalizationResult {
  readonly sessionId: string;
  /** True once freeze + review transition were confirmed by CaptureService.finish(). */
  readonly captureCommitted: boolean;
  readonly freezeId: string | null;
  readonly freezeGeneration: number | null;
  readonly preparationStatus: CapturePreparationStatus;
  readonly drainResult: ExportPrepDrainResult | null;
  readonly recoverable: boolean;
  readonly userMessage: string | null;
  readonly finishCommit: CaptureFinishCommit | null;
}

export interface CaptureFinalizationCoordinatorDeps {
  readonly capture: CaptureService;
  readonly exportPrepQueue: ExportPrepQueue | null;
  readonly logger?: Logger | null;
  readonly drainTimeoutMs?: number;
}

export class CaptureFinalizationCoordinator {
  private readonly drainTimeoutMs: number;

  constructor(private readonly deps: CaptureFinalizationCoordinatorDeps) {
    this.drainTimeoutMs = deps.drainTimeoutMs ?? 10 * 60_000;
  }

  /**
   * Finalize capture for local ZIP review path.
   * Pre-commit failures → captureCommitted=false (stay on Capture).
   * Post-commit issues → captureCommitted=true + navigate to Review with prep status.
   */
  async finalizeForReview(
    sessionId: string,
    options?: {
      readonly onProgress?: (snap: ExportPrepDrainResult) => void;
      readonly timeoutMs?: number;
    },
  ): Promise<CaptureFinalizationResult> {
    this.deps.logger?.info('export_prep', {
      code: 'FINALIZATION_STARTED',
      sessionId,
    });

    let finishCommit: CaptureFinishCommit;
    try {
      finishCommit = await this.deps.capture.finish();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.deps.logger?.warn('export_prep', {
        code: 'FINALIZATION_PRE_COMMIT_FAILED',
        sessionId,
        message,
      });
      return {
        sessionId,
        captureCommitted: false,
        freezeId: null,
        freezeGeneration: null,
        preparationStatus: 'STRUCTURAL_FAILURE',
        drainResult: null,
        recoverable: true,
        userMessage: message,
        finishCommit: null,
      };
    }

    const snap = await this.deps.capture.getSessionSnapshot(sessionId);
    const session = snap.session;
    if (!session) {
      this.deps.logger?.warn('export_prep', {
        code: 'EXPORT_PREP_SESSION_MISSING',
        sessionId,
      });
      return {
        sessionId,
        captureCommitted: true,
        freezeId: finishCommit.freezeId,
        freezeGeneration: finishCommit.freezeGeneration,
        preparationStatus: 'STRUCTURAL_FAILURE',
        drainResult: null,
        recoverable: false,
        userMessage: 'La sesión de captura ya no está disponible.',
        finishCommit,
      };
    }

    const freezeId = finishCommit.freezeId ?? session.active_freeze_id;
    const freezeGeneration =
      finishCommit.freezeGeneration ?? session.capture_freeze_generation ?? null;

    this.deps.logger?.info('export_prep', {
      code: 'FINALIZATION_COMMIT_COMPLETED',
      sessionId,
      freezeId,
      freezeGeneration,
      producerBarrierCompleted: finishCommit.producerBarrierCompleted,
      exportPackagingMode: finishCommit.exportPackagingMode,
    });

    const prepQueue = this.deps.exportPrepQueue;
    if (!prepQueue) {
      return {
        sessionId,
        captureCommitted: true,
        freezeId,
        freezeGeneration,
        preparationStatus: 'READY',
        drainResult: null,
        recoverable: false,
        userMessage: null,
        finishCommit,
      };
    }

    const classification = classifySessionExportPolicy(session, true);
    if (classification.freezeRequired && freezeId == null) {
      this.deps.logger?.warn('export_prep', {
        code: 'EXPORT_PREP_FREEZE_MISSING',
        sessionId,
        packagingMode: classification.packagingMode,
      });
      return {
        sessionId,
        captureCommitted: true,
        freezeId: null,
        freezeGeneration,
        preparationStatus: 'STRUCTURAL_FAILURE',
        drainResult: null,
        recoverable: true,
        userMessage: 'No se encontró el freeze de la captura. Reintentá la preparación desde Revisión.',
        finishCommit,
      };
    }

    try {
      const drain = await prepQueue.waitUntilExportable(sessionId, {
        reason: 'FINISH',
        producerBarrierCompleted: finishCommit.producerBarrierCompleted,
        expectedFreezeId: freezeId,
        expectedFreezeGeneration: freezeGeneration,
        allowLegacyWithoutFreeze: classification.allowLegacyWithoutFreeze,
        timeoutMs: options?.timeoutMs ?? this.drainTimeoutMs,
        pollMs: 500,
        ...(options?.onProgress ? { onProgress: options.onProgress } : {}),
      });

      return {
        ...this.classifyPostCommit(sessionId, freezeId, freezeGeneration, drain),
        finishCommit,
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.deps.logger?.warn('export_prep', {
        code: 'EXPORT_PREP_POST_COMMIT_RECOVERY_REQUIRED',
        sessionId,
        freezeId,
        message,
      });
      return {
        sessionId,
        captureCommitted: true,
        freezeId,
        freezeGeneration,
        preparationStatus: 'IN_PROGRESS',
        drainResult: null,
        recoverable: true,
        userMessage:
          message ||
          'La captura quedó guardada; la preparación continúa. Revisá el estado en Revisión.',
        finishCommit,
      };
    }
  }

  private classifyPostCommit(
    sessionId: string,
    freezeId: string | null,
    freezeGeneration: number | null,
    drain: ExportPrepDrainResult,
  ): Omit<CaptureFinalizationResult, 'finishCommit'> {
    if (drain.exportable) {
      this.deps.logger?.info('export_prep', {
        code: 'EXPORT_PREP_DRAIN_READY',
        sessionId,
        freezeId: drain.freezeId,
        totalEligible: drain.totalEligible,
        ready: drain.ready,
        durationMs: drain.durationMs,
      });
      return {
        sessionId,
        captureCommitted: true,
        freezeId,
        freezeGeneration,
        preparationStatus: 'READY',
        drainResult: drain,
        recoverable: false,
        userMessage: null,
      };
    }

    if (drain.structuralError) {
      this.deps.logger?.warn('export_prep', {
        code: 'EXPORT_PREP_POST_COMMIT_RECOVERY_REQUIRED',
        sessionId,
        structuralError: drain.structuralError,
      });
      return {
        sessionId,
        captureCommitted: true,
        freezeId,
        freezeGeneration,
        preparationStatus: 'STRUCTURAL_FAILURE',
        drainResult: drain,
        recoverable: drain.structuralError !== 'SESSION_MISSING',
        userMessage: this.messageForStructural(drain),
      };
    }

    if (
      drain.failedTerminal > 0 &&
      drain.missingJobs === 0 &&
      drain.queued === 0 &&
      drain.processing === 0 &&
      drain.failedRetryable === 0
    ) {
      return {
        sessionId,
        captureCommitted: true,
        freezeId,
        freezeGeneration,
        preparationStatus: 'TERMINAL_FAILURE',
        drainResult: drain,
        recoverable: true,
        userMessage: `${drain.failedTerminal} foto(s) con fallo terminal. Reintentá o excluí en Revisión.`,
      };
    }

    if (drain.timedOut) {
      this.deps.logger?.warn('export_prep', {
        code: 'EXPORT_PREP_OBSERVER_TIMEOUT',
        sessionId,
        ready: drain.ready,
        totalEligible: drain.totalEligible,
      });
      return {
        sessionId,
        captureCommitted: true,
        freezeId,
        freezeGeneration,
        preparationStatus: 'IN_PROGRESS',
        drainResult: drain,
        recoverable: true,
        userMessage: `Tiempo de espera agotado (${drain.ready}/${drain.totalEligible} listas). La cola sigue en segundo plano.`,
      };
    }

    return {
      sessionId,
      captureCommitted: true,
      freezeId,
      freezeGeneration,
      preparationStatus: 'IN_PROGRESS',
      drainResult: drain,
      recoverable: true,
      userMessage:
        drain.missingJobs > 0
          ? `Faltan ${drain.missingJobs} job(s) de preparación. Reintentá desde Revisión.`
          : 'Preparación incompleta. Continuá en Revisión.',
    };
  }

  private messageForStructural(drain: ExportPrepDrainResult): string {
    switch (drain.structuralError) {
      case 'SESSION_MISSING':
        return 'La sesión de captura ya no está disponible.';
      case 'FREEZE_MISSING':
        return 'No se encontró el freeze de la captura. Reintentá la preparación desde Revisión.';
      case 'FREEZE_CHANGED':
        return 'El lote congelado cambió durante la preparación. Reintentá desde Revisión.';
      case 'DATABASE_ERROR':
        return 'Error de base de datos durante la preparación. Reintentá desde Revisión.';
      case 'STORAGE_ERROR':
        return 'Error de almacenamiento durante la preparación. Reintentá desde Revisión.';
      case 'DRAIN_FAILED':
        return 'La preparación falló. Revisá el estado en Revisión.';
      default:
        return 'Error estructural de preparación. Revisá el estado en Revisión.';
    }
  }
}
