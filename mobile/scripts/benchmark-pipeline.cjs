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
const {
  BENCHMARK_FIXTURE_ORDER_DEFAULT_VERSION,
  BENCHMARK_FIXTURE_ORDER_DEFAULT_SEED,
  buildInterleavedFixtureOrderV2,
} = require('./lib/andesFixtureOrder.cjs');

/** New benches default to andes_interleaved_v2. */
const BENCHMARK_FIXTURE_ORDER_VERSION = BENCHMARK_FIXTURE_ORDER_DEFAULT_VERSION;
const BENCHMARK_FIXTURE_ORDER_SEED = BENCHMARK_FIXTURE_ORDER_DEFAULT_SEED;
const {
  summarizeDualCorrectness,
  evaluateAbsoluteCorrectnessGate,
  evaluateDualRegressionGate,
  dualCorrectnessToCsv,
  extractDualRowsFromEvents,
  extractDualRowsFromStatus,
  buildSequenceBandsCsv,
} = require('./lib/andesDualCorrectness.cjs');

/** Phase 4 A/B: ExportPrep workers stay at 1; only scannerConcurrency varies. */
const PHASE4_EXPORT_PREP_MAX_WORKERS = 2;
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
    scannerConcurrency: 1,
    interleave: true,
    compareCorrectness: null,
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
    else if (a === '--scanner-concurrency') {
      const n = Number(next());
      if (n !== 1 && n !== 2) die('ARGS', '--scanner-concurrency must be 1 or 2');
      out.scannerConcurrency = n;
    } else if (a === '--compare-correctness') {
      out.compareCorrectness = next();
    } else if (a === '--no-interleave') out.interleave = false;
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
  const header = lines[0].split(',').map((h) => h.trim().toLowerCase());
  const idx = (name) => header.indexOf(name);
  // Legacy Andes 50: sequence,filename,type,sourceTemplate,width,height,sizeBytes,sha256
  // Andes 300: sequence,filename,scenario,category,width,height,size_bytes,sha256,...
  const hasCategory = idx('category') >= 0;
  const colFilename = idx('filename') >= 0 ? idx('filename') : 1;
  const colType = hasCategory ? idx('category') : idx('type') >= 0 ? idx('type') : 2;
  const colTemplate = hasCategory
    ? idx('scenario') >= 0
      ? idx('scenario')
      : 2
    : idx('sourcetemplate') >= 0
      ? idx('sourcetemplate')
      : 3;
  const colWidth = idx('width') >= 0 ? idx('width') : 4;
  const colHeight = idx('height') >= 0 ? idx('height') : 5;
  const colSize =
    idx('size_bytes') >= 0 ? idx('size_bytes') : idx('sizebytes') >= 0 ? idx('sizebytes') : 6;
  const colSha = idx('sha256') >= 0 ? idx('sha256') : 7;
  const colScenario = idx('scenario') >= 0 ? idx('scenario') : -1;
  const colValid = idx('valid_andes_count') >= 0 ? idx('valid_andes_count') : -1;
  const colFalse = idx('false_label_count') >= 0 ? idx('false_label_count') : -1;
  const colLabels = idx('label_count') >= 0 ? idx('label_count') : -1;
  const colLabelsJson = idx('labels_json') >= 0 ? idx('labels_json') : -1;
  const colDecoded = idx('decoded_payloads') >= 0 ? idx('decoded_payloads') : -1;

  const rows = [];
  const seen = new Set();
  for (let i = 1; i < lines.length; i += 1) {
    // CSV may contain quoted JSON with commas — use a minimal split that keeps trailing fields joined when needed.
    const cols = splitCsvLine(lines[i]);
    if (cols.length < 8) die('MANIFEST', `bad row ${i}`);
    const filename = cols[colFilename].trim();
    if (seen.has(filename)) die('MANIFEST', `duplicate filename ${filename}`);
    seen.add(filename);
    const typeRaw = cols[colType].trim().toLowerCase();
    const type =
      typeRaw === 'position' || typeRaw === 'item'
        ? typeRaw
        : typeRaw.includes('position')
          ? 'position'
          : typeRaw.includes('item')
            ? 'item'
            : typeRaw;
    rows.push({
      sequence: Number(cols[0]),
      filename,
      type,
      sourceTemplate: cols[colTemplate].trim(),
      width: Number(cols[colWidth]),
      height: Number(cols[colHeight]),
      sizeBytes: Number(cols[colSize]),
      sha256: cols[colSha].trim().toLowerCase(),
      scenario: colScenario >= 0 ? cols[colScenario].trim() : null,
      category: hasCategory ? typeRaw : type,
      labelCount: colLabels >= 0 ? Number(cols[colLabels]) : null,
      validAndesCount: colValid >= 0 ? Number(cols[colValid]) : null,
      falseLabelCount: colFalse >= 0 ? Number(cols[colFalse]) : null,
      labelsJson: colLabelsJson >= 0 ? cols[colLabelsJson] : null,
      decodedPayloads: colDecoded >= 0 ? cols[colDecoded] : null,
    });
  }
  return rows;
}

/** Split a CSV line respecting double-quoted fields (for Andes 300 labels_json). */
function splitCsvLine(line) {
  const out = [];
  let cur = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        cur += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (ch === ',' && !inQuotes) {
      out.push(cur);
      cur = '';
      continue;
    }
    cur += ch;
  }
  out.push(cur);
  return out;
}

function selectFixtures(rows, photos, options = {}) {
  if (photos === 3) {
    const positions = rows.filter((r) => r.type === 'position' || r.category === 'position');
    const items = rows.filter((r) => r.type === 'item' || r.category === 'item');
    if (positions.length < 1 || items.length < 2) die('SMOKE', 'need 1 position + 2 item');
    return [positions[0], items[0], items[1]];
  }
  if (photos < 1 || photos > rows.length) die('PHOTOS', 'invalid --photos');
  if (options.interleave === false || photos <= 3) {
    return rows.slice(0, photos).map((r, i) => ({
      ...r,
      benchmarkSequence: i + 1,
      originalSequence: r.sequence,
    }));
  }
  // Interleave the FULL manifest first, then take the first N of the ordered
  // stream. Slicing before interleave starves ITEM/MULTI when the raw CSV is
  // category-sorted (POSITION head).
  const enriched = rows.map((r) => ({
    ...r,
    scenario: r.scenario || r.sourceTemplate || r.type,
    category: r.category || r.type,
  }));
  const built = buildInterleavedFixtureOrderV2(enriched, {
    seed: options.seed != null ? options.seed : BENCHMARK_FIXTURE_ORDER_SEED,
    version: options.version || BENCHMARK_FIXTURE_ORDER_VERSION,
  });
  return built.ordered.slice(0, photos).map((r, i) => ({
    ...r,
    benchmarkSequence: i + 1,
    // Domain order for device command.sequence must follow benchmarkSequence.
    sequence: i + 1,
    type: r.type || (r.scenarioKind === 'position' ? 'position' : 'item'),
  }));
}

function sha256File(filePath) {
  const hash = crypto.createHash('sha256');
  hash.update(fs.readFileSync(filePath));
  return hash.digest('hex');
}

function adb(device, args, opts = {}) {
  const base = device ? ['-s', device] : [];
  const full = [...base, ...args];
  const maxAttempts = opts.retries != null ? opts.retries : 3;
  const { retries: _retries, ...spawnOpts } = opts;
  let res = null;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    res = spawnSync('adb', full, {
      encoding: 'utf8',
      maxBuffer: 64 * 1024 * 1024,
      ...spawnOpts,
    });
    const enobufs =
      (res.error && (res.error.code === 'ENOBUFS' || /ENOBUFS/i.test(String(res.error.message || '')))) ||
      /ENOBUFS/i.test(String(res.stderr || ''));
    if (enobufs && attempt < maxAttempts) {
      sleep(1500 * attempt);
      continue;
    }
    break;
  }
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

/**
 * Abort C=2 before any labeled run if the installed APK lacks native
 * setBarcodeScanConcurrency. APK is a ZIP — plain `strings` on the APK file
 * misses DEX contents, so we pull the APK and search uncompressed classes*.dex.
 */
function assertNativeScannerConcurrencyCapability(device) {
  const pathOut = adb(device, ['shell', 'pm', 'path', PACKAGE], { allowFail: true });
  if (pathOut.status !== 0 || !pathOut.stdout) {
    die(
      'NATIVE_SCANNER_CONCURRENCY_UNAVAILABLE',
      'cannot resolve APK path for native concurrency preflight',
    );
  }
  const apkLine = String(pathOut.stdout)
    .split('\n')
    .map((l) => l.trim())
    .find((l) => l.startsWith('package:'));
  const apk = apkLine ? apkLine.replace(/^package:/, '').trim() : '';
  if (!apk) {
    die(
      'NATIVE_SCANNER_CONCURRENCY_UNAVAILABLE',
      'empty pm path for package; cannot verify setBarcodeScanConcurrency',
    );
  }
  const tmpRoot = fs.mkdtempSync(path.join(require('os').tmpdir(), 'phase4-apk-preflight-'));
  const localApk = path.join(tmpRoot, 'base.apk');
  try {
    // Prefer the local debug APK when present to avoid large adb pulls (ENOBUFS
    // after heavy 300-photo transfers). Fall back to device pull with retries.
    const localDebugApk = path.resolve(
      __dirname,
      '../android/app/build/outputs/apk/debug/app-debug.apk',
    );
    let apkSource = 'device-pull';
    if (fs.existsSync(localDebugApk)) {
      fs.copyFileSync(localDebugApk, localApk);
      apkSource = 'local-debug-apk';
    } else {
      const pull = adb(device, ['pull', apk, localApk], { allowFail: true, retries: 5 });
      if (pull.status !== 0 || !fs.existsSync(localApk)) {
        die(
          'NATIVE_SCANNER_CONCURRENCY_UNAVAILABLE',
          `adb pull failed for ${apk}: ${(pull.stderr || pull.error && pull.error.message || pull.stdout || '').slice(0, 200)}`,
        );
      }
    }
    void apkSource;
    const { spawnSync: sp } = require('child_process');
    const unzip = sp(
      'unzip',
      ['-l', localApk],
      { encoding: 'utf8' },
    );
    const dexNames = String(unzip.stdout || '')
      .split('\n')
      .map((l) => {
        const m = l.match(/\b(classes\d*\.dex)\b/);
        return m ? m[1] : null;
      })
      .filter(Boolean);
    if (dexNames.length === 0) {
      die('NATIVE_SCANNER_CONCURRENCY_UNAVAILABLE', 'APK has no classes*.dex entries');
    }
    const extract = sp('unzip', ['-qo', localApk, ...dexNames, '-d', tmpRoot], {
      encoding: 'utf8',
    });
    if (extract.status !== 0) {
      die(
        'NATIVE_SCANNER_CONCURRENCY_UNAVAILABLE',
        `unzip dex failed: ${(extract.stderr || '').slice(0, 200)}`,
      );
    }
    const needles = [
      Buffer.from('setBarcodeScanConcurrency'),
      Buffer.from('getBarcodeScanConcurrencyStats'),
    ];
    let foundSet = false;
    let foundStats = false;
    for (const name of dexNames) {
      const dexPath = path.join(tmpRoot, name);
      if (!fs.existsSync(dexPath)) continue;
      const data = fs.readFileSync(dexPath);
      if (data.includes(needles[0])) foundSet = true;
      if (data.includes(needles[1])) foundStats = true;
    }
    if (!foundSet || !foundStats) {
      die(
        'NATIVE_SCANNER_CONCURRENCY_UNAVAILABLE',
        `APK DEX missing native API (set=${foundSet} stats=${foundStats}) — rebuild native module before C=2`,
      );
    }
    console.log('NATIVE_CONCURRENCY_PREFLIGHT_OK', {
      set: foundSet,
      stats: foundStats,
      dex: dexNames.length,
      source: apkSource,
    });
  } finally {
    try {
      fs.rmSync(tmpRoot, { recursive: true, force: true });
    } catch {
      // ignore cleanup
    }
  }
}

function writeDualCorrectnessArtifacts(outRoot, label, status, events, options = {}) {
  let rows = extractDualRowsFromStatus(status);
  if (!rows.length) {
    rows = extractDualRowsFromEvents(events);
  }
  if (!rows.length) {
    if (options.optional) {
      console.warn(
        `WARN[${label}]: dual correctness rows missing (device build may predate Phase4 runner)`,
      );
      return {
        rows: [],
        summary: null,
        absoluteGate: { pass: true, failures: ['dual_rows_missing_optional'] },
      };
    }
    die(
      'DUAL_CORRECTNESS_MISSING',
      `${label}: no dual_correctness_row events and no status.extras.dualCorrectnessRows`,
    );
  }
  const summary =
    (status && status.extras && status.extras.dualCorrectnessSummary) ||
    summarizeDualCorrectness(rows);
  fs.writeFileSync(path.join(outRoot, `${label}-dual-correctness.csv`), dualCorrectnessToCsv(rows));
  fs.writeFileSync(
    path.join(outRoot, `${label}-dual-correctness-summary.json`),
    JSON.stringify(summary, null, 2),
  );
  const absoluteGate = evaluateAbsoluteCorrectnessGate(summary);
  fs.writeFileSync(
    path.join(outRoot, `${label}-correctness-absolute-gate.json`),
    JSON.stringify(absoluteGate, null, 2),
  );
  return { rows, summary, absoluteGate };
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
    // Integrity correction: strong validation always native-rehashes (no reused_persisted).
    const nativeStrong = strongHashes.filter(
      (e) =>
        e.extras?.hashMode === 'native_file' ||
        e.extras?.hashImplementation === 'native_stream',
    );
    if (nativeStrong.length !== status.expectedCount) {
      failures.push(`strong_native_file=${nativeStrong.length}/${status.expectedCount}`);
    }
    const reused = strongHashes.filter((e) => e.extras?.hashMode === 'reused_persisted');
    if (reused.length !== 0) {
      failures.push(`strong_reused_persisted_unexpected=${reused.length}`);
    }
    const base64Strong = strongHashes.filter(
      (e) =>
        e.extras?.hashMode === 'js_base64_full_file' ||
        e.extras?.hashImplementation === 'js_base64_full_file',
    );
    if (base64Strong.length !== 0) {
      failures.push(`strong_base64_unexpected=${base64Strong.length}`);
    }
  }

  const draftLookup = events.filter(
    (e) =>
      e.stage === 'draft_lookup' ||
      e.stage === 'draft_lookup_pre_scan' ||
      e.stage === 'draft_lookup_post_scan',
  );
  if (!draftLookup.length) failures.push('draft_lookup_missing');
  else if (draftLookup.some((e) => !(e.extras && e.extras.lookupMode))) {
    failures.push('draft_lookup_metrics_incomplete');
  } else {
    const badMode = draftLookup.filter(
      (e) => e.extras && e.extras.lookupMode !== 'direct_indexed_lookup',
    );
    if (badMode.length) {
      failures.push(`draft_lookup_mode_unexpected=${badMode.length}`);
    }
    const badFull = draftLookup.filter(
      (e) => e.extras && Number(e.extras.fullSessionRowsLoaded) > 0,
    );
    if (badFull.length) {
      failures.push(`draft_lookup_full_session_loaded=${badFull.length}`);
    }
    const badQuery = draftLookup.filter((e) => e.extras && Number(e.extras.queryCount) !== 1);
    if (badQuery.length) {
      failures.push(`draft_lookup_query_count_unexpected=${badQuery.length}`);
    }
    const aliased = events.filter((e) => e.stage === 'draft_lookup');
    const pre = events.filter((e) => e.stage === 'draft_lookup_pre_scan');
    const post = events.filter((e) => e.stage === 'draft_lookup_post_scan');
    if (status.expectedCount >= 3) {
      if (!pre.length) failures.push('draft_lookup_pre_scan_missing');
      if (!post.length) failures.push('draft_lookup_post_scan_missing');
      const badPurpose = aliased.filter(
        (e) =>
          e.extras &&
          e.extras.lookupPurpose !== 'skip_scan_check' &&
          e.extras.lookupPurpose !== 'export_ready_check',
      );
      if (badPurpose.length) {
        failures.push(`draft_lookup_purpose_unexpected=${badPurpose.length}`);
      }
      // Alias events should equal pre+post (each lookup emits purpose stage + draft_lookup).
      if (aliased.length !== pre.length + post.length) {
        failures.push(
          `draft_lookup_alias_count_mismatch=alias:${aliased.length},pre:${pre.length},post:${post.length}`,
        );
      }
    }
  }

  // Phase 3A — export_resolution substages (staging path; soft-skip when only legacy stages).
  const exportResolution = events.filter((e) => e.stage === 'export_resolution');
  const stagingValidation = events.filter((e) => e.stage === 'export_resolution_staging_validation');
  const hashValidation = events.filter((e) => e.stage === 'export_resolution_hash_validation');
  const HASH_NEST_TOLERANCE_MS = 50;
  if (stagingValidation.length || hashValidation.length || exportResolution.length) {
    const requireOnce = (stage) => {
      const rows = events.filter((e) => e.stage === stage);
      if (!rows.length) failures.push(`${stage}_missing`);
      else if (rows.length > 1) failures.push(`${stage}_duplicated=${rows.length}`);
      else if (!(Number(rows[0].durationMs) >= 0)) failures.push(`${stage}_duration_negative`);
      return rows[0] || null;
    };
    requireOnce('export_resolution');
    requireOnce('export_resolution_queries');
    requireOnce('export_resolution_freeze_checks');
    requireOnce('export_resolution_profile');
    if (stagingValidation.length) {
      requireOnce('export_resolution_ensure_jobs');
      requireOnce('export_resolution_staging_validation');
      requireOnce('export_resolution_hash_validation');
      requireOnce('export_resolution_scan_catchup');
      const entryOrOther =
        events.filter((e) => e.stage === 'export_resolution_entry_build').length ||
        events.filter((e) => e.stage === 'export_resolution_other').length;
      if (!entryOrOther) failures.push('export_resolution_entry_or_other_missing');

      const staging = stagingValidation[0];
      const hash = hashValidation[0];
      if (staging && hash) {
        const sDur = Number(staging.durationMs) || 0;
        const hDur = Number(hash.durationMs) || 0;
        if (hDur > sDur + HASH_NEST_TOLERANCE_MS) {
          failures.push(`hash_validation_exceeds_staging=${hDur}>${sDur}`);
        }
      }
      const agg = exportResolution[0];
      if (agg && agg.extras && agg.extras.reconciliationValid === false) {
        failures.push('export_resolution_reconciliation_invalid');
      }
      if (agg && Number(agg.extras?.queryCount) === -1) {
        failures.push('export_resolution_fictitious_queryCount_-1');
      }
      const ensure = events.find((e) => e.stage === 'export_resolution_ensure_jobs');
      if (ensure && Number(ensure.extras?.queryCount) === -1) {
        failures.push('ensure_jobs_fictitious_queryCount_-1');
      }
    }
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
  if (args.scannerConcurrency === 2) {
    assertNativeScannerConcurrencyCapability(device);
  }
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
  const smokeFixtureBytes = selectFixtures(allRows, 3, { interleave: false }).reduce(
    (a, r) => a + r.sizeBytes,
    0,
  );
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
    exportPrepMaxWorkers: PHASE4_EXPORT_PREP_MAX_WORKERS,
    scannerConcurrency: args.scannerConcurrency,
    fixtureOrderVersion: BENCHMARK_FIXTURE_ORDER_VERSION,
    fixtureOrderSeed: BENCHMARK_FIXTURE_ORDER_SEED,
    deviceManufacturer: manufacturer,
    deviceModel: model,
    androidRelease: release,
    androidSdk: sdk ? Number(sdk) : null,
    package: PACKAGE,
    device,
    gitSha,
    dirty,
    uploadHttpEnabled: false,
    concurrency: {
      exportPrepMaxWorkers: PHASE4_EXPORT_PREP_MAX_WORKERS,
      scannerConcurrency: args.scannerConcurrency,
      note: 'Phase4 A/B: workers fixed at 2 (feed); scannerConcurrency is the measured variable',
    },
    profile: configDoc,
    baselineNote: 'baseline del working tree exacto utilizado',
  };
  fs.writeFileSync(path.join(outRoot, 'benchmark-environment.json'), JSON.stringify(envDoc, null, 2));

  // --- Smoke ---
  const smokeFixtures = selectFixtures(allRows, 3, { interleave: false });
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
    scannerConcurrency: args.scannerConcurrency,
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

  // Dual correctness from real device rows (never INCONCLUSIVE placeholders).
  const smokeDual = writeDualCorrectnessArtifacts(outRoot, 'smoke', smokeStatus, smokeEvents, {
    optional: true,
  });

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

  // Full run — use requested --photos (50 default for short suite; 300 for scale).
  const fullPhotoCount = args.photos > 3 ? args.photos : 50;
  const fullFixtures = selectFixtures(allRows, fullPhotoCount, {
    interleave: args.interleave && fullPhotoCount >= 50,
  });
  fs.writeFileSync(
    path.join(outRoot, 'fixture-order.json'),
    JSON.stringify(
      {
        version: BENCHMARK_FIXTURE_ORDER_VERSION,
        seed: BENCHMARK_FIXTURE_ORDER_SEED,
        exportPrepMaxWorkers: PHASE4_EXPORT_PREP_MAX_WORKERS,
        scannerConcurrency: args.scannerConcurrency,
        photos: fullFixtures.length,
        order: fullFixtures.map((f) => ({
          benchmarkSequence: f.benchmarkSequence || f.sequence,
          originalSequence: f.originalSequence || f.sequence,
          filename: f.filename,
          scenario: f.scenario || f.sourceTemplate,
          scenarioKind: f.scenarioKind || null,
        })),
      },
      null,
      2,
    ),
  );
  fs.writeFileSync(
    path.join(outRoot, 'fixture-sequence-bands.csv'),
    buildSequenceBandsCsv(fullFixtures, 50),
  );
  console.log('FULL RUN');
  console.log({
    device,
    client: AUTHORIZED_CLIENT,
    supplier: AUTHORIZED_SUPPLIER,
    resolvedClientSupplierId: preflight.resolvedClientSupplierId,
    profile: preflight.resolvedProfileName,
    item: preflight.itemProfileVersion,
    position: preflight.positionProfileVersion,
    photos: fullFixtures.length,
    runs: args.runs,
    scannerConcurrency: args.scannerConcurrency,
    exportPrepMaxWorkers: PHASE4_EXPORT_PREP_MAX_WORKERS,
    fixtureOrderVersion: BENCHMARK_FIXTURE_ORDER_VERSION,
  });

  const runDurations = [];
  const csvRows = [
    'run,coldWarm,status,durationMs,terminalCount,pendingJobs,errorCode,scannerConcurrency,exportPrepMaxWorkers',
  ];
  let lastDualSummary = smokeDual.summary;
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
      scannerConcurrency: args.scannerConcurrency,
    });
    const dur = Date.now() - t0;
    runDurations.push(dur);
    csvRows.push(
      `${i + 1},${coldWarm},${st.status},${dur},${st.terminalCount},${st.pendingJobs},${st.errorCode || ''},${args.scannerConcurrency},${PHASE4_EXPORT_PREP_MAX_WORKERS}`,
    );
    const eventsPath = path.join(outRoot, `run${i + 1}-events.jsonl`);
    const events = fs.existsSync(eventsPath) ? readJsonl(eventsPath) : [];
    const dual = writeDualCorrectnessArtifacts(outRoot, `run${i + 1}`, st, events);
    lastDualSummary = dual.summary;
    if (!dual.absoluteGate.pass && fullPhotoCount >= 50) {
      fs.writeFileSync(
        path.join(outRoot, `run${i + 1}-CORRECTNESS_ABSOLUTE_GATE_FAILED.txt`),
        dual.absoluteGate.failures.join('\n') + '\n',
      );
      console.warn(
        `WARN: CORRECTNESS_ABSOLUTE_GATE_FAILED run ${i + 1}: ${dual.absoluteGate.failures.join('; ')}`,
      );
      // Do not abort mid A/B — collect all runs; final verdict consumes gate files.
    }
    if (st.status !== 'COMPLETED') {
      fs.writeFileSync(path.join(outRoot, 'benchmark-runs.csv'), csvRows.join('\n'));
      die('FULL_RUN_FAILED', `run ${i + 1} status=${st.status}`);
    }
    if (i < args.runs - 1) sleep(args.cooldownMs);
  }
  fs.writeFileSync(path.join(outRoot, 'benchmark-runs.csv'), csvRows.join('\n'));

  if (args.compareCorrectness) {
    if (!lastDualSummary) {
      die('COMPARE_CORRECTNESS', 'no dual correctness summary from this run to compare');
    }
    const baselinePath = path.resolve(process.cwd(), args.compareCorrectness);
    if (!fs.existsSync(baselinePath)) {
      die('COMPARE_CORRECTNESS', `baseline not found: ${baselinePath}`);
    }
    const baseline = JSON.parse(fs.readFileSync(baselinePath, 'utf8'));
    const regression = evaluateDualRegressionGate(baseline, lastDualSummary);
    fs.writeFileSync(
      path.join(outRoot, 'correctness-regression-gate.json'),
      JSON.stringify(regression, null, 2),
    );
    if (!regression.pass) {
      die('CORRECTNESS_REGRESSION_GATE_FAILED', regression.failures.join('; '));
    }
  }

  const summary = {
    min: Math.min(...runDurations),
    max: Math.max(...runDurations),
    median: median(runDurations),
    exportPrepMaxWorkers: PHASE4_EXPORT_PREP_MAX_WORKERS,
    scannerConcurrency: args.scannerConcurrency,
    dualCorrectness: lastDualSummary,
    note: 'Do not treat 5 totals as p95; per-photo percentiles live in events jsonl',
  };
  fs.writeFileSync(
    path.join(outRoot, 'benchmark-report.md'),
    `# Benchmark\n\nStatus: BENCHMARK_COMPLETED\n\n## Durations (ms)\n\n${JSON.stringify(summary, null, 2)}\n\n## PROFILE RESOLUTION EVIDENCE\n\n\`\`\`json\n${JSON.stringify(configDoc, null, 2)}\n\`\`\`\n\nNo performance improvement is claimed in this phase.\n`,
  );
  console.log('BENCHMARK_COMPLETED', summary);
}

async function runOne({
  device,
  inputDir,
  fixtures,
  coldWarm,
  timeoutMs,
  outRoot,
  runLabel,
  scannerConcurrency = 1,
}) {
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
      sequence: fx.benchmarkSequence || fx.sequence,
      fixtureId: fx.filename.replace(/\.jpg$/i, ''),
      filename: fx.filename,
      type: fx.type,
      sizeBytes: fx.sizeBytes,
      width: fx.width,
      height: fx.height,
      fileUri: `file:///data/user/0/${PACKAGE}/files/${remoteRel}`,
      originalSequence: fx.originalSequence || fx.sequence,
      scenarioKind: fx.scenarioKind || null,
      labelsJson: fx.labelsJson || null,
      scenario: fx.scenario || fx.sourceTemplate || null,
      category: fx.category || fx.type || null,
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
    scannerConcurrency: scannerConcurrency === 2 ? 2 : 1,
    // exportPrepMaxWorkers is fixed at 2 on device (feed capacity); only scannerConcurrency varies.
    fixtureOrderVersion: BENCHMARK_FIXTURE_ORDER_VERSION,
    fixtureOrderSeed: BENCHMARK_FIXTURE_ORDER_SEED,
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
