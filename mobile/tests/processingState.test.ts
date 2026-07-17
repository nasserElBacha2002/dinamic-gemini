import {
  mapProcessingPersistence,
  processingStateLabel,
  toProcessingState,
} from '../src/core/processingState';

describe('processingState', () => {
  it.each([
    ['queued', 'queued'],
    ['pending', 'queued'],
    ['starting', 'starting'],
    ['running', 'processing'],
    ['processing', 'processing'],
    ['completed', 'completed'],
    ['success', 'completed'],
    ['succeeded', 'completed'],
    ['failed', 'failed'],
    ['error', 'failed'],
    ['cancelled', 'cancelled'],
    ['canceled', 'cancelled'],
    ['weird_status', 'unknown'],
  ])('maps remote %s to %s', (remote, expected) => {
    expect(toProcessingState(remote)).toBe(expected);
    expect(processingStateLabel(toProcessingState(remote))).toBeTruthy();
  });

  it.each([
    ['queued', 'pending', 'processing', false],
    ['running', 'running', 'processing', false],
    ['completed', 'success', 'completed', true],
    ['success', 'success', 'completed', true],
    ['failed', 'failed', 'failed_processing', true],
    ['cancelled', 'cancelled', 'failed_processing', true],
  ])('persist mapping for %s', (remote, jobStatus, captureStatus, terminal) => {
    expect(mapProcessingPersistence(remote)).toMatchObject({
      jobStatus,
      captureStatus,
      terminal,
    });
  });
});
