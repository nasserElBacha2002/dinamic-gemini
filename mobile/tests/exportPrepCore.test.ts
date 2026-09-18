import { exportPhotoFileName } from '../src/features/exportPrep/exportPhotoFileName';
import { EXPORT_PREP_STATUSES } from '../src/features/exportPrep/exportPrepTypes';
import { resolveFeatureFlags, DEFAULT_FEATURE_FLAGS } from '../src/core/featureFlags';
import { MIGRATIONS } from '../src/database/migrations/migrations';

describe('exportPhotoFileName', () => {
  it('matches legacy ZIP basename contract', () => {
    expect(exportPhotoFileName('session-1:1', 1, 'photo.HEIC')).toBe('0001_session-1_1.HEIC');
    expect(exportPhotoFileName('abc', 12, 'x.jpg')).toBe('0012_abc.jpg');
    expect(exportPhotoFileName('a/b', 3, null)).toBe('0003_a_b.jpg');
  });

  it('is stable across reopen (deterministic)', () => {
    const a = exportPhotoFileName('p1', 7, 'n.png');
    const b = exportPhotoFileName('p1', 7, 'n.png');
    expect(a).toBe(b);
  });
});

describe('export prep statuses', () => {
  it('includes required state machine values', () => {
    expect(EXPORT_PREP_STATUSES).toEqual([
      'QUEUED',
      'PREPARING',
      'SCANNING',
      'VALIDATING',
      'READY',
      'FAILED_RETRYABLE',
      'FAILED_TERMINAL',
      'EXCLUDED',
    ]);
  });
});

describe('mobileExportPrepQueue flag', () => {
  it('defaults on in non-production; off in production; kill-switch and explicit opt-in', () => {
    expect(DEFAULT_FEATURE_FLAGS.mobileExportPrepQueue).toBe(true);
    expect(resolveFeatureFlags({}, 'production').mobileExportPrepQueue).toBe(false);
    expect(resolveFeatureFlags({}, 'development').mobileExportPrepQueue).toBe(true);
    expect(resolveFeatureFlags({}, 'staging').mobileExportPrepQueue).toBe(true);
    expect(resolveFeatureFlags({ mobileExportPrepQueue: '0' }, 'development').mobileExportPrepQueue).toBe(
      false,
    );
    expect(resolveFeatureFlags({ mobileExportPrepQueue: '1' }, 'production').mobileExportPrepQueue).toBe(
      true,
    );
  });
});

describe('migration 35 export_prep_jobs', () => {
  it('is present and idempotent CREATE IF NOT EXISTS', () => {
    const v35 = MIGRATIONS.find((m) => m.version === 35);
    expect(v35?.sql).toContain('CREATE TABLE IF NOT EXISTS export_prep_jobs');
    expect(v35?.sql).toContain('CREATE INDEX IF NOT EXISTS idx_export_prep_jobs_session_status');
  });
});
