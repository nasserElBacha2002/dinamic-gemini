import type { AppConfig } from '../../runtime/config/resolveAppConfig';
import type { Logger } from '../../core/logging';
import type { ApiClient } from '../../services/api/apiClient';
import type { TokenStorage } from '../../services/secureStorage/tokenStorage';
import type { ConnectivityService } from '../../services/connectivity/connectivity';
import { getStorageStatus } from './storageCleanup';

export type HealthStatus = 'ok' | 'warn' | 'fail';

export interface HealthCheckResult {
  readonly id: string;
  readonly label: string;
  readonly status: HealthStatus;
  readonly detail: string;
}

export async function runHealthChecks(input: {
  readonly config: AppConfig;
  readonly api: ApiClient;
  readonly tokenStorage: TokenStorage;
  readonly connectivity: ConnectivityService;
  readonly logger?: Logger;
  readonly probeSqlite: () => Promise<void>;
  readonly probeMediaStore?: () => Promise<void>;
}): Promise<readonly HealthCheckResult[]> {
  const results: HealthCheckResult[] = [];

  results.push({
    id: 'config',
    label: 'Configuración',
    status: input.config.apiBaseUrl ? 'ok' : 'fail',
    detail: `${input.config.environment} · v${input.config.versionName} (${input.config.versionCode}) · ${input.config.gitSha}`,
  });

  const conn = input.connectivity.getState();
  results.push({
    id: 'connectivity',
    label: 'Conectividad',
    status: conn === 'online' ? 'ok' : conn === 'offline' ? 'warn' : 'warn',
    detail: conn,
  });

  try {
    const url = new URL(input.config.apiBaseUrl);
    const secure =
      input.config.environment !== 'production' || url.protocol === 'https:';
    results.push({
      id: 'https',
      label: 'HTTPS / base URL',
      status: secure ? 'ok' : 'fail',
      detail: url.origin,
    });
  } catch {
    results.push({
      id: 'https',
      label: 'HTTPS / base URL',
      status: 'fail',
      detail: 'URL inválida',
    });
  }

  try {
    await input.api.get('/api/v3/health', { auth: false, timeoutKind: 'list' });
    results.push({ id: 'api', label: 'API accesible', status: 'ok', detail: '/api/v3/health' });
  } catch (e) {
    // Many backends expose /health without /api/v3 — try soft fail with detail.
    const msg = e instanceof Error ? e.message : String(e);
    results.push({
      id: 'api',
      label: 'API accesible',
      status: 'warn',
      detail: `No respondió /api/v3/health (${msg}). Verificar listados tras login.`,
    });
  }

  try {
    const access = await input.tokenStorage.getAccessToken();
    results.push({
      id: 'auth',
      label: 'Auth / SecureStore',
      status: access ? 'ok' : 'warn',
      detail: access ? 'Access token presente' : 'Sin sesión',
    });
  } catch (e) {
    results.push({
      id: 'auth',
      label: 'Auth / SecureStore',
      status: 'fail',
      detail: e instanceof Error ? e.message : String(e),
    });
  }

  try {
    await input.probeSqlite();
    results.push({ id: 'sqlite', label: 'SQLite', status: 'ok', detail: 'Lectura OK' });
  } catch (e) {
    results.push({
      id: 'sqlite',
      label: 'SQLite',
      status: 'fail',
      detail: e instanceof Error ? e.message : String(e),
    });
  }

  if (input.probeMediaStore) {
    try {
      await input.probeMediaStore();
      results.push({ id: 'mediastore', label: 'MediaStore', status: 'ok', detail: 'Acceso OK' });
    } catch (e) {
      results.push({
        id: 'mediastore',
        label: 'MediaStore',
        status: 'warn',
        detail: e instanceof Error ? e.message : String(e),
      });
    }
  }

  const storage = await getStorageStatus();
  results.push({
    id: 'storage',
    label: 'Almacenamiento',
    status: storage.lowSpace ? 'warn' : storage.freeBytes == null ? 'warn' : 'ok',
    detail:
      storage.freeBytes == null
        ? 'No se pudo medir'
        : `${Math.round(storage.freeBytes / (1024 * 1024))} MB libres`,
  });

  results.push({
    id: 'flags',
    label: 'Feature flags',
    status: 'ok',
    detail: Object.entries(input.config.flags)
      .map(([k, v]) => `${k}=${v ? '1' : '0'}`)
      .join(', '),
  });

  input.logger?.info('health_check', {
    ok: results.filter((r) => r.status === 'ok').length,
    warn: results.filter((r) => r.status === 'warn').length,
    fail: results.filter((r) => r.status === 'fail').length,
  });

  return results;
}
