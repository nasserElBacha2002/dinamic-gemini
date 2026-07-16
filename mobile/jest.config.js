/**
 * Full test config for the React Native app (device/integration suites).
 * Requires the Expo dev toolchain to be installed. In CI without the RN toolchain,
 * run the pure-core suite instead: `npm run test:core`.
 */
module.exports = {
  preset: 'jest-expo',
  transformIgnorePatterns: [
    'node_modules/(?!((jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@unimodules/.*|unimodules|sentry-expo|native-base|react-native-svg))',
  ],
  moduleNameMapper: {
    '^@core/(.*)$': '<rootDir>/src/core/$1',
    '^@domain/(.*)$': '<rootDir>/src/domain/$1',
    '^@native/(.*)$': '<rootDir>/src/native/$1',
    '^@shared/(.*)$': '<rootDir>/src/shared/$1',
  },
};
