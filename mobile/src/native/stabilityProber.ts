/**
 * Device-side stability prober (Fase 0, §13).
 *
 * Samples a file's (size, mtime) over time via expo-file-system and folds each sample into
 * the pure `stability` reducer. When the reducer reports `settled`, a final decode check
 * confirms the bytes are a real, openable image before the photo is marked `ready`.
 *
 * Requires the Expo dev toolchain; excluded from pure-core sandbox validation.
 */
import * as FileSystem from 'expo-file-system';
import { Image } from 'react-native';

import {
  DEFAULT_STABILITY_CONFIG,
  initStability,
  recordSample,
  type StabilityConfig,
  type StabilityState,
} from '../core/stability';

export interface StabilityProbeOptions {
  readonly config?: StabilityConfig;
  /** Delay between samples in ms. */
  readonly intervalMs?: number;
  /** Injected sleeper (tests). */
  readonly sleep?: (ms: number) => Promise<void>;
}

export type StabilityOutcome =
  | { readonly ok: true }
  | { readonly ok: false; readonly reason: 'unstable' | 'undecodable' };

const _defaultSleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

async function sampleFile(uri: string): Promise<{ size: number; dateModified: number; accessible: boolean }> {
  try {
    const info = await FileSystem.getInfoAsync(uri, { size: true });
    if (!info.exists) {
      return { size: 0, dateModified: 0, accessible: false };
    }
    return {
      size: typeof info.size === 'number' ? info.size : 0,
      dateModified: typeof info.modificationTime === 'number' ? Math.floor(info.modificationTime) : 0,
      accessible: true,
    };
  } catch {
    return { size: 0, dateModified: 0, accessible: false };
  }
}

function canDecode(uri: string): Promise<boolean> {
  return new Promise((resolve) => {
    Image.getSize(
      uri,
      (w, h) => resolve(w > 0 && h > 0),
      () => resolve(false),
    );
  });
}

/**
 * Run the stability loop for one image. Returns ok=true only when the file settled AND
 * decoded to positive dimensions. Never marks error before `maxChecks` samples.
 */
export async function probeStability(
  uri: string,
  options: StabilityProbeOptions = {},
): Promise<StabilityOutcome> {
  const config = options.config ?? DEFAULT_STABILITY_CONFIG;
  const intervalMs = options.intervalMs ?? 750;
  const sleep = options.sleep ?? _defaultSleep;

  let state: StabilityState = initStability();
  for (let i = 0; i < config.maxChecks; i += 1) {
    const sample = await sampleFile(uri);
    state = recordSample(state, sample, config);
    if (state.phase === 'settled') {
      break;
    }
    if (state.phase === 'unstable') {
      return { ok: false, reason: 'unstable' };
    }
    await sleep(intervalMs);
  }

  if (state.phase !== 'settled') {
    return { ok: false, reason: 'unstable' };
  }
  const decodable = await canDecode(uri);
  return decodable ? { ok: true } : { ok: false, reason: 'undecodable' };
}
