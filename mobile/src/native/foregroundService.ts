/**
 * Foreground Service contract + binding for active capture sessions.
 *
 * Native implementation: `modules/capture-foreground-service` (Expo Module + Android Service).
 */
import { Platform } from 'react-native';

export interface CaptureNotificationContent {
  readonly inventoryName: string;
  readonly aisleName: string;
  readonly detected: number;
  readonly stable: number;
  readonly pending: number;
}

export interface ForegroundService {
  start(content: CaptureNotificationContent): Promise<void>;
  update(content: CaptureNotificationContent): Promise<void>;
  stop(): Promise<void>;
  readonly isAvailable: boolean;
}

export function buildCaptureNotificationText(content: CaptureNotificationContent): {
  title: string;
  body: string;
} {
  return {
    title: `Captura: ${content.inventoryName} · ${content.aisleName}`,
    body: `Detectadas ${content.detected} · Estables ${content.stable} · Pendientes ${content.pending}`,
  };
}

type NativeFgs = {
  startService: (title: string, body: string) => Promise<void>;
  updateNotification: (title: string, body: string) => Promise<void>;
  stopService: () => Promise<void>;
};

function resolveNative(): NativeFgs | null {
  if (Platform.OS !== 'android') {
    return null;
  }
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { requireOptionalNativeModule } = require('expo-modules-core') as {
      requireOptionalNativeModule: (name: string) => NativeFgs | null;
    };
    const mod = requireOptionalNativeModule('CaptureForegroundService');
    if (mod && typeof mod.startService === 'function') {
      return mod;
    }
  } catch {
    /* module not in this runtime */
  }
  return null;
}

export function createForegroundService(): ForegroundService {
  const native = resolveNative();
  if (!native) {
    return {
      isAvailable: false,
      async start() {},
      async update() {},
      async stop() {},
    };
  }

  return {
    isAvailable: true,
    async start(content) {
      const { title, body } = buildCaptureNotificationText(content);
      await native.startService(title, body);
    },
    async update(content) {
      const { title, body } = buildCaptureNotificationText(content);
      await native.updateNotification(title, body);
    },
    async stop() {
      await native.stopService();
    },
  };
}

export const noopForegroundService: ForegroundService = {
  isAvailable: false,
  async start() {},
  async update() {},
  async stop() {},
};
