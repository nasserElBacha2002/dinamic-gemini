module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  rootDir: '.',
  testMatch: [
    '<rootDir>/tests/apiClient.test.ts',
    '<rootDir>/tests/resolveAppConfig.test.ts',
    '<rootDir>/tests/authService.test.ts',
    '<rootDir>/tests/captureService.test.ts',
    '<rootDir>/tests/selectionRules.test.ts',
  ],
  transform: {
    '^.+\\.ts$': ['ts-jest', { tsconfig: 'tsconfig.json' }],
  },
};

