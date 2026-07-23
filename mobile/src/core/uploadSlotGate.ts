/**
 * Atomic upload concurrency slots — acquire before launching async batch work.
 */
export class UploadSlotGate {
  private active = 0;

  get activeCount(): number {
    return this.active;
  }

  tryAcquire(limit: number): boolean {
    const cap = Math.max(0, Math.floor(limit));
    if (cap <= 0 || this.active >= cap) {
      return false;
    }
    this.active += 1;
    return true;
  }

  release(): void {
    this.active = Math.max(0, this.active - 1);
  }

  /** Test helper / dispose safety. */
  reset(): void {
    this.active = 0;
  }
}

/**
 * How many additional photos may be prepared given pending prepared count and free upload slots.
 * When uploads are saturated (freeSlots=0), still allow preparing up to maxPreparedPending total,
 * but never grow unboundedly.
 */
export function prepareAllowance(input: {
  readonly preparedPending: number;
  readonly freeUploadSlots: number;
  readonly maxFilesPerBatch: number;
  readonly maxPreparedPending: number;
}): number {
  const maxPrepared = Math.max(1, input.maxPreparedPending);
  const headroom = Math.max(0, maxPrepared - input.preparedPending);
  if (headroom <= 0) {
    return 0;
  }
  if (input.freeUploadSlots <= 0) {
    // Saturated uploads: only fill up to the pending cap (do not prepare forever).
    return headroom;
  }
  const slotDriven = input.freeUploadSlots * Math.max(1, input.maxFilesPerBatch);
  return Math.min(headroom, slotDriven);
}
