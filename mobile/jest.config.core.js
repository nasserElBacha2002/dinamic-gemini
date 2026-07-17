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
    '<rootDir>/tests/fase2UploadCore.test.ts',
    '<rootDir>/tests/fase3HardeningCore.test.ts',
    '<rootDir>/tests/featureFlags.test.ts',
    '<rootDir>/tests/fase3CorrectionsCore.test.ts',
    '<rootDir>/tests/processingState.test.ts',
    '<rootDir>/tests/processingReadiness.test.ts',
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
