import {
  canTransitionPhoto,
  canTransitionSession,
  isOpenCaptureSession,
} from '../src/core/captureState';

describe('capture state transitions', () => {
  it('allows only expected photo transitions', () => {
    expect(canTransitionPhoto('detected', 'waiting_stability')).toBe(true);
    expect(canTransitionPhoto('waiting_stability', 'stable')).toBe(true);
    expect(canTransitionPhoto('stable', 'excluded')).toBe(true);
    expect(canTransitionPhoto('excluded', 'stable')).toBe(false);
    expect(canTransitionPhoto('stable', 'undecodable')).toBe(false);
  });

  it('allows only expected session transitions', () => {
    expect(canTransitionSession('preparing', 'active')).toBe(true);
    expect(canTransitionSession('active', 'finishing')).toBe(true);
    expect(canTransitionSession('finishing', 'review')).toBe(true);
    expect(canTransitionSession('review', 'completed')).toBe(true);
    expect(canTransitionSession('completed', 'active')).toBe(false);
  });

  it('classifies open sessions', () => {
    expect(isOpenCaptureSession('preparing')).toBe(true);
    expect(isOpenCaptureSession('review')).toBe(true);
    expect(isOpenCaptureSession('completed')).toBe(false);
    expect(isOpenCaptureSession('cancelled')).toBe(false);
  });
});

