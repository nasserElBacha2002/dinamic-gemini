#!/usr/bin/env node
/**
 * Mac-side ADB coordinator for the Android mobile pipeline benchmark.
 * Does NOT process images locally — copies fixtures and polls device status.
 *
 * Usage:
 *   npm run benchmark:pipeline -- --input ../../andes_benchmark_50 --device R58N30GNF2T --photos 3
 */
'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawnSync, execFileSync } = require('child_process');

const AUTHORIZED_CLIENT = '8a3c9a01-7494-4be0-99be-595ecbf2b9bd';
const AUTHORIZED_SUPPLIER = 'bce1460e-7238-4e39-82ec-8c4e51dcb9ca';
const PACKAGE = 'com.dinamic.inventory.capture';
const EXPECTED_PROFILE = 'andes';

function die(code, message) {
  console.error(`ERROR[${code}]: ${message}`);
  process.exit(1);
}

function parseArgs(argv) {
  const out = {
    input: null,
    clientId: AUTHORIZED_CLIENT,
    supplierId: AUTHORIZED_SUPPLIER,
    runs: 1,
    photos: 3,
    device: null,
    confirmFullRun: false,
    cooldownMs: 5000,
    timeoutMs: 20 * 60 * 1000,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    const next = () => {
      const v = argv[++i];
      if (v == null) die('ARGS', `missing value for ${a}`);
      return v;
    };
    if (a === '--input') out.input = next();
    else if (a === '--client-id') out.clientId = next();
    else if (a === '--supplier-id') out.supplierId = next();
    else if (a === '--runs') out.runs = Number(next());
    else if (a === '--photos') out.photos = Number(next());
    else if (a === '--device') out.device = next();
    else if (a === '--confirm-full-run') out.confirmFullRun = true;
    else if (a === '--cooldown-ms') out.cooldownMs = Number(next());
    else if (a === '--timeout-ms') out.timeoutMs = Number(next());
    else if (a === '--help' || a === '-h') {
      console.log(`See mobile/scripts/benchmark-pipeline.mjs header`);
      process.exit(0);
    } else die('ARGS', `unknown arg ${a}`);
  }
  if (!out.input) die('ARGS', '--input is required');
  return out;
}

function resolveInputDir(raw) {
  const resolved = path.resolve(process.cwd(), raw);
  if (!fs.existsSync(resolved) || !fs.statSync(resolved).isDirectory()) {
    die('INPUT', `input directory not found: ${resolved}`);
  }
  // Refuse copying into the git repo by accident when input is inside mobile/
  const repoMobile = path.resolve(__dirname, '..');
  if (resolved.startsWith(repoMobile + path.sep)) {
    die('INPUT', 'fixtures must stay outside the mobile package directory');
  }
  return resolved;
}

function parseManifest(text) {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (lines.length < 2) die('MANIFEST', 'empty manifest');
  const rows = [];
  const seen = new Set();
  for (let i = 1; i < lines.length; i += 1) {
    const cols = lines[i].split(',');
    if (cols.length < 8) die('MANIFEST', `bad row ${i}`);
    const filename = cols[1].trim();
    if (seen.has(filename)) die('MANIFEST', `duplicate filename ${filename}`);
    seen.add(filename);
    rows.push({
      sequence: Number(cols[0]),
      filename,
      type: cols[2].trim().toLowerCase(),
      sourceTemplate: cols[3].trim(),
      width: Number(cols[4]),
      height: Number(cols[5]),
      sizeBytes: Number(cols[6]),
      sha256: cols[7].trim().toLowerCase(),
    });
  }
  return rows;
}

function selectFixtures(rows, photos) {
  if (photos === 3) {
    const positions = rows.filter((r) => r.type === 'position');
    const items = rows.filter((r) => r.type === 'item');
    if (positions.length < 1 || items.length < 2) die('SMOKE', 'need 1 position + 2 item');
    return [positions[0], items[0], items[1]];
  }
  if (photos < 1 || photos > rows.length) die('PHOTOS', 'invalid --photos');
  return rows.slice(0, photos);
}

function sha256File(filePath) {
  const hash = crypto.createHash('sha256');
  hash.update(fs.readFileSync(filePath));
  return hash.digest('hex');
}

function adb(device, args, opts = {}) {
  const base = device ? ['-s', device] : [];
  const full = [...base, ...args];
  const res = spawnSync('adb', full, {
    encoding: 'utf8',
    maxBuffer: 20 * 1024 * 1024,
    ...opts,
  });
  if (res.error) die('ADB', res.error.message);
  if (res.status !== 0 && !opts.allowFail) {
    die('ADB', `adb ${full.join(' ')} failed: ${res.stderr || res.stdout}`);
  }
  return res;
}

function listDevices() {
  const out = adb(null, ['devices', '-l']).stdout || '';
  return out
    .split('\n')
    .slice(1)
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('*'))
    .map((l) => l.split(/\s+/)[0])
    .filter((id) => id && id !== 'List');
}

function runAs(device, shellCmd) {
  // One shell string so `sh -c` receives the full command.
  const quoted = shellCmd.replace(/'/g, `'"'"'`);
  return adb(device, ['shell', `run-as ${PACKAGE} sh -c '${quoted}'`]);
}

function pushViaTmp(device, localPath, remoteRelUnderFiles) {
  const tmp = `/data/local/tmp/dinamic-bench-${path.basename(localPath)}-${Date.now()}`;
  adb(device, ['push', localPath, tmp]);
  const destDir = path.posix.dirname(`files/${remoteRelUnderFiles}`);
  runAs(device, `mkdir -p ${destDir}`);
  // Copy into app-private files
  adb(device, [
    'shell',
    `cat ${tmp} | run-as ${PACKAGE} sh -c 'cat > files/${remoteRelUnderFiles}'`,
  ]);
  adb(device, ['shell', 'rm', '-f', tmp], { allowFail: true });
}

function pullViaTmp(device, remoteRelUnderFiles, localPath) {
  const tmp = `/data/local/tmp/dinamic-bench-pull-${Date.now()}`;
  const res = adb(
    device,
    ['shell', `run-as ${PACKAGE} cat files/${remoteRelUnderFiles} > ${tmp}`],
    { allowFail: true },
  );
  if (res.status !== 0) {
    // fallback: run-as cat to stdout
    const cat = runAs(device, `cat files/${remoteRelUnderFiles}`);
    fs.mkdirSync(path.dirname(localPath), { recursive: true });
    fs.writeFileSync(localPath, cat.stdout, 'utf8');
    return;
  }
  adb(device, ['pull', tmp, localPath]);
  adb(device, ['shell', 'rm', '-f', tmp], { allowFail: true });
}

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function pollStatus(device, runId, timeoutMs) {
  const started = Date.now();
  let last = null;
  while (Date.now() - started < timeoutMs) {
    const raw = adb(
      device,
      ['shell', 'run-as', PACKAGE, 'cat', `files/benchmark/${runId}/status.json`],
      { allowFail: true },
    );
    if (raw.status === 0 && raw.stdout && raw.stdout.trim().startsWith('{')) {
      try {
        last = JSON.parse(raw.stdout);
        if (last.status === 'COMPLETED' || last.status === 'FAILED' || last.status === 'TIMEOUT') {
          return last;
        }
      } catch {
        // keep polling
      }
    }
    sleep(2000);
  }
  return last
    ? { ...last, status: 'TIMEOUT', errorCode: 'TIMEOUT' }
    : {
        status: 'TIMEOUT',
        benchmarkRunId: runId,
        errorCode: 'TIMEOUT',
        errorDetail: 'no status.json',
        terminalCount: 0,
        expectedCount: 0,
        pendingJobs: -1,
      };
}

function devicePreflightSqlite(device) {
  const tmpDb = path.join(require('os').tmpdir(), `dinamic-bench-preflight-${Date.now()}.db`);
  adb(device, [
    'shell',
    `run-as ${PACKAGE} cat files/SQLite/dinamic_mobile.db`,
  ]);
  // pull via stdout redirect is awkward; use adb exec-out
  const buf = execFileSync(
    'adb',
    device
      ? ['-s', device, 'exec-out', 'run-as', PACKAGE, 'cat', 'files/SQLite/dinamic_mobile.db']
      : ['exec-out', 'run-as', PACKAGE, 'cat', 'files/SQLite/dinamic_mobile.db'],
    { maxBuffer: 50 * 1024 * 1024 },
  );
  fs.writeFileSync(tmpDb, buf);
  const sql = (q) =>
    execFileSync('sqlite3', [tmpDb, q], { encoding: 'utf8' }).trim();
  const row = sql(
    `SELECT id, client_id, name, active FROM local_client_suppliers WHERE id='${AUTHORIZED_SUPPLIER}';`,
  );
  if (!row) {
    fs.unlinkSync(tmpDb);
    return {
      ok: false,
      code: 'BENCHMARK_PROFILE_PREFLIGHT_FAILED',
      detail: 'ClientSupplier missing on device',
    };
  }
  const [id, clientId, name, active] = row.split('|');
  if (clientId !== AUTHORIZED_CLIENT || id !== AUTHORIZED_SUPPLIER) {
    fs.unlinkSync(tmpDb);
    return { ok: false, code: 'BENCHMARK_PROFILE_PREFLIGHT_FAILED', detail: 'id mismatch' };
  }
  if (String(active) !== '1') {
    fs.unlinkSync(tmpDb);
    return { ok: false, code: 'BENCHMARK_PROFILE_PREFLIGHT_FAILED', detail: 'inactive' };
  }
  if (String(name).toLowerCase() !== EXPECTED_PROFILE) {
    fs.unlinkSync(tmpDb);
    return {
      ok: false,
      code: 'BENCHMARK_PROFILE_PREFLIGHT_FAILED',
      detail: `profile name ${name}`,
    };
  }
  const inv = 'f00e01a8-1514-46a4-a5b9-711ead486509';
  const sources = sql(
    `SELECT item_source, position_source FROM offline_supplier_recognition_config WHERE inventory_id='${inv}' AND client_supplier_id='${AUTHORIZED_SUPPLIER}';`,
  );
  if (!sources || !sources.startsWith('SUPPLIER|SUPPLIER')) {
    fs.unlinkSync(tmpDb);
    return {
      ok: false,
      code: 'BENCHMARK_PROFILE_PREFLIGHT_FAILED',
      detail: `sources=${sources || 'missing'}`,
    };
  }
  const itemVer = sql(
    `SELECT profile_version FROM offline_recognition_profiles WHERE inventory_id='${inv}' AND client_supplier_id='${AUTHORIZED_SUPPLIER}' AND label_kind='ITEM';`,
  );
  const posVer = sql(
    `SELECT profile_version FROM offline_recognition_profiles WHERE inventory_id='${inv}' AND client_supplier_id='${AUTHORIZED_SUPPLIER}' AND label_kind='POSITION';`,
  );
  fs.unlinkSync(tmpDb);
  if (!itemVer || !posVer) {
    return {
      ok: false,
      code: 'BENCHMARK_PROFILE_PREFLIGHT_FAILED',
      detail: 'ITEM/POSITION profile missing',
    };
  }
  return {
    ok: true,
    resolvedClientSupplierId: id,
    resolvedProfileName: name.toLowerCase(),
    itemProfileVersion: Number(itemVer),
    positionProfileVersion: Number(posVer),
    hostInventoryId: inv,
  };
}

function ensureDebuggable(device) {
  const flags = adb(device, [
    'shell',
    'dumpsys',
    'package',
    PACKAGE,
  ]).stdout;
  if (!/DEBUGGABLE/.test(flags)) {
    die('RELEASE_BLOCKED', 'installed app is not DEBUGGABLE');
  }
  const pid = adb(device, ['shell', 'pidof', PACKAGE], { allowFail: true }).stdout.trim();
  if (!pid) {
    adb(device, [
      'shell',
      'monkey',
      '-p',
      PACKAGE,
      '-c',
      'android.intent.category.LAUNCHER',
      '1',
    ]);
    sleep(4000);
  }
}

function writeReportDir(root, files) {
  fs.mkdirSync(root, { recursive: true });
  for (const [name, content] of Object.entries(files)) {
    fs.writeFileSync(path.join(root, name), content);
  }
}

function median(values) {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function readJsonl(filePath) {
  if (!fs.existsSync(filePath)) return [];
  return fs
    .readFileSync(filePath, 'utf8')
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => {
      try {
        return JSON.parse(l);
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

/**
 * Mac-side instrumentation gate for smoke acceptance.
 * Pipeline COMPLETED alone is not enough — instrumentation criteria must pass.
 */
function validateSmokeInstrumentation(events, status) {
  const failures = [];
  if (status.status !== 'COMPLETED') {
    failures.push(`status=${status.status}`);
  }
  if (status.terminalCount !== status.expectedCount) {
    failures.push(`terminalCount ${status.terminalCount} != expected ${status.expectedCount}`);
  }
  if (status.pendingJobs !== 0) {
    failures.push(`pendingJobs=${status.pendingJobs}`);
  }

  const photoEvents = events.filter((e) => e.photoId);
  const missingFixture = photoEvents.filter((e) => e.fixtureId == null || e.fixtureId === '');
  if (missingFixture.length) {
    failures.push(`fixtureId_missing=${missingFixture.length}`);
  }

  const terminals = events.filter((e) => e.stage === 'photo_terminal');
  const positionBad = terminals.filter(
    (e) =>
      e.errorCode === 'POSITION_LABEL_DETECTED' &&
      !(e.outcome === 'position_detected' && e.success === true),
  );
  if (positionBad.length) {
    failures.push(`position_misclassified=${positionBad.length}`);
  }
  const falseTech = terminals.filter(
    (e) =>
      e.outcome === 'scanner_technical_error' &&
      (e.errorCode === 'POSITION_LABEL_DETECTED' || e.errorCode === 'POSITION_LABEL_DUPLICATE'),
  );
  if (falseTech.length) {
    failures.push(`false_scanner_technical_error=${falseTech.length}`);
  }

  const zipEntries = events.filter((e) => e.stage === 'zip_entry');
  const kinds = new Set(zipEntries.map((e) => (e.extras && e.extras.entryKind) || ''));
  if (!kinds.has('csv')) failures.push('zip_entry_csv_missing');
  if (!kinds.has('manifest')) failures.push('zip_entry_manifest_missing');
  if (!kinds.has('photo')) failures.push('zip_entry_photo_missing');

  const finalize = events.filter((e) => e.stage === 'zip_finalize');
  const totalExport = events.filter((e) => e.stage === 'total_export');
  if (!finalize.length) failures.push('zip_finalize_missing');
  if (finalize.length && totalExport.length) {
    const fDur = finalize[0].durationMs;
    const tDur = totalExport[0].durationMs;
    if (tDur > 0 && Math.abs(fDur - tDur) / tDur < 0.05) {
      failures.push('zip_finalize_≈_total_export');
    }
  }

  const validation = events.filter((e) => e.stage === 'zip_validation');
  if (!validation.length) failures.push('zip_validation_missing');
  else if (!(validation[0].durationMs > 0)) failures.push('zip_validation_duration_zero');

  const hashStages = events.filter((e) =>
    ['staging_hash', 'strong_validation_hash', 'export_resolution_hash', 'zip_entry_hash'].includes(
      e.stage,
    ),
  );
  if (!hashStages.some((e) => e.stage === 'staging_hash')) {
    failures.push('staging_hash_missing');
  }
  const stagingNativeOk = events.some(
    (e) =>
      e.stage === 'staging_hash' &&
      (e.extras?.hashMode === 'native_file' || e.extras?.hashImplementation === 'native_stream'),
  );
  if (!stagingNativeOk) failures.push('staging_hash_not_native_file');

  const base64Count = events.filter(
    (e) =>
      e.extras?.hashMode === 'js_base64_full_file' ||
      e.extras?.hashImplementation === 'js_base64_full_file' ||
      e.extras?.base64FullFileHashCount > 0,
  ).length;
  // Also trust aggregate on total_pipeline if present
  const tp = events.find((e) => e.stage === 'total_pipeline');
  const base64Agg =
    tp && typeof tp.extras?.base64FullFileHashCount === 'number'
      ? tp.extras.base64FullFileHashCount
      : null;
  if (base64Count > 0 || base64Agg > 0) {
    failures.push('base64_full_file_hash_present');
  }

  const strongHashes = events.filter((e) => e.stage === 'strong_validation_hash');
  if (status.expectedCount >= 3) {
    if (strongHashes.length < status.expectedCount) {
      failures.push(`strong_validation_hash_count=${strongHashes.length}`);
    }
    const reused = strongHashes.filter((e) => e.extras?.hashMode === 'reused_persisted');
    if (reused.length !== status.expectedCount) {
      failures.push(`strong_reused_persisted=${reused.length}/${status.expectedCount}`);
    }
    const fallback = strongHashes.filter((e) => e.extras?.hashSource === 'validation_fallback');
    if (fallback.length !== 0) {
      failures.push(`validation_fallback_unexpected=${fallback.length}`);
    }
  }

  const draftLookup = events.filter((e) => e.stage === 'draft_lookup');
  if (!draftLookup.length) failures.push('draft_lookup_missing');
  else if (draftLookup.some((e) => !(e.extras && e.extras.lookupMode))) {
    failures.push('draft_lookup_metrics_incomplete');
  }

  const queueOk = events.some(
    (e) =>
      typeof e.queueDepth === 'number' ||
      (e.extras && (e.extras.queueDepthAtEnd != null || e.extras.notAvailableReason)),
  );
  if (!queueOk) failures.push('queue_depth_missing');

  const cleanup = events.filter((e) => e.stage === 'cleanup');
  if (!cleanup.length || cleanup.some((e) => e.success !== true)) {
    failures.push('cleanup_failed_or_missing');
  }

  return {
    ok: failures.length === 0,
    failures,
    summary: {
      eventCount: events.length,
      photoEventCount: photoEvents.length,
      zipEntryCount: zipEntries.length,
      zipEntryKinds: [...kinds],
      terminals: terminals.map((t) => ({
        fixtureId: t.fixtureId,
        outcome: t.outcome,
        success: t.success,
        errorCode: t.errorCode,
        durationMs: t.durationMs,
        scannerProcessingMs: t.extras && t.extras.scannerProcessingMs,
        photoPipelineWallMs: t.extras && t.extras.photoPipelineWallMs,
      })),
    },
  };
}

function buildStageSummaryCsv(events) {
  const byStage = new Map();
  for (const e of events) {
    const cur = byStage.get(e.stage) || { stage: e.stage, count: 0, sumMs: 0, maxMs: 0 };
    cur.count += 1;
    cur.sumMs += Number(e.durationMs) || 0;
    cur.maxMs = Math.max(cur.maxMs, Number(e.durationMs) || 0);
    byStage.set(e.stage, cur);
  }
  const lines = ['stage,count,sumMs,maxMs,avgMs'];
  for (const row of [...byStage.values()].sort((a, b) => a.stage.localeCompare(b.stage))) {
    const avg = row.count ? row.sumMs / row.count : 0;
    lines.push(`${row.stage},${row.count},${row.sumMs.toFixed(3)},${row.maxMs.toFixed(3)},${avg.toFixed(3)}`);
  }
  return lines.join('\n') + '\n';
}

function buildSmokeComparison(prev, next, nextRunId) {
  return `# Smoke comparison (instrumentation validation)

Prior smoke (misclassified instrumentation):
- benchmarkRunId = 0253ee4f-5c6b-4174-b6bf-676d4f24087b
- terminalCount: 3 / expected 3 / pendingJobs 0
- totalPipeline: 6755 ms
- postLastInput: 4448 ms
- POSITION: errorCode=POSITION_LABEL_DETECTED outcome=scanner_technical_error success=false (**bug**)
- ITEM: decoded_accepted ×2
- Defects: fixtureId=null, no zip_entry, csv_write/zip_validation durationMs=0, zip_close≈total_export

Corrected smoke:
- benchmarkRunId = ${nextRunId}
- status: ${next.status}
- terminalCount: ${next.terminalCount} / expected ${next.expectedCount} / pendingJobs ${next.pendingJobs}
- instrumentation: ${next.instrumentationOk ? 'VALIDATED' : 'INVALID'}
- failures: ${(next.failures || []).join('; ') || 'none'}
- eventCount: ${next.eventCount}
- POSITION outcomes: ${(next.positionOutcomes || []).join(', ') || 'n/a'}
- ITEM outcomes: ${(next.itemOutcomes || []).join(', ') || 'n/a'}
- total_pipeline_ms: ${next.totalPipelineMs ?? 'n/a'}
- zip_entry kinds: ${(next.zipEntryKinds || []).join(', ') || 'n/a'}
- zip_finalize_ms: ${next.zipFinalizeMs ?? 'n/a'}
- zip_validation_ms: ${next.zipValidationMs ?? 'n/a'}
- fixtureId_complete: ${next.fixtureIdComplete}

**Do not treat timing deltas as performance improvements** — this phase validates measurement only.
`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.clientId !== AUTHORIZED_CLIENT || args.supplierId !== AUTHORIZED_SUPPLIER) {
    die('UNAUTHORIZED_IDS', 'client/supplier must match authorized Andes IDs');
  }

  const inputDir = resolveInputDir(args.input);
  const manifestPath = path.join(inputDir, 'manifest.csv');
  if (!fs.existsSync(manifestPath)) die('MANIFEST', 'manifest.csv missing');
  const allRows = parseManifest(fs.readFileSync(manifestPath, 'utf8'));
  if (allRows.length !== 50) {
    console.warn(`WARN: manifest has ${allRows.length} rows (expected 50 for full suite)`);
  }

  const devices = listDevices().filter((d) => d !== 'unauthorized');
  if (devices.length === 0) {
    console.error('DEVICE_BENCHMARK_NOT_RUN: no adb devices');
    process.exit(2);
  }
  if (!args.device && devices.length > 1) {
    die('DEVICE', `multiple devices; pass --device. found=${devices.join(',')}`);
  }
  const device = args.device || devices[0];
  if (args.device && !devices.includes(args.device)) {
    die('DEVICE', `device ${args.device} not connected`);
  }

  ensureDebuggable(device);
  const preflight = devicePreflightSqlite(device);
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const outRoot = path.resolve(
    __dirname,
    '../../audit/mobile-pipeline/benchmark',
    stamp,
  );
  fs.mkdirSync(outRoot, { recursive: true });

  const configDoc = {
    clientId: AUTHORIZED_CLIENT,
    supplierRouteId: AUTHORIZED_SUPPLIER,
    resolvedClientSupplierId: preflight.resolvedClientSupplierId || null,
    expectedProfile: EXPECTED_PROFILE,
    resolvedClientId: AUTHORIZED_CLIENT,
    resolvedSupplierId: AUTHORIZED_SUPPLIER,
    resolvedProfileName: preflight.resolvedProfileName || null,
    itemProfileVersion: preflight.itemProfileVersion || null,
    positionProfileVersion: preflight.positionProfileVersion || null,
    configurationSource: 'device_sqlite_offline_recognition',
    snapshotResolved: preflight.ok === true,
    hostInventoryId: preflight.hostInventoryId || null,
  };
  fs.writeFileSync(path.join(outRoot, 'benchmark-config.json'), JSON.stringify(configDoc, null, 2));

  if (!preflight.ok) {
    fs.writeFileSync(
      path.join(outRoot, 'benchmark-errors.txt'),
      `${preflight.code}\n${preflight.detail}\n`,
    );
    fs.writeFileSync(
      path.join(outRoot, 'benchmark-report.md'),
      `# Benchmark\n\nStatus: BENCHMARK_PROFILE_PREFLIGHT_FAILED\n\n${preflight.detail}\n`,
    );
    console.error('BENCHMARK_PROFILE_PREFLIGHT_FAILED', preflight.detail);
    process.exit(3);
  }

  const props = adb(device, ['shell', 'getprop']).stdout;
  const model = (props.match(/\[ro.product.model\]: \[(.+?)\]/) || [])[1] || 'unknown';
  const manufacturer =
    (props.match(/\[ro.product.manufacturer\]: \[(.+?)\]/) || [])[1] || 'unknown';
  const release = (props.match(/\[ro.build.version.release\]: \[(.+?)\]/) || [])[1] || 'unknown';
  const sdk = (props.match(/\[ro.build.version.sdk\]: \[(.+?)\]/) || [])[1] || null;
  const gitSha = spawnSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).stdout.trim();
  const dirty =
    spawnSync('git', ['status', '--porcelain'], { encoding: 'utf8' }).stdout.trim() !== '';
  const smokeFixtureBytes = selectFixtures(allRows, 3).reduce((a, r) => a + r.sizeBytes, 0);
  const envDoc = {
    appVersion: null,
    appBuild: null,
    appVersionUnavailableReason: 'filled_from_device_environment_json_after_run',
    jsEngine: null,
    batteryLevelStart: null,
    batteryLevelEnd: null,
    batteryCharging: null,
    batteryUnavailableReason: 'expo-battery_not_installed',
    thermalStatusStart: null,
    thermalStatusEnd: null,
    thermalStatusUnavailableReason: 'android_thermal_api_not_wired',
    freeStorageBytesStart: null,
    freeStorageBytesEnd: null,
    freeStorageUnavailableReason: 'filled_from_device_after_run',
    totalFixtureBytes: smokeFixtureBytes,
    fixtureCount: 3,
    exportPrepMaxWorkers: 1,
    scannerConcurrency: 1,
    deviceManufacturer: manufacturer,
    deviceModel: model,
    androidRelease: release,
    androidSdk: sdk ? Number(sdk) : null,
    package: PACKAGE,
    device,
    gitSha,
    dirty,
    uploadHttpEnabled: false,
    concurrency: { exportPrepMaxWorkers: 1 },
    profile: configDoc,
    baselineNote: 'baseline del working tree exacto utilizado',
  };
  fs.writeFileSync(path.join(outRoot, 'benchmark-environment.json'), JSON.stringify(envDoc, null, 2));

  // --- Smoke ---
  const smokeFixtures = selectFixtures(allRows, 3);
  for (const fx of smokeFixtures) {
    const fp = path.join(inputDir, fx.filename);
    if (!fs.existsSync(fp)) die('FIXTURE', `missing ${fx.filename}`);
    const dig = sha256File(fp);
    if (dig !== fx.sha256) die('FIXTURE_HASH', `${fx.filename} hash mismatch`);
  }

  const smokeStatus = await runOne({
    device,
    inputDir,
    fixtures: smokeFixtures,
    coldWarm: 'cold',
    timeoutMs: args.timeoutMs,
    outRoot,
    runLabel: 'smoke',
  });

  const smokeEventsPath = path.join(outRoot, 'smoke-events.jsonl');
  const smokeEvents = readJsonl(smokeEventsPath);
  const instr = validateSmokeInstrumentation(smokeEvents, smokeStatus);

  // Merge device environment if present
  try {
    pullViaTmp(
      device,
      `benchmark/${smokeStatus.benchmarkRunId}/environment.json`,
      path.join(outRoot, 'device-environment.json'),
    );
    const deviceEnv = JSON.parse(
      fs.readFileSync(path.join(outRoot, 'device-environment.json'), 'utf8'),
    );
    const merged = { ...envDoc, ...deviceEnv, gitSha, dirty, package: PACKAGE, device };
    fs.writeFileSync(path.join(outRoot, 'benchmark-environment.json'), JSON.stringify(merged, null, 2));
  } catch {
    // device env optional if pull fails
  }

  fs.writeFileSync(path.join(outRoot, 'benchmark-stage-summary.csv'), buildStageSummaryCsv(smokeEvents));

  const terminals = smokeEvents.filter((e) => e.stage === 'photo_terminal');
  const totalPipeline = smokeEvents.find((e) => e.stage === 'total_pipeline');
  const zipFinalize = smokeEvents.find((e) => e.stage === 'zip_finalize');
  const zipValidation = smokeEvents.find((e) => e.stage === 'zip_validation');
  const zipEntries = smokeEvents.filter((e) => e.stage === 'zip_entry');
  const comparison = buildSmokeComparison(
    {},
    {
      status: smokeStatus.status,
      terminalCount: smokeStatus.terminalCount,
      expectedCount: smokeStatus.expectedCount,
      pendingJobs: smokeStatus.pendingJobs,
      instrumentationOk: instr.ok,
      failures: instr.failures,
      eventCount: smokeEvents.length,
      positionOutcomes: terminals
        .filter((t) => String(t.errorCode || '').includes('POSITION') || t.outcome === 'position_detected')
        .map((t) => t.outcome),
      itemOutcomes: terminals
        .filter((t) => t.outcome === 'decoded_accepted' || t.outcome === 'decoded_duplicate')
        .map((t) => t.outcome),
      totalPipelineMs: totalPipeline ? totalPipeline.durationMs : null,
      zipEntryKinds: [...new Set(zipEntries.map((e) => e.extras && e.extras.entryKind))],
      zipFinalizeMs: zipFinalize ? zipFinalize.durationMs : null,
      zipValidationMs: zipValidation ? zipValidation.durationMs : null,
      fixtureIdComplete: !smokeEvents.some((e) => e.photoId && !e.fixtureId),
    },
    smokeStatus.benchmarkRunId,
  );
  fs.writeFileSync(path.join(outRoot, 'smoke-comparison.md'), comparison);

  if (smokeStatus.status !== 'COMPLETED' || !instr.ok) {
    const failBody = [
      'SMOKE_FAILED_INSTRUMENTATION_INVALID',
      JSON.stringify(smokeStatus, null, 2),
      JSON.stringify(instr, null, 2),
    ].join('\n');
    fs.writeFileSync(path.join(outRoot, 'benchmark-errors.txt'), failBody + '\n');
    fs.writeFileSync(
      path.join(outRoot, 'benchmark-report.md'),
      `# Benchmark\n\nStatus: SMOKE_FAILED_INSTRUMENTATION_INVALID\n\n\`\`\`json\n${JSON.stringify(instr, null, 2)}\n\`\`\`\n\n${comparison}\n`,
    );
    console.error('SMOKE_FAILED_INSTRUMENTATION_INVALID', instr.failures);
    process.exit(4);
  }

  fs.writeFileSync(path.join(outRoot, 'benchmark-errors.txt'), '');
  fs.writeFileSync(
    path.join(outRoot, 'benchmark-report.md'),
    `# Benchmark\n\nStatus: SMOKE_PASSED_INSTRUMENTATION_VALIDATED\n\nPROFILE RESOLUTION EVIDENCE\n\n\`\`\`json\n${JSON.stringify(configDoc, null, 2)}\n\`\`\`\n\n## Instrumentation\n\n\`\`\`json\n${JSON.stringify(instr.summary, null, 2)}\n\`\`\`\n\n${comparison}\n\nDecision: do not run 5×50 until explicitly requested after this gate.\n`,
  );

  if (args.photos > 3 || args.runs > 1) {
    if (!args.confirmFullRun) {
      console.log('SMOKE_PASSED_INSTRUMENTATION_VALIDATED');
      console.log('FULL_RUN_NOT_REQUESTED (pass --confirm-full-run for 5×50)');
      process.exit(0);
    }
  } else {
    console.log('SMOKE_PASSED_INSTRUMENTATION_VALIDATED');
    process.exit(0);
  }

  // Full run
  const fullFixtures = selectFixtures(allRows, 50);
  console.log('FULL RUN');
  console.log({
    device,
    client: AUTHORIZED_CLIENT,
    supplier: AUTHORIZED_SUPPLIER,
    resolvedClientSupplierId: preflight.resolvedClientSupplierId,
    profile: preflight.resolvedProfileName,
    item: preflight.itemProfileVersion,
    position: preflight.positionProfileVersion,
    photos: 50,
    runs: args.runs,
  });

  const runDurations = [];
  const csvRows = ['run,coldWarm,status,durationMs,terminalCount,pendingJobs,errorCode'];
  for (let i = 0; i < args.runs; i += 1) {
    const coldWarm = i === 0 ? 'cold' : 'warm';
    const t0 = Date.now();
    const st = await runOne({
      device,
      inputDir,
      fixtures: fullFixtures,
      coldWarm,
      timeoutMs: args.timeoutMs,
      outRoot,
      runLabel: `run${i + 1}`,
    });
    const dur = Date.now() - t0;
    runDurations.push(dur);
    csvRows.push(
      `${i + 1},${coldWarm},${st.status},${dur},${st.terminalCount},${st.pendingJobs},${st.errorCode || ''}`,
    );
    if (st.status !== 'COMPLETED') {
      fs.writeFileSync(path.join(outRoot, 'benchmark-runs.csv'), csvRows.join('\n'));
      die('FULL_RUN_FAILED', `run ${i + 1} status=${st.status}`);
    }
    if (i < args.runs - 1) sleep(args.cooldownMs);
  }
  fs.writeFileSync(path.join(outRoot, 'benchmark-runs.csv'), csvRows.join('\n'));
  const summary = {
    min: Math.min(...runDurations),
    max: Math.max(...runDurations),
    median: median(runDurations),
    note: 'Do not treat 5 totals as p95; per-photo percentiles live in events jsonl',
  };
  fs.writeFileSync(
    path.join(outRoot, 'benchmark-report.md'),
    `# Benchmark\n\nStatus: BENCHMARK_COMPLETED\n\n## Durations (ms)\n\n${JSON.stringify(summary, null, 2)}\n\n## PROFILE RESOLUTION EVIDENCE\n\n\`\`\`json\n${JSON.stringify(configDoc, null, 2)}\n\`\`\`\n\nNo performance improvement is claimed in this phase.\n`,
  );
  console.log('BENCHMARK_COMPLETED', summary);
}

async function runOne({ device, inputDir, fixtures, coldWarm, timeoutMs, outRoot, runLabel }) {
  const runId = crypto.randomUUID();
  const relFixtures = `benchmark/${runId}/fixtures`;
  runAs(
    device,
    `mkdir -p "files/${relFixtures}" "files/benchmark/${runId}" "files/benchmark/inbox"`,
  );

  const fixtureRefs = [];
  for (const fx of fixtures) {
    const local = path.join(inputDir, fx.filename);
    const remoteRel = `${relFixtures}/${fx.filename}`;
    pushViaTmp(device, local, remoteRel);
    fixtureRefs.push({
      sequence: fx.sequence,
      fixtureId: fx.filename.replace(/\.jpg$/i, ''),
      filename: fx.filename,
      type: fx.type,
      sizeBytes: fx.sizeBytes,
      width: fx.width,
      height: fx.height,
      fileUri: `file:///data/user/0/${PACKAGE}/files/${remoteRel}`,
    });
  }

  const command = {
    enabled: true,
    benchmarkRunId: runId,
    mode: 'synthetic-inject',
    clientId: AUTHORIZED_CLIENT,
    supplierId: AUTHORIZED_SUPPLIER,
    photos: fixtures.length,
    coldWarm,
    fixtures: fixtureRefs,
    skipUpload: true,
    timeoutMs,
  };
  const cmdLocal = path.join(outRoot, `${runLabel}-command.json`);
  fs.writeFileSync(cmdLocal, JSON.stringify(command, null, 2));
  pushViaTmp(device, cmdLocal, `benchmark/inbox/command.json`);

  console.log(`Run ${runLabel} id=${runId} photos=${fixtures.length} waiting…`);
  const status = pollStatus(device, runId, timeoutMs);
  fs.writeFileSync(
    path.join(outRoot, `${runLabel}-status.json`),
    JSON.stringify(status, null, 2),
  );

  try {
    pullViaTmp(
      device,
      `benchmark/${runId}/events.jsonl`,
      path.join(outRoot, `${runLabel}-events.jsonl`),
    );
  } catch {
    // optional
  }

  // Append to aggregate events
  const agg = path.join(outRoot, 'benchmark-events.jsonl');
  if (fs.existsSync(path.join(outRoot, `${runLabel}-events.jsonl`))) {
    fs.appendFileSync(agg, fs.readFileSync(path.join(outRoot, `${runLabel}-events.jsonl`)));
  }

  return status;
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
