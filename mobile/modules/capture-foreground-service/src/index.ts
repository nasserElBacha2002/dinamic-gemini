/**
 * Type surface for CaptureForegroundService (Expo module).
 * Runtime binding uses requireOptionalNativeModule('CaptureForegroundService').
 */
export type CaptureForegroundNativeModule = {
  startService: (title: string, body: string) => Promise<void>;
  updateNotification: (title: string, body: string) => Promise<void>;
  stopService: () => Promise<void>;
  detectBarcodes?: (uri: string, formatsCsv: string) => Promise<unknown>;
  /** Append Base64-decoded bytes to an absolute path (ZIP streaming). */
  appendBase64File?: (absolutePath: string, base64: string) => Promise<void>;
  truncateFile?: (absolutePath: string) => Promise<void>;
};

export {};
