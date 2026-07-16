import {
  DEFAULT_STABILITY_CONFIG,
  evaluateStability,
  initStability,
  recordSample,
  type StabilitySample,
} from '../src/core/stability';

const s = (size: number, dateModified: number, accessible = true): StabilitySample => ({
  size,
  dateModified,
  accessible,
});

describe('file stability reducer', () => {
  it('settles after the required streak of identical samples', () => {
    const res = evaluateStability([s(1000, 5), s(2000, 6), s(2000, 6)]);
    expect(res.phase).toBe('settled');
  });

  it('keeps waiting while the file is still growing (no premature error)', () => {
    let state = initStability();
    state = recordSample(state, s(1000, 1));
    state = recordSample(state, s(2000, 2));
    expect(state.phase).toBe('waiting');
  });

  it('declares unstable only after maxChecks without settling', () => {
    const growing = Array.from({ length: DEFAULT_STABILITY_CONFIG.maxChecks }, (_, i) =>
      s(1000 * (i + 1), i + 1),
    );
    const res = evaluateStability(growing);
    expect(res.phase).toBe('unstable');
  });

  it('does not settle on a zero-byte or inaccessible file even if unchanged', () => {
    expect(evaluateStability([s(0, 5), s(0, 5)]).phase).not.toBe('settled');
    expect(evaluateStability([s(1000, 5, false), s(1000, 5, false)]).phase).not.toBe('settled');
  });

  it('is idempotent once terminal', () => {
    const settled = evaluateStability([s(10, 1), s(10, 1)]);
    expect(settled.phase).toBe('settled');
    expect(recordSample(settled, s(999, 2))).toBe(settled);
  });
});
