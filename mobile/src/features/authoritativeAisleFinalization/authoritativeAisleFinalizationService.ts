import type { FeatureFlags } from '../../core/featureFlags';
import type { Logger } from '../../core/logging';
import type { AisleFinalizationIntentRepository } from '../../database/repositories/aisleFinalizationIntentRepository';
import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { ConfirmedLocalResultRepository } from '../../database/repositories/confirmedLocalResultRepository';
import { ApiError } from '../../services/api/apiClient';
import type { ConnectivityService } from '../../services/connectivity/connectivity';
import type { AuthoritativeAisleFinalizationApi } from './authoritativeAisleFinalizationApi';
import {
  evaluateLocalAuthoritativeAisleReadiness,
  type AuthoritativeAisleReadiness,
} from './authoritativeAisleReadiness';

export type MobileFinalizationStatus =
  | 'IDLE'
  | 'FINALIZATION_PENDING'
  | 'FINALIZATION_SYNCING'
  | 'FINALIZATION_RETRY_SCHEDULED'
  | 'FINALIZATION_COMPLETED'
  | 'FINALIZATION_CONFLICT'
  | 'FINALIZATION_REJECTED'
  | 'FINALIZATION_FAILED_TERMINAL';

export interface AuthoritativeAisleFinalizationServiceOptions {
  readonly flags: FeatureFlags;
  readonly api: AuthoritativeAisleFinalizationApi;
  readonly capture: CaptureRepository;
  readonly confirmed: ConfirmedLocalResultRepository;
  readonly intents?: AisleFinalizationIntentRepository | null;
  readonly connectivity?: ConnectivityService | null;
  readonly logger: Logger;
  readonly createId: () => string;
}

/**
 * Phase 6: operator finalization. Never marks completed until server confirms.
 * Persists finalization_id + offline intent in SQLite when offline queue flag is on.
 */
export class AuthoritativeAisleFinalizationService {
  private inFlight = false;
  private finalizationIds = new Map<string, string>();
  private statuses = new Map<string, MobileFinalizationStatus>();

  constructor(private readonly options: AuthoritativeAisleFinalizationServiceOptions) {}

  isEnabled(): boolean {
    return this.options.flags.mobileAuthoritativeAisleFinalization === true;
  }

  getStatus(sessionId: string): MobileFinalizationStatus {
    return this.statuses.get(sessionId) ?? 'IDLE';
  }

  getOrCreateFinalizationId(sessionId: string): string {
    const existing = this.finalizationIds.get(sessionId);
    if (existing) return existing;
    const id = this.options.createId();
    this.finalizationIds.set(sessionId, id);
    return id;
  }

  async evaluateLocal(sessionId: string): Promise<AuthoritativeAisleReadiness> {
    const photos = await this.options.capture.listPhotos(sessionId);
    const confirmed = await this.options.confirmed.listForSession(sessionId);
    return evaluateLocalAuthoritativeAisleReadiness({
      photos,
      confirmed,
      enabled: this.isEnabled(),
    });
  }

  async refreshServerReadiness(
    inventoryId: string,
    aisleId: string,
  ): Promise<AuthoritativeAisleReadiness> {
    return this.options.api.getReadiness(inventoryId, aisleId);
  }

  async recordExclusion(input: {
    readonly inventoryId: string;
    readonly aisleId: string;
    readonly assetId: string;
    readonly reason?: string;
  }): Promise<void> {
    if (!this.isEnabled()) return;
    await this.options.api.recordExclusion(
      input.inventoryId,
      input.aisleId,
      input.assetId,
      input.reason ?? 'USER_EXCLUDED',
    );
  }

  async finalize(input: {
    readonly sessionId: string;
    readonly inventoryId: string;
    readonly aisleId: string;
  }): Promise<{ ok: true; status: string } | { ok: false; reason: string; code?: string }> {
    if (!this.isEnabled()) {
      return { ok: false, reason: 'Feature disabled', code: 'FEATURE_DISABLED' };
    }
    if (this.inFlight) {
      return { ok: false, reason: 'Finalization already in progress', code: 'IN_FLIGHT' };
    }
    const finalizationId = this.getOrCreateFinalizationId(input.sessionId);
    const online = this.options.connectivity
      ? this.options.connectivity.getState() === 'online'
      : true;
    if (!online) {
      this.statuses.set(input.sessionId, 'FINALIZATION_PENDING');
      if (
        this.options.flags.authoritativeFinalizationOfflineQueue &&
        this.options.intents
      ) {
        const nowIso = new Date().toISOString();
        await this.options.intents.upsertPending({
          id: this.options.createId(),
          sessionId: input.sessionId,
          inventoryId: input.inventoryId,
          aisleId: input.aisleId,
          finalizationId,
          expectedAssetCount: 0,
          nowIso,
        });
      }
      return {
        ok: false,
        reason: 'Sin conexión. La finalización queda pendiente hasta recuperar red.',
        code: 'NETWORK_OFFLINE',
      };
    }

    this.inFlight = true;
    this.statuses.set(input.sessionId, 'FINALIZATION_SYNCING');
    try {
      const server = await this.options.api.getReadiness(input.inventoryId, input.aisleId);
      if (server.status !== 'READY' || !server.canFinalize) {
        this.statuses.set(input.sessionId, 'FINALIZATION_REJECTED');
        return {
          ok: false,
          reason: `Servidor no listo: ${server.reasons.join(', ') || server.status}`,
          code: 'AUTHORITATIVE_FINALIZATION_NOT_READY',
        };
      }
      if (
        this.options.flags.authoritativeFinalizationOfflineQueue &&
        this.options.intents
      ) {
        const nowIso = new Date().toISOString();
        await this.options.intents.upsertPending({
          id: this.options.createId(),
          sessionId: input.sessionId,
          inventoryId: input.inventoryId,
          aisleId: input.aisleId,
          finalizationId,
          expectedAssetCount: server.totalImages,
          nowIso,
        });
        await this.options.intents.updateStatus(input.sessionId, 'FINALIZATION_SYNCING', {
          nowIso,
        });
      }
      const result = await this.options.api.finalize(input.inventoryId, input.aisleId, {
        finalization_id: finalizationId,
        expected_asset_count: server.totalImages,
        client_session_id: input.sessionId,
      });
      this.statuses.set(input.sessionId, 'FINALIZATION_COMPLETED');
      if (this.options.intents) {
        await this.options.intents.updateStatus(input.sessionId, 'FINALIZATION_COMPLETED', {
          nowIso: new Date().toISOString(),
        });
      }
      return { ok: true, status: result.status };
    } catch (e) {
      const apiErr = e instanceof ApiError ? e : null;
      const code = apiErr?.code ?? 'FINALIZATION_FAILED';
      let status: MobileFinalizationStatus = 'FINALIZATION_RETRY_SCHEDULED';
      if (code.includes('CONFLICT') || apiErr?.status === 409) {
        status = 'FINALIZATION_CONFLICT';
      } else if (apiErr?.status === 422 || apiErr?.status === 404) {
        status = 'FINALIZATION_FAILED_TERMINAL';
      }
      this.statuses.set(input.sessionId, status);
      if (this.options.intents) {
        await this.options.intents.updateStatus(input.sessionId, status, {
          errorCode: code,
          nowIso: new Date().toISOString(),
          bumpAttempt: true,
        });
      }
      this.options.logger.warn('error', {
        where: 'authoritative_aisle_finalization',
        code,
        message: String(e),
      });
      return { ok: false, reason: String(e), code };
    } finally {
      this.inFlight = false;
    }
  }
}
