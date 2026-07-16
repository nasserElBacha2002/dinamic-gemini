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
  testMatch: ['**/*.test.ts'],
  moduleNameMapper: {
    '^@core/(.*)$': '<rootDir>/src/core/$1',
    '^@domain/(.*)$': '<rootDir>/src/domain/$1',
    '^@shared/(.*)$': '<rootDir>/src/shared/$1',
  },
  transform: {
    '^.+\\.ts$': ['ts-jest', { tsconfig: 'tsconfig.core.json' }],
  },
};
