import { resolveFeatureFlags, type FeatureFlags } from '../../core/featureFlags';

export type AppEnvironment = 'development' | 'staging' | 'production';

export interface AppConfig {
  readonly apiBaseUrl: string;
  readonly apiKey: string | null;
  readonly environment: AppEnvironment;
  readonly isDevelopment: boolean;
  readonly versionName: string;
  readonly versionCode: number;
  readonly gitSha: string;
  readonly buildTime: string;
  readonly flags: FeatureFlags;
}

/** Raw values injected via app.config.ts `extra` (from mobile/.env at build time). */
export interface RawAppExtra {
  readonly apiBaseUrl?: unknown;
  readonly apiKey?: unknown;
  readonly environment?: unknown;
  readonly versionName?: unknown;
  readonly versionCode?: unknown;
  readonly gitSha?: unknown;
  readonly buildTime?: unknown;
  readonly flags?: unknown;
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function asNumber(value: unknown, fallback: number): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim()) {
    const n = Number(value);
    if (Number.isFinite(n)) {
      return n;
    }
  }
  return fallback;
}

/**
 * Fallback to process.env only for Node/CI (tests). React Native bundles do NOT
 * receive mobile/.env in process.env, so runtime relies on Expo `extra`.
 */
function fromProcessEnv(name: string): string {
  return asString(process.env[name]);
}

function normalizeEnvironment(raw: string): AppEnvironment {
  if (raw === 'staging' || raw === 'production') {
    return raw;
  }
  return 'development';
}

/** Pure resolver: testable without Expo native modules. */
export function resolveAppConfig(extra: RawAppExtra | null | undefined): AppConfig {
  const apiBaseUrl = (asString(extra?.apiBaseUrl) || fromProcessEnv('DINAMIC_API_BASE_URL')).replace(
    /\/+$/,
    '',
  );
  const apiKey = asString(extra?.apiKey) || fromProcessEnv('DINAMIC_API_KEY') || null;
  const environment = normalizeEnvironment(
    asString(extra?.environment) || fromProcessEnv('DINAMIC_ENVIRONMENT'),
  );
  return {
    apiBaseUrl,
    apiKey,
    environment,
    isDevelopment: environment === 'development',
    versionName: asString(extra?.versionName) || fromProcessEnv('DINAMIC_VERSION_NAME') || '0.0.1',
    versionCode: asNumber(extra?.versionCode, asNumber(fromProcessEnv('DINAMIC_VERSION_CODE'), 1)),
    gitSha: asString(extra?.gitSha) || fromProcessEnv('DINAMIC_GIT_SHA') || 'unknown',
    buildTime: asString(extra?.buildTime) || fromProcessEnv('DINAMIC_BUILD_TIME') || '',
    flags: resolveFeatureFlags(extra?.flags, environment),
  };
}

export function validateAppConfig(config: AppConfig): string | null {
  if (!config.apiBaseUrl) {
    return 'Falta configurar DINAMIC_API_BASE_URL.';
  }
  try {
    const parsed = new URL(config.apiBaseUrl);
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      return 'DINAMIC_API_BASE_URL debe usar http o https.';
    }
    if (config.environment === 'production' && parsed.protocol !== 'https:') {
      return 'En producción DINAMIC_API_BASE_URL debe usar HTTPS.';
    }
  } catch {
    return 'DINAMIC_API_BASE_URL no es una URL válida.';
  }
  return null;
}
