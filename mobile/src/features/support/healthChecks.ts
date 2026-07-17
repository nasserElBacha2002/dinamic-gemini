import type { AppConfig } from '../../runtime/config/resolveAppConfig';
import type { Logger } from '../../core/logging';
import { ApiError, type ApiClient } from '../../services/api/apiClient';
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

/**
 * Probe backend reachability without requiring a dedicated /api/v3/health route.
 * Prefers a lightweight authenticated or public inventory list page=1&page_size=1.
 */
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
    const secure = input.config.environment !== 'production' || url.protocol === 'https:';
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

  results.push(await probeApi(input.api, input.connectivity));

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

async function probeApi(
  api: ApiClient,
  connectivity: ConnectivityService,
): Promise<HealthCheckResult> {
  if (connectivity.getState() === 'offline') {
    return {
      id: 'api',
      label: 'API accesible',
      status: 'warn',
      detail: 'Sin conexión local — no se pudo probar el backend',
    };
  }
  try {
    await api.get('/api/v3/inventories/?page=1&page_size=1', { timeoutKind: 'list' });
    return { id: 'api', label: 'API accesible', status: 'ok', detail: 'GET /api/v3/inventories OK' };
  } catch (e) {
    if (e instanceof ApiError) {
      if (e.status === 401 || e.status === 403) {
        return {
          id: 'api',
          label: 'API accesible',
          status: 'ok',
          detail: `Backend alcanzó respuesta HTTP ${e.status} (auth requerida)`,
        };
      }
      if (e.status === 404) {
        return {
          id: 'api',
          label: 'API accesible',
          status: 'warn',
          detail: 'Ruta de inventarios no encontrada (404) — verificar versión de API',
        };
      }
      return {
        id: 'api',
        label: 'API accesible',
        status: 'fail',
        detail: `HTTP ${e.status ?? '?'} · ${e.code ?? 'error'}`,
      };
    }
    const msg = e instanceof Error ? e.message : String(e);
    const lower = msg.toLowerCase();
    if (lower.includes('abort') || lower.includes('timeout')) {
      return { id: 'api', label: 'API accesible', status: 'fail', detail: 'Timeout al contactar el backend' };
    }
    if (lower.includes('ssl') || lower.includes('tls') || lower.includes('certificate')) {
      return { id: 'api', label: 'API accesible', status: 'fail', detail: 'Error TLS/certificado' };
    }
    if (lower.includes('dns') || lower.includes('name not resolved')) {
      return { id: 'api', label: 'API accesible', status: 'fail', detail: 'Error DNS' };
    }
    if (lower.includes('network') || lower.includes('failed to fetch')) {
      return { id: 'api', label: 'API accesible', status: 'fail', detail: 'Red no disponible o backend caído' };
    }
    return { id: 'api', label: 'API accesible', status: 'fail', detail: msg.slice(0, 160) };
  }
}
