/**
 * File-stability state machine (Fase 0, §13).
 *
 * A drone photo may still be written to disk when MediaStore first reports it. We must not
 * queue an image until it stops changing. This module is a pure reducer over successive
 * (size, dateModified) samples; the actual sampling + decode is done by a device prober.
 */

export interface StabilitySample {
  readonly size: number;
  readonly dateModified: number;
  /** True when the sampler could open/read the file at this point (best-effort). */
  readonly accessible: boolean;
}

export interface StabilityConfig {
  /** Consecutive identical samples required to consider the file settled. */
  readonly requiredStableStreak: number;
  /** Hard cap on samples before declaring the file unstable (recoverable error). */
  readonly maxChecks: number;
}

export const DEFAULT_STABILITY_CONFIG: StabilityConfig = {
  requiredStableStreak: 2,
  maxChecks: 5,
};

export type StabilityPhase =
  | 'waiting' // still sampling / file still changing
  | 'settled' // size+mtime stable and accessible; ready for decode verification
  | 'unstable'; // never settled within maxChecks -> recoverable error

export interface StabilityState {
  readonly checks: number;
  readonly streak: number;
  readonly last: StabilitySample | null;
  readonly phase: StabilityPhase;
}

export function initStability(): StabilityState {
  return { checks: 0, streak: 0, last: null, phase: 'waiting' };
}

function samplesEqual(a: StabilitySample, b: StabilitySample): boolean {
  return a.size === b.size && a.dateModified === b.dateModified;
}

/**
 * Fold one sample into the state. Once a terminal phase is reached the state is returned
 * unchanged (idempotent).
 */
export function recordSample(
  state: StabilityState,
  sample: StabilitySample,
  config: StabilityConfig = DEFAULT_STABILITY_CONFIG,
): StabilityState {
  if (state.phase !== 'waiting') {
    return state;
  }

  const checks = state.checks + 1;
  const streak =
    state.last !== null && samplesEqual(state.last, sample) ? state.streak + 1 : 1;

  // A settled file must have positive size, be accessible, and be stable across the
  // required streak of identical samples.
  const settled =
    sample.size > 0 && sample.accessible && streak >= config.requiredStableStreak;

  if (settled) {
    return { checks, streak, last: sample, phase: 'settled' };
  }
  if (checks >= config.maxChecks) {
    return { checks, streak, last: sample, phase: 'unstable' };
  }
  return { checks, streak, last: sample, phase: 'waiting' };
}

/** Convenience for tests / batch evaluation: fold an ordered list of samples. */
export function evaluateStability(
  samples: readonly StabilitySample[],
  config: StabilityConfig = DEFAULT_STABILITY_CONFIG,
): StabilityState {
  let state = initStability();
  for (const s of samples) {
    state = recordSample(state, s, config);
    if (state.phase !== 'waiting') {
      break;
    }
  }
  return state;
}
