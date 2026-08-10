/**
 * Fase 0 sandbox validation config: pure-core logic only (no React Native / Expo).
 * The device-dependent adapters (src/native, app) require the Expo dev toolchain and
 * are excluded here. Use `jest.config.js` (react-native preset) for on-device suites.
 */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  rootDir: '.',
  roots: ['<rootDir>/tests', '<rootDir>/src/core'],
  testMatch: [
    '<rootDir>/tests/compositeCursor.test.ts',
    '<rootDir>/tests/imageFilter.test.ts',
    '<rootDir>/tests/stability.test.ts',
    '<rootDir>/tests/photoDetection.test.ts',
    '<rootDir>/tests/incrementalScan.test.ts',
    '<rootDir>/tests/scanCoordinator.test.ts',
    '<rootDir>/tests/detectionStability.integration.test.ts',
    '<rootDir>/tests/logging.test.ts',
    '<rootDir>/tests/captureState.test.ts',
    '<rootDir>/tests/canExportSession.test.ts',
    '<rootDir>/tests/localAisleWork.test.ts',
    '<rootDir>/tests/captureSequence.test.ts',
    '<rootDir>/tests/fase2UploadCore.test.ts',
    '<rootDir>/tests/fase3HardeningCore.test.ts',
    '<rootDir>/tests/featureFlags.test.ts',
    '<rootDir>/tests/observabilityPhase0.test.ts',
    '<rootDir>/tests/uploadPhase1Policies.test.ts',
    '<rootDir>/tests/uploadLeasePhase2.test.ts',
    '<rootDir>/tests/fase3CorrectionsCore.test.ts',
    '<rootDir>/tests/processingState.test.ts',
    '<rootDir>/tests/processingReadiness.test.ts',
    '<rootDir>/tests/labelPayloadContracts.test.ts',
    '<rootDir>/tests/productLabelMultiConsolidator.test.ts',
    '<rootDir>/tests/databaseCorruption.test.ts',
    '<rootDir>/tests/databaseMigrations.test.ts',
    '<rootDir>/tests/localCsvAndReconcilePhase346.test.ts',
    '<rootDir>/tests/processingService.test.ts',
    '<rootDir>/tests/offlineOperationsPhase9.test.ts',
  ],
  moduleNameMapper: {
    '^@core/(.*)$': '<rootDir>/src/core/$1',
    '^@domain/(.*)$': '<rootDir>/src/domain/$1',
    '^@shared/(.*)$': '<rootDir>/src/shared/$1',
  },
  transform: {
    '^.+\\.ts$': ['ts-jest', { tsconfig: 'tsconfig.core.json' }],
  },
};
