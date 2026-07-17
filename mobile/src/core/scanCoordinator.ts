/**
 * Serial scan coordinator: at most one scan runs at a time; coalesces concurrent requests
 * into a single follow-up pass so gallery events are not lost and not parallelized.
 */
export interface ScanCoordinator {
  /** Request a scan. Coalesces while one is in flight. */
  request(): Promise<void>;
  readonly isInProgress: boolean;
  readonly hasPending: boolean;
  /** How many times `runScan` actually executed (for tests/metrics). */
  readonly runCount: number;
}

export function createScanCoordinator(runScan: () => Promise<void>): ScanCoordinator {
  let inProgress = false;
  let pending = false;
  let runCount = 0;
  let chain: Promise<void> = Promise.resolve();

  function request(): Promise<void> {
    if (inProgress) {
      pending = true;
      return chain;
    }
    inProgress = true;
    chain = (async () => {
      try {
        do {
          pending = false;
          runCount += 1;
          await runScan();
        } while (pending);
      } finally {
        inProgress = false;
      }
    })();
    return chain;
  }

  return {
    request,
    get isInProgress() {
      return inProgress;
    },
    get hasPending() {
      return pending;
    },
    get runCount() {
      return runCount;
    },
  };
}
