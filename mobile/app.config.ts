import type { ExpoConfig } from 'expo/config';
import { execSync } from 'child_process';

function readGitSha(): string {
  if (process.env.DINAMIC_GIT_SHA?.trim()) {
    return process.env.DINAMIC_GIT_SHA.trim();
  }
  try {
    return execSync('git rev-parse --short HEAD', { encoding: 'utf8' }).trim();
  } catch {
    return 'unknown';
  }
}

const versionName = process.env.DINAMIC_VERSION_NAME ?? '0.3.0';
const versionCode = Number(process.env.DINAMIC_VERSION_CODE ?? '30');
const environment = process.env.DINAMIC_ENVIRONMENT ?? 'development';
const allowCleartext = environment === 'development' || environment === 'staging';

/**
 * Expo config for the Dinamic Inventory Android capture client.
 *
 * PHOTOS-ONLY: Android manifest declares only image media permissions. We intentionally
 * do NOT declare READ_MEDIA_VIDEO. On Android 13+ the OS shows a photos-only prompt.
 * On Android 14+ partial photo access (READ_MEDIA_VISUAL_USER_SELECTED) is honored by
 * expo-media-library; the app must degrade gracefully to the user-selected subset.
 */
const config: ExpoConfig = {
  name: 'Dinamic Captura',
  slug: 'dinamic-inventory-mobile',
  scheme: 'dinamiccaptura',
  version: versionName,
  orientation: 'portrait',
  userInterfaceStyle: 'automatic',
  splash: {
    backgroundColor: '#0d1b2a',
  },
  android: {
    package: 'com.dinamic.inventory.capture',
    versionCode: Number.isFinite(versionCode) ? versionCode : 30,
    permissions: [
      'android.permission.READ_MEDIA_IMAGES',
      'android.permission.READ_MEDIA_VISUAL_USER_SELECTED',
      'android.permission.FOREGROUND_SERVICE',
      'android.permission.FOREGROUND_SERVICE_DATA_SYNC',
      'android.permission.POST_NOTIFICATIONS',
      'android.permission.INTERNET',
      'android.permission.ACCESS_NETWORK_STATE',
      'android.permission.RECEIVE_BOOT_COMPLETED',
      'android.permission.WAKE_LOCK',
    ],
    blockedPermissions: [
      'android.permission.READ_MEDIA_VIDEO',
      'android.permission.WRITE_EXTERNAL_STORAGE',
    ],
    ...(allowCleartext ? { usesCleartextTraffic: true } : { usesCleartextTraffic: false }),
  },
  plugins: [
    'expo-secure-store',
    [
      'expo-media-library',
      {
        photosPermission: 'La app usa tus fotografías para cargar imágenes del inventario.',
        savePhotosPermission: false,
        isAccessMediaLocationEnabled: false,
      },
    ],
    [
      'expo-build-properties',
      {
        android: {
          minSdkVersion: 24,
          compileSdkVersion: 34,
          targetSdkVersion: 34,
        },
      },
    ],
  ],
  extra: {
    apiBaseUrl: process.env.DINAMIC_API_BASE_URL ?? '',
    apiKey: process.env.DINAMIC_API_KEY ?? '',
    environment,
    versionName,
    versionCode: Number.isFinite(versionCode) ? versionCode : 30,
    gitSha: readGitSha(),
    buildTime: process.env.DINAMIC_BUILD_TIME ?? new Date().toISOString(),
    flags: {
      allowMobileDataUploads: process.env.DINAMIC_FLAG_MOBILE_DATA !== '0',
      heicConvertToJpeg: process.env.DINAMIC_FLAG_HEIC_JPEG !== '0',
      workManagerScheduling: process.env.DINAMIC_FLAG_WORK_MANAGER === '1',
      advancedReconciliation: process.env.DINAMIC_FLAG_RECONCILE !== '0',
      backgroundJobPolling: process.env.DINAMIC_FLAG_BG_POLL !== '0',
      aisleDeviceLock: process.env.DINAMIC_FLAG_AISLE_LOCK === '1',
      uploadObservabilityEnabled: process.env.DINAMIC_FLAG_UPLOAD_OBS !== '0',
      uploadDimensionCap: process.env.DINAMIC_FLAG_UPLOAD_DIM_CAP !== '0',
      uploadAdaptiveQuality: process.env.DINAMIC_FLAG_UPLOAD_ADAPTIVE_QUALITY !== '0',
      uploadAdaptiveConcurrency: process.env.DINAMIC_FLAG_UPLOAD_ADAPTIVE_CONCURRENCY !== '0',
      uploadAbortEnabled: process.env.DINAMIC_FLAG_UPLOAD_ABORT !== '0',
    },
  },
};

export default config;
