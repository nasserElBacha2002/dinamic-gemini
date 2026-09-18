/**
 * Typed evidence from CaptureService.finish() for post-commit drain/export.
 * UI must not invent producerBarrierCompleted — only this commit (or recovery policy) may.
 */

import type { ExportPackagingMode } from '../exportPrep/sessionExportPolicy';

export interface CaptureFinishCommit {
  readonly sessionId: string;
  readonly freezeId: string | null;
  readonly freezeGeneration: number | null;
  /** True when finish waited the producer barrier (or no barrier was configured). */
  readonly producerBarrierCompleted: boolean;
  readonly committed: boolean;
  readonly exportPackagingMode: ExportPackagingMode | null;
}
