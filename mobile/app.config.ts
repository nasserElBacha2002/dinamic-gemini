import type { ExpoConfig } from 'expo/config';

/**
 * Expo config for the Dinamic Inventory Android capture client (Fase 1).
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
  version: '0.0.1',
  orientation: 'portrait',
  userInterfaceStyle: 'automatic',
  splash: {
    backgroundColor: '#0d1b2a',
  },
  android: {
    package: 'com.dinamic.inventory.capture',
    permissions: [
      // Photos only — Android 13+.
      'android.permission.READ_MEDIA_IMAGES',
      // Android 14+ partial selection (photos subset). No video counterpart requested.
      'android.permission.READ_MEDIA_VISUAL_USER_SELECTED',
      // Foreground service for active capture sessions.
      'android.permission.FOREGROUND_SERVICE',
      'android.permission.FOREGROUND_SERVICE_DATA_SYNC',
      'android.permission.POST_NOTIFICATIONS',
      'android.permission.INTERNET',
      'android.permission.ACCESS_NETWORK_STATE',
    ],
    // Explicitly block legacy broad storage / any video permission from being merged in.
    blockedPermissions: [
      'android.permission.READ_MEDIA_VIDEO',
      'android.permission.WRITE_EXTERNAL_STORAGE',
    ],
  },
  plugins: [
    'expo-secure-store',
    [
      'expo-media-library',
      {
        // Request read-only photo access; never write to the gallery, never audio/video.
        photosPermission: 'La app usa tus fotografías para cargar imágenes del inventario.',
        savePhotosPermission: false,
        isAccessMediaLocationEnabled: false,
      },
    ],
  ],
  extra: {
    // Backend base URL is injected per-environment; see .env.example.
    apiBaseUrl: process.env.DINAMIC_API_BASE_URL ?? '',
    apiKey: process.env.DINAMIC_API_KEY ?? '',
    environment: process.env.DINAMIC_ENVIRONMENT ?? 'development',
  },
};

export default config;
