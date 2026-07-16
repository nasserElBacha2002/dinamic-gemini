/**
 * Foreground Service abstraction for active capture sessions (Fase 0, §22).
 *
 * A real Android Foreground Service (type `dataSync`) keeps detection + uploads alive while
 * the screen is locked / app is backgrounded. Expo does NOT ship a managed FGS module, so a
 * Development Build with ONE of the following is required (validated in the spike report):
 *   (a) a custom Expo config plugin + a tiny native `Service` (recommended), or
 *   (b) a community module such as `@supersami/rn-foreground-service`.
 *
 * This TypeScript surface is the contract the rest of the app codes against; the concrete
 * binding is wired in the Development Build. The interface is kept pure so callers and tests
 * do not depend on the native implementation.
 */

export interface CaptureNotificationContent {
  readonly inventoryName: string;
  readonly aisleName: string;
  readonly detected: number;
  readonly pending: number;
  readonly uploaded: number;
}

export interface ForegroundService {
  /** Start the FGS and show the persistent notification. Safe to call once per session. */
  start(content: CaptureNotificationContent): Promise<void>;
  /** Update the persistent notification counters without restarting the service. */
  update(content: CaptureNotificationContent): Promise<void>;
  /** Stop the FGS and dismiss the notification when the session finishes/cancels. */
  stop(): Promise<void>;
  /** Whether a concrete native binding is available in this build. */
  readonly isAvailable: boolean;
}

/**
 * No-op fallback used when no native FGS binding is present (e.g. Expo Go, pure-core tests).
 * It deliberately reports `isAvailable = false` so bootstrap can surface a clear limitation
 * instead of silently pretending background execution works.
 */
export const noopForegroundService: ForegroundService = {
  isAvailable: false,
  async start() {
    /* no-op: no native FGS in this runtime */
  },
  async update() {
    /* no-op */
  },
  async stop() {
    /* no-op */
  },
};

export function buildCaptureNotificationText(content: CaptureNotificationContent): {
  title: string;
  body: string;
} {
  return {
    title: `Captura: ${content.inventoryName} · ${content.aisleName}`,
    body: `Detectadas ${content.detected} · Pendientes ${content.pending} · Cargadas ${content.uploaded}`,
  };
}
