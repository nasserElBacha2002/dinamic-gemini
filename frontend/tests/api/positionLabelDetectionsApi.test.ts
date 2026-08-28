/**
 * Frontend labels for position detection statuses (P1 copy rules).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  labelForPositionDetectionStatus,
  listJobPositionDetections,
} from '../../src/api/positionLabelDetectionsApi';

const apiRequestJson = vi.fn();

vi.mock('../../src/api/request', () => ({
  apiRequestJson: (...args: unknown[]) => apiRequestJson(...args),
}));

describe('labelForPositionDetectionStatus', () => {
  it('covers known resolved and unresolved statuses', () => {
    expect(labelForPositionDetectionStatus('VALID')).toBe(
      'Firma válida — posición resuelta',
    );
    expect(labelForPositionDetectionStatus('LEGACY_UNSIGNED_REQUIRES_REVIEW')).toMatch(
      /sin firma/i,
    );
    expect(labelForPositionDetectionStatus('LABEL_NOT_FOUND')).toContain('no resuelta');
    expect(labelForPositionDetectionStatus('INVALID_SIGNATURE')).toContain('firma');
    expect(labelForPositionDetectionStatus('SIGNATURE_VALIDATION_SKIPPED')).toContain(
      'no validada',
    );
    expect(labelForPositionDetectionStatus('DETECTION_CONTEXT_INVALID')).toContain(
      'contexto',
    );
    expect(labelForPositionDetectionStatus('AMBIGUOUS_POSITION_DETECTION')).toContain(
      'ambigua',
    );
  });

  it('treats FEATURE_DISABLED and NO_LABEL as absence', () => {
    expect(labelForPositionDetectionStatus('FEATURE_DISABLED')).toBe(
      'Sin etiqueta de posición',
    );
    expect(labelForPositionDetectionStatus('NO_LABEL')).toBe('Sin etiqueta de posición');
  });

  it('uses neutral copy for unknown statuses (does not invent unresolved)', () => {
    expect(labelForPositionDetectionStatus('SOMETHING_NEW')).toBe(
      'Estado de etiqueta de posición: SOMETHING_NEW',
    );
    expect(labelForPositionDetectionStatus('POSITION_WEIRD')).toBe(
      'Estado de etiqueta de posición: POSITION_WEIRD',
    );
  });
});

describe('listJobPositionDetections URL', () => {
  beforeEach(() => {
    apiRequestJson.mockReset();
    apiRequestJson.mockResolvedValue({ items: [] });
  });

  it('builds URL via apiRequestJson with API_BASE prefix pattern', async () => {
    await listJobPositionDetections('inv-1', 'job-1');
    expect(apiRequestJson).toHaveBeenCalledTimes(1);
    const url = apiRequestJson.mock.calls[0][0] as string;
    expect(url).toContain('/api/v3/inventories/inv-1/jobs/job-1/position-detections');
    expect(url).not.toMatch(/^undefined/);
  });
});
