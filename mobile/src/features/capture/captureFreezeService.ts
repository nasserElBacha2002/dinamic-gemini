/**
 * Persists an exact photo snapshot at capture finish / local close.
 * CSV export and upload must use this set — not the live photo table.
 */

import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';
import { sha256Hex } from '../../core/payloadFingerprint';
import { createId } from '../../shared/createId';

export interface CaptureFreezeSnapshot {
  readonly freezeId: string;
  readonly generation: number;
  readonly frozenAt: string;
  readonly photoCount: number;
  readonly contentFingerprint: string;
  readonly photos: readonly CapturePhotoRow[];
}

export class CaptureFreezeService {
  constructor(private readonly repo: CaptureRepository) {}

  /**
   * Create (or reuse) a freeze snapshot for the current eligible photo set.
   * Runs with session watermark update in one transactional write when possible.
   */
  async freezeSession(
    sessionId: string,
    photos: readonly CapturePhotoRow[],
  ): Promise<CaptureFreezeSnapshot> {
    const eligible = [...photos]
      .filter((p) => p.status !== 'excluded' && p.status !== 'rejected')
      .sort((a, b) => {
        const sa = a.sequence_number ?? Number.MAX_SAFE_INTEGER;
        const sb = b.sequence_number ?? Number.MAX_SAFE_INTEGER;
        if (sa !== sb) return sa - sb;
        if (a.date_added !== b.date_added) return a.date_added - b.date_added;
        return a.asset_id.localeCompare(b.asset_id);
      });

    const fingerprint = sha256Hex(
      eligible.map((p) => `${p.id}:${p.status}:${p.sequence_number ?? ''}`).join('|'),
    );

    const existing = await this.repo.getActiveFreeze(sessionId);
    if (existing && existing.content_fingerprint === fingerprint) {
      const frozenPhotos = await this.repo.listFreezePhotos(existing.id);
      return {
        freezeId: existing.id,
        generation: existing.generation,
        frozenAt: existing.frozen_at,
        photoCount: existing.photo_count,
        contentFingerprint: existing.content_fingerprint,
        photos: frozenPhotos,
      };
    }

    const freezeId = createId();
    const frozenAt = new Date().toISOString();
    const session = await this.repo.createFreezeSnapshot({
      freezeId,
      sessionId,
      frozenAt,
      photoCount: eligible.length,
      contentFingerprint: fingerprint,
      photos: eligible.map((p, index) => ({
        capturePhotoId: p.id,
        sequenceNumber: p.sequence_number ?? index + 1,
        statusAtFreeze: p.status,
        included: true,
      })),
    });

    return {
      freezeId,
      generation: session.capture_freeze_generation,
      frozenAt,
      photoCount: eligible.length,
      contentFingerprint: fingerprint,
      photos: eligible,
    };
  }

  async listFrozenPhotos(session: CaptureSessionRow): Promise<CapturePhotoRow[] | null> {
    if (!session.active_freeze_id) {
      return null;
    }
    return this.repo.listFreezePhotos(session.active_freeze_id);
  }
}
