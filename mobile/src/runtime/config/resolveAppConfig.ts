export type AppEnvironment = 'development' | 'staging' | 'production';

export interface AppConfig {
  readonly apiBaseUrl: string;
  readonly apiKey: string | null;
  readonly environment: AppEnvironment;
  readonly isDevelopment: boolean;
}

/** Raw values injected via app.config.ts `extra` (from mobile/.env at build time). */
export interface RawAppExtra {
  readonly apiBaseUrl?: unknown;
  readonly apiKey?: unknown;
  readonly environment?: unknown;
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
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
  } catch {
    return 'DINAMIC_API_BASE_URL no es una URL válida.';
  }
  return null;
}
