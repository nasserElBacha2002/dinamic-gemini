const { getDefaultConfig } = require('expo/metro-config');
const exclusionList = require('metro-config/src/defaults/exclusionList');
const path = require('path');

/** @type {import('expo/metro-config').MetroConfig} */
const config = getDefaultConfig(__dirname);

// Keep file watching scoped to this app. Watching the monorepo root (backend,
// frontend, htmlcov, venv, …) triggers EMFILE when Watchman is unavailable and
// Metro falls back to Node FSEvents (macOS soft limit is often ~256).
config.projectRoot = __dirname;
config.watchFolders = [__dirname];
config.resolver.nodeModulesPaths = [path.resolve(__dirname, 'node_modules')];
// Keep hierarchical lookup enabled: React Native 0.74 installs some internal
// packages (for example @react-native/virtualized-lists) under
// node_modules/react-native/node_modules.
config.resolver.blockList = exclusionList([
  /\/android\/build\/.*/,
  /\/android\/\.gradle\/.*/,
  /\/android\/app\/build\/.*/,
  /\/\.expo\/.*/,
  /\/coverage\/.*/,
  /\/\.git\/.*/,
]);

// Prefer Watchman; avoid crawling parent workspace roots Expo may detect.
config.watcher = {
  ...(config.watcher ?? {}),
  additionalExts: config.watcher?.additionalExts,
  healthCheck: {
    enabled: true,
    interval: 30000,
    timeout: 5000,
  },
};

module.exports = config;
