/**
 * Type surface for CaptureForegroundService (Expo module).
 * Runtime binding uses requireOptionalNativeModule('CaptureForegroundService').
 */
export type CaptureForegroundNativeModule = {
  startService: (title: string, body: string) => Promise<void>;
  updateNotification: (title: string, body: string) => Promise<void>;
  stopService: () => Promise<void>;
  detectBarcodes?: (uri: string, formatsCsv: string) => Promise<unknown>;
  appendBase64File?: (absolutePath: string, base64: string) => Promise<void>;
  truncateFile?: (absolutePath: string) => Promise<void>;
  appendFile?: (destAbsolutePath: string, sourceAbsolutePath: string) => Promise<number>;
  digestFile?: (
    absolutePath: string,
  ) => Promise<{ size: number; sha256: string; crc32: number }>;
  getFileSize?: (absolutePath: string) => Promise<number>;
  readFileRangeBase64?: (
    absolutePath: string,
    offset: number,
    length: number,
  ) => Promise<string>;
  hashFileSha256?: (absolutePath: string) => Promise<string>;
};

export {};
