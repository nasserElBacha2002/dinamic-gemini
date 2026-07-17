#!/usr/bin/env node
/**
 * Android-first expo-doctor wrapper for Dinamic Captura.
 *
 * Expo SDK 51 requires Xcode ≤16.2. Local machines may only have Xcode 26.x.
 * This project has no iOS target (no ios/ directory, Android-only config/module),
 * so the native Xcode tooling check is irrelevant to Android builds.
 *
 * We still fail hard on any other expo-doctor finding (deps, setup, etc.).
 * Do not use this to paper over real Android/toolchain issues.
 *
 * Intentional Expo upgrades (to SDK 55+ for Xcode 26) remain a separate, planned task.
 */
const { spawnSync } = require('node:child_process');
const { existsSync } = require('node:fs');
const { join } = require('node:path');

const projectRoot = process.cwd();
const hasIosNativeProject = existsSync(join(projectRoot, 'ios'));

const result = spawnSync('npx', ['expo-doctor@1.20.1'], {
  cwd: projectRoot,
  encoding: 'utf8',
  env: process.env,
  shell: process.platform === 'win32',
});

const stdout = result.stdout ?? '';
const stderr = result.stderr ?? '';
process.stdout.write(stdout);
process.stderr.write(stderr);

const combined = `${stdout}\n${stderr}`;
const exitCode = result.status ?? 1;

if (exitCode === 0) {
  process.exit(0);
}

const failedCountMatch = combined.match(/(\d+)\s+check(?:s)? failed/i);
const failedCount = failedCountMatch ? Number(failedCountMatch[1]) : null;
const mentionsXcodeTooling =
  /Check native tooling versions/i.test(combined) && /Xcode/i.test(combined);
const mentionsOtherCritical =
  /Found outdated dependencies/i.test(combined) ||
  /packages should be updated/i.test(combined) ||
  /Check that packages match versions/i.test(combined);

const canIgnoreXcodeOnly =
  !hasIosNativeProject &&
  failedCount === 1 &&
  mentionsXcodeTooling &&
  !mentionsOtherCritical;

if (canIgnoreXcodeOnly) {
  console.log('');
  console.log(
    '[doctor] Android-only project: ignoring the Xcode ↔ Expo SDK compatibility check.'
  );
  console.log(
    '[doctor] This app builds with Android/Gradle only. Keeping Expo SDK 51 is intentional;'
  );
  console.log(
    '[doctor] upgrading to SDK 55+ (for Xcode 26) is a separate planned migration.'
  );
  process.exit(0);
}

if (hasIosNativeProject && mentionsXcodeTooling) {
  console.log('');
  console.log(
    '[doctor] ios/ is present — Xcode must match the Expo SDK. Install Xcode ≤16.2 for SDK 51,'
  );
  console.log('[doctor] or upgrade the Expo SDK before relying on Xcode 26.');
}

process.exit(exitCode);
