import type { FeatureFlags } from '../../core/featureFlags';
import { LABEL_PAYLOAD_PARSER_VERSION } from '../../core/labelPayload';
import type {
  ConfirmedLocalResultRepository,
  ConfirmedLocalResultRow,
  ConfirmedLocalResultSource,
  ConfirmedQuantityStatus,
} from '../../database/repositories/confirmedLocalResultRepository';
import type {
  LocalDetectionDraftRepository,
  LocalDetectionDraftRow,
} from '../../database/repositories/localDetectionDraftRepository';
import { LOCAL_CODE_DETECTOR_VERSION } from '../localCodeScan/localCodeDetector';
import {
  userMessageForConfirmValidation,
  validateConfirmedInternalCode,
  validateConfirmedQuantity,
} from './confirmLocalResultValidation';

export interface ConfirmLocalResultEdits {
  readonly internalCode: string;
  readonly quantity: number | null;
  readonly quantityStatus: ConfirmedQuantityStatus;
}

function isSupplierIdentityOnlyDraft(
  draft: LocalDetectionDraftRow | null,
  confirmedCode: string,
): boolean {
  if (!draft?.label_id?.trim() || confirmedCode) return false;
  if (draft.detected_format === 'SUPPLIER') return true;
  const snap = draft.recognition_profile_snapshot_json ?? '';
  return snap.includes('"profile_source":"SUPPLIER"');
}

export class ConfirmLocalResultService {
  constructor(
    private readonly flags: FeatureFlags,
    private readonly confirmed: ConfirmedLocalResultRepository,
    private readonly drafts: LocalDetectionDraftRepository,
  ) {}

  isEnabled(): boolean {
    return this.flags.mobileAuthoritativeLocalCodeScan === true;
  }

  async getLatestDraftForPhoto(capturePhotoId: string): Promise<LocalDetectionDraftRow | null> {
    const rows = await this.drafts.listForPhoto(capturePhotoId);
    return rows.find((r) => r.status !== 'NOT_APPLICABLE') ?? rows[0] ?? null;
  }

  resolveSource(
    draft: LocalDetectionDraftRow | null,
    edits: ConfirmLocalResultEdits,
  ): ConfirmedLocalResultSource {
    const confirmedCode = edits.internalCode.trim();
    const detectedCode = draft?.internal_code?.trim() ?? null;
    const detectedQty = draft?.quantity ?? null;
    const confirmedQty = edits.quantityStatus === 'PRESENT' ? edits.quantity : null;
    if (isSupplierIdentityOnlyDraft(draft, confirmedCode)) {
      // Identity-only: detected internal is also null — treat as local scan when qty matches.
      if (detectedQty !== confirmedQty) {
        return 'LOCAL_MANUAL_CORRECTION';
      }
      if (edits.quantityStatus === 'MISSING' && draft?.quantity_status !== 'MISSING') {
        return 'LOCAL_MANUAL_CORRECTION';
      }
      return 'LOCAL_CODE_SCAN';
    }
    if (!detectedCode || detectedCode !== confirmedCode) {
      return 'LOCAL_MANUAL_CORRECTION';
    }
    if (detectedQty !== confirmedQty) {
      return 'LOCAL_MANUAL_CORRECTION';
    }
    if (edits.quantityStatus === 'MISSING' && draft?.quantity_status !== 'MISSING') {
      return 'LOCAL_MANUAL_CORRECTION';
    }
    return 'LOCAL_CODE_SCAN';
  }

  async confirm(input: {
    readonly capturePhotoId: string;
    readonly captureSessionId: string;
    readonly clientFileId: string | null;
    readonly confirmedByUserId: string;
    readonly edits: ConfirmLocalResultEdits;
    readonly draft?: LocalDetectionDraftRow | null;
    readonly confirmedAt?: string;
  }): Promise<ConfirmedLocalResultRow> {
    if (!this.isEnabled()) {
      throw new Error('La confirmación local autoritativa no está habilitada.');
    }

    const draft = input.draft ?? (await this.getLatestDraftForPhoto(input.capturePhotoId));
    const confirmedCode = input.edits.internalCode.trim();
    const identityOnly = isSupplierIdentityOnlyDraft(draft, confirmedCode);
    const codeError = validateConfirmedInternalCode(input.edits.internalCode, {
      allowEmpty: identityOnly,
    });
    if (codeError) {
      throw new Error(userMessageForConfirmValidation(codeError));
    }
    const qtyError = validateConfirmedQuantity({
      quantity: input.edits.quantity,
      quantityStatus: input.edits.quantityStatus,
    });
    if (qtyError) {
      throw new Error(userMessageForConfirmValidation(qtyError));
    }

    const confirmedQuantity =
      input.edits.quantityStatus === 'PRESENT' ? input.edits.quantity : null;
    const source = this.resolveSource(draft, input.edits);
    const prepared =
      draft?.prepared_asset_fingerprint ??
      `sha256:${'0'.repeat(64)}`;

    return this.confirmed.upsertConfirmed({
      capturePhotoId: input.capturePhotoId,
      captureSessionId: input.captureSessionId,
      clientFileId: input.clientFileId,
      detectedInternalCode: draft?.internal_code ?? null,
      detectedQuantity: draft?.quantity ?? null,
      // SQLite column remains NOT NULL; empty string = identity-only (mapped to null on wire).
      confirmedInternalCode: confirmedCode,
      confirmedQuantity,
      quantityStatus: input.edits.quantityStatus,
      source,
      // Physical sticker identity from draft — never inferred from SKU/internal_code.
      labelId: draft?.label_id ?? null,
      detectedSymbology: draft?.detected_symbology ?? null,
      parserVersion: draft?.parser_version ?? LABEL_PAYLOAD_PARSER_VERSION,
      detectorVersion: draft?.detector_version ?? LOCAL_CODE_DETECTOR_VERSION,
      preparedAssetSha256: prepared,
      confirmedByUserId: input.confirmedByUserId,
      confirmedAt: input.confirmedAt ?? new Date().toISOString(),
      recognitionProfileSnapshotJson: draft?.recognition_profile_snapshot_json ?? null,
    });
  }

  /**
   * Auto-confirm stable photos that already have a usable local CODE_SCAN draft.
   * Skips photos without an internal code unless supplier identity-only (label_id).
   */
  async confirmResolvedDraftsForSession(input: {
    readonly sessionId: string;
    readonly confirmedByUserId: string;
    readonly photos: readonly {
      readonly id: string;
      readonly client_file_id: string | null;
      readonly status: string;
    }[];
  }): Promise<{ readonly confirmed: number; readonly skipped: number }> {
    if (!this.isEnabled()) {
      return { confirmed: 0, skipped: input.photos.length };
    }
    const existing = await this.confirmed.listForSession(input.sessionId);
    const confirmedPhotoIds = new Set(existing.map((r) => r.capture_photo_id));
    let confirmed = 0;
    let skipped = 0;
    for (const photo of input.photos) {
      if (photo.status !== 'stable') {
        skipped += 1;
        continue;
      }
      if (confirmedPhotoIds.has(photo.id)) {
        confirmed += 1;
        continue;
      }
      const draft = await this.getLatestDraftForPhoto(photo.id);
      const code = draft?.internal_code?.trim() ?? '';
      const labelId = draft?.label_id?.trim() ?? '';
      if (!code && !labelId) {
        skipped += 1;
        continue;
      }
      const quantityStatus =
        draft?.quantity_status === 'PRESENT' || draft?.quantity != null ? 'PRESENT' : 'MISSING';
      await this.confirm({
        capturePhotoId: photo.id,
        captureSessionId: input.sessionId,
        clientFileId: photo.client_file_id,
        confirmedByUserId: input.confirmedByUserId,
        edits: {
          internalCode: code,
          quantity: draft?.quantity ?? null,
          quantityStatus,
        },
        draft,
      });
      confirmed += 1;
    }
    return { confirmed, skipped };
  }
}
