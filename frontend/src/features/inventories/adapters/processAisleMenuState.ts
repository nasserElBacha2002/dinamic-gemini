/**
 * Derives whether “Process aisle” should be enabled and optional helper copy for the row menu.
 */

import type { Aisle } from '../../../api/types';

/** Minimal aisle fields for process-menu gating (avoids tying the helper to full list DTOs). */
export type AisleProcessMenuInput = Pick<Aisle, 'id' | 'status' | 'assets_count'>;

export interface ProcessAisleMenuState {
  disabled: boolean;
  disabledReason?: string;
}

export interface ProcessAisleMenuContext {
  aislesDataLoaded: boolean;
  aislesLoading: boolean;
  processingAisleId: string | null;
  t: (key: string) => string;
}

export function isAisleProcessingBusy(aisle: AisleProcessMenuInput, processingAisleId: string | null): boolean {
  const status = (aisle.status || '').toLowerCase();
  return status === 'queued' || status === 'processing' || processingAisleId === aisle.id;
}

export function computeProcessAisleMenuState(
  aisle: AisleProcessMenuInput,
  ctx: ProcessAisleMenuContext
): ProcessAisleMenuState {
  const busy = isAisleProcessingBusy(aisle, ctx.processingAisleId);
  const noListYet = !ctx.aislesDataLoaded;
  const missingAssets = ctx.aislesDataLoaded && (aisle.assets_count ?? 0) < 1;
  const disabled = busy || noListYet || missingAssets;
  if (busy) {
    return { disabled };
  }
  if (noListYet) {
    return {
      disabled,
      disabledReason: ctx.aislesLoading
        ? ctx.t('aisle.upload_error_verify')
        : ctx.t('aisle.upload_error_fallback'),
    };
  }
  if (missingAssets) {
    return { disabled, disabledReason: ctx.t('aisle.upload_need_image') };
  }
  return { disabled };
}
