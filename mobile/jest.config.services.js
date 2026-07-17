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
    '<rootDir>/tests/inventoryService.test.ts',
    '<rootDir>/tests/aisleService.test.ts',
    '<rootDir>/tests/processingService.test.ts',
    '<rootDir>/tests/operationalFlow.test.ts',
    '<rootDir>/tests/aisleCreationRules.test.ts',
  ],
  transform: {
    '^.+\\.ts$': ['ts-jest', { tsconfig: 'tsconfig.json' }],
  },
};

