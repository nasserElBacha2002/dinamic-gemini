'use strict';

const OFFLINE_AISLE_SCHEMA_VERSION = 2;
const REQUIRED_OFFLINE_STAGES = [
  'offline_prepare',
  'offline_asset_prepare',
  'offline_payload_build',
  'offline_integrity',
  'offline_validation',
  'offline_zip',
  'offline_total_export',
];
const REQUIRED_ZIP_ENTRIES = ['manifest.json', 'aisle-package.json'];
const LEGACY_ZIP_PATHS = ['aisle.json', 'recognition/profiles.json'];

function isLegacyCaptureJson(entry) {
  return typeof entry === 'string' && entry.startsWith('captures/') && entry.endsWith('.json');
}

function collectOfflineAisleMetrics(events) {
  const byStage = {};
  for (const stage of REQUIRED_OFFLINE_STAGES) {
    byStage[stage] = (events || []).filter((e) => e && e.stage === stage);
  }
  const total = byStage.offline_total_export[0] || null;
  const extras = (total && total.extras) || {};
  return {
    stages: byStage,
    payloadBytes: extras.payloadBytes ?? null,
    zipBytes: extras.zipBytes ?? null,
    zipEntryCount: extras.zipEntryCount ?? null,
    captureCount: extras.captureCount ?? extras.offlineCaptureCount ?? null,
    assetCount: extras.assetCount ?? extras.offlineAssetCount ?? null,
    schemaVersion: extras.schemaVersion ?? extras.offlineAisleSchemaVersion ?? null,
    durationMs: total ? total.durationMs : null,
    success: total ? total.success === true : false,
  };
}

function assertOfflineAisleV2ZipLayout(entryPaths) {
  const failures = [];
  const names = new Set(entryPaths || []);
  for (const required of REQUIRED_ZIP_ENTRIES) {
    if (!names.has(required)) failures.push(`missing_${required}`);
  }
  for (const legacy of LEGACY_ZIP_PATHS) {
    if (names.has(legacy)) failures.push(`legacy_${legacy}`);
  }
  for (const entry of entryPaths || []) {
    if (isLegacyCaptureJson(entry)) failures.push(`legacy_${entry}`);
  }
  return failures;
}

function assertOfflineAisleRun(input) {
  const failures = [];
  const events = input.events || [];
  const status = input.status || {};
  const metrics = collectOfflineAisleMetrics(events);

  if (status.status && status.status !== 'COMPLETED') {
    failures.push(`status=${status.status}`);
  }
  if (status.errorCode) {
    failures.push(`errorCode=${status.errorCode}`);
  }

  for (const stage of REQUIRED_OFFLINE_STAGES) {
    const rows = metrics.stages[stage] || [];
    if (rows.length !== 1) {
      failures.push(`${stage}_count=${rows.length}`);
    } else if (rows[0].success !== true) {
      failures.push(`${stage}_failed`);
    }
  }

  if (metrics.schemaVersion != null && Number(metrics.schemaVersion) !== OFFLINE_AISLE_SCHEMA_VERSION) {
    failures.push(`schemaVersion=${metrics.schemaVersion}`);
  }
  if (metrics.payloadBytes == null || Number(metrics.payloadBytes) < 0) {
    failures.push('payloadBytes_missing');
  }
  if (metrics.zipBytes == null || Number(metrics.zipBytes) <= 0) {
    failures.push('zipBytes_missing');
  }
  if (metrics.zipEntryCount == null || Number(metrics.zipEntryCount) < 2) {
    failures.push('zipEntryCount_missing');
  }

  const zipEntries = input.zipEntries || [];
  if (zipEntries.length > 0) {
    for (const layoutFailure of assertOfflineAisleV2ZipLayout(zipEntries)) {
      failures.push(layoutFailure);
    }
    if (
      metrics.zipEntryCount != null &&
      Number(metrics.zipEntryCount) !== zipEntries.length
    ) {
      failures.push(
        `zipEntryCount_physical_mismatch:metrics=${metrics.zipEntryCount}:zip=${zipEntries.length}`,
      );
    }
  }

  const validator = input.validatorResult;
  if (!validator || validator.valid !== true) {
    const errors = validator && Array.isArray(validator.errors) ? validator.errors : ['validator_not_run'];
    failures.push(`backend_validator_failed:${errors.join('|')}`);
  } else if (Number(validator.manifest?.schema_version) !== OFFLINE_AISLE_SCHEMA_VERSION) {
    failures.push(`schemaVersion=${validator.manifest?.schema_version ?? 'missing'}`);
  }
  if (
    input.expectedCaptureCount != null &&
    Number(validator?.manifest?.capture_count) !== Number(input.expectedCaptureCount)
  ) {
    failures.push(
      `capture_count=${validator?.manifest?.capture_count ?? 'missing'} expected=${input.expectedCaptureCount}`,
    );
  }
  return { ok: failures.length === 0, failures, metrics };
}

module.exports = {
  OFFLINE_AISLE_SCHEMA_VERSION,
  REQUIRED_OFFLINE_STAGES,
  REQUIRED_ZIP_ENTRIES,
  collectOfflineAisleMetrics,
  assertOfflineAisleV2ZipLayout,
  assertOfflineAisleRun,
};
