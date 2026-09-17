/**
 * Shared binding to CaptureForegroundService for ZIP append / random-access I/O.
 * Barcode + FGS use the same module; ZIP needs appendBase64File (Phase 5+).
 */

export type CaptureForegroundAppendNative = {
  appendBase64File: (absolutePath: string, base64: string) => Promise<void>;
  truncateFile?: (absolutePath: string) => Promise<void>;
  /** Raw file→file append (no Base64). Returns bytes copied. */
  appendFile?: (destAbsolutePath: string, sourceAbsolutePath: string) => Promise<number>;
  /** One-pass size + sha256 + crc32 for a source file. */
  digestFile?: (
    absolutePath: string,
  ) => Promise<{ size: number; sha256: string; crc32: number }>;
};

export type CaptureForegroundRandomAccessNative = {
  getFileSize: (absolutePath: string) => Promise<number>;
  readFileRangeBase64: (
    absolutePath: string,
    offset: number,
    length: number,
  ) => Promise<string>;
  hashFileSha256: (absolutePath: string) => Promise<string>;
};

function platformOS(): string | undefined {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return (require('react-native') as { Platform?: { OS?: string } }).Platform?.OS;
  } catch {
    return undefined;
  }
}

/** Raw Expo module or null (Android only). */
export function resolveCaptureForegroundNative(): Record<string, unknown> | null {
  if (platformOS() !== 'android') {
    return null;
  }
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { requireOptionalNativeModule } = require('expo-modules-core') as {
      requireOptionalNativeModule: (name: string) => Record<string, unknown> | null;
    };
    return requireOptionalNativeModule('CaptureForegroundService');
  } catch {
    return null;
  }
}

function isFn(value: unknown): value is (...args: never[]) => unknown {
  return typeof value === 'function';
}

function normalizeDigest(raw: Record<string, unknown>): {
  size: number;
  sha256: string;
  crc32: number;
} {
  const size = Math.trunc(Number(raw.size));
  const sha256 = String(raw.sha256 ?? '').toLowerCase();
  const crc32 = Math.trunc(Number(raw.crc32)) >>> 0;
  return { size, sha256, crc32 };
}

/** Android ZIP append APIs, or null if this native binary is missing Phase 5 methods. */
export function resolveNativeBinaryAppend(): CaptureForegroundAppendNative | null {
  const mod = resolveCaptureForegroundNative();
  if (!mod || !isFn(mod.appendBase64File)) {
    return null;
  }
  const append: CaptureForegroundAppendNative = {
    appendBase64File: mod.appendBase64File as CaptureForegroundAppendNative['appendBase64File'],
  };
  if (isFn(mod.truncateFile)) {
    append.truncateFile = mod.truncateFile as NonNullable<
      CaptureForegroundAppendNative['truncateFile']
    >;
  }
  if (isFn(mod.appendFile)) {
    append.appendFile = mod.appendFile as NonNullable<CaptureForegroundAppendNative['appendFile']>;
  }
  if (isFn(mod.digestFile)) {
    append.digestFile = async (absolutePath: string) => {
      const raw = (await (
        mod.digestFile as (p: string) => Promise<Record<string, unknown>>
      )(absolutePath)) as Record<string, unknown>;
      return normalizeDigest(raw);
    };
  }
  return append;
}

/** Android random-access + hash APIs for ZIP validation. */
export function resolveNativeRandomAccess(): CaptureForegroundRandomAccessNative | null {
  const mod = resolveCaptureForegroundNative();
  if (
    !mod ||
    !isFn(mod.getFileSize) ||
    !isFn(mod.readFileRangeBase64) ||
    !isFn(mod.hashFileSha256)
  ) {
    return null;
  }
  return {
    getFileSize: mod.getFileSize as CaptureForegroundRandomAccessNative['getFileSize'],
    readFileRangeBase64:
      mod.readFileRangeBase64 as CaptureForegroundRandomAccessNative['readFileRangeBase64'],
    hashFileSha256: mod.hashFileSha256 as CaptureForegroundRandomAccessNative['hashFileSha256'],
  };
}

export function missingNativeZipIoDetail(): string {
  const mod = resolveCaptureForegroundNative();
  if (!mod) {
    return 'CaptureForegroundService module not loaded';
  }
  const keys = Object.keys(mod).sort().join(',');
  const hasAppend = isFn(mod.appendBase64File);
  const hasAppendFile = isFn(mod.appendFile);
  return `module_loaded appendBase64File=${hasAppend} appendFile=${hasAppendFile} keys=[${keys}] — rebuild Android native (npm run android)`;
}
