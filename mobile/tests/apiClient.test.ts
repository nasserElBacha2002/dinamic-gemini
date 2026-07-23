import {
  ApiClient,
  NETWORK_ERROR,
  REQUEST_ABORTED,
  REQUEST_TIMEOUT,
  linkAbortSignal,
} from '../src/services/api/apiClient';
import type { AppConfig } from '../src/runtime/config/resolveAppConfig';
import { createLogger } from '../src/core/logging';
import type { AuthTokens, TokenStorage } from '../src/services/secureStorage/tokenStorage';

class MemoryTokenStorage implements TokenStorage {
  access: string | null = 'old';
  refresh: string | null = 'refresh';
  async getAccessToken() {
    return this.access;
  }
  async getRefreshToken() {
    return this.refresh;
  }
  async saveTokens(tokens: AuthTokens) {
    this.access = tokens.accessToken;
    this.refresh = tokens.refreshToken;
  }
  async clear() {
    this.access = null;
    this.refresh = null;
  }
}

describe('ApiClient refresh mutex', () => {
  const config: AppConfig = {
    apiBaseUrl: 'https://api.example.test',
    apiKey: null,
    environment: 'development',
    isDevelopment: true,
    versionName: '0.3.0',
    versionCode: 30,
    gitSha: 'test',
    buildTime: '',
    flags: {
      allowMobileDataUploads: true,
      heicConvertToJpeg: true,
      workManagerScheduling: true,
      advancedReconciliation: true,
      backgroundJobPolling: true,
      aisleDeviceLock: false,
      uploadObservabilityEnabled: true,
      uploadDimensionCap: true,
      uploadAdaptiveQuality: true,
      uploadAdaptiveConcurrency: true,
      uploadAbortEnabled: true,
    },
  };

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('runs a single refresh for concurrent 401 responses and retries both requests', async () => {
    const storage = new MemoryTokenStorage();
    let refreshCalls = 0;
    let protectedCalls = 0;

    jest.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/auth/refresh')) {
        refreshCalls += 1;
        await new Promise((resolve) => setTimeout(resolve, 10));
        return new Response(JSON.stringify({
          access_token: 'new',
          token_type: 'bearer',
          expires_in: 900,
          refresh_token: 'refresh2',
          refresh_expires_in: 3600,
          user: { id: 'admin', username: 'admin', role: 'platform_admin', client_id: null },
        }), { status: 200 });
      }
      protectedCalls += 1;
      if (protectedCalls <= 2) {
        return new Response(JSON.stringify({ error: { code: 'UNAUTHORIZED', message: 'expired' } }), { status: 401 });
      }
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    });

    const client = new ApiClient({
      config,
      tokenStorage: storage,
      logger: createLogger(() => undefined),
    });

    await Promise.all([
      client.get<{ ok: boolean }>('/api/v3/inventories/'),
      client.get<{ ok: boolean }>('/api/v3/inventories/'),
    ]);

    expect(refreshCalls).toBe(1);
    expect(storage.access).toBe('new');
  });

  it('clears tokens and notifies once when refresh is definitively invalid', async () => {
    const storage = new MemoryTokenStorage();
    const onAuthExpired = jest.fn();
    jest.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/auth/refresh')) {
        return new Response(JSON.stringify({ error: { code: 'UNAUTHORIZED', message: 'revoked' } }), { status: 401 });
      }
      return new Response(JSON.stringify({ error: { code: 'UNAUTHORIZED', message: 'expired' } }), { status: 401 });
    });
    const client = new ApiClient({
      config,
      tokenStorage: storage,
      logger: createLogger(() => undefined),
      onAuthExpired,
    });

    await expect(client.get('/api/v3/inventories/')).rejects.toThrow('HTTP 401');
    await expect(client.get('/api/v3/inventories/')).rejects.toThrow('La sesión venció.');

    expect(storage.access).toBeNull();
    expect(storage.refresh).toBeNull();
    expect(onAuthExpired).toHaveBeenCalledTimes(1);
  });

  it('does not clear tokens for temporary refresh failures', async () => {
    const storage = new MemoryTokenStorage();
    const onAuthExpired = jest.fn();
    jest.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/auth/refresh')) {
        return new Response(JSON.stringify({ detail: 'temporary' }), { status: 500 });
      }
      return new Response(JSON.stringify({ error: { code: 'UNAUTHORIZED', message: 'expired' } }), { status: 401 });
    });
    const client = new ApiClient({
      config,
      tokenStorage: storage,
      logger: createLogger(() => undefined),
      onAuthExpired,
    });

    await expect(client.get('/api/v3/inventories/')).rejects.toThrow('temporary');

    expect(storage.access).toBe('old');
    expect(storage.refresh).toBe('refresh');
    expect(onAuthExpired).not.toHaveBeenCalled();
  });

  it('clears tokens when no refresh token exists', async () => {
    const storage = new MemoryTokenStorage();
    storage.refresh = null;
    const onAuthExpired = jest.fn();
    jest.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'UNAUTHORIZED', message: 'expired' } }), { status: 401 }),
    );
    const client = new ApiClient({
      config,
      tokenStorage: storage,
      logger: createLogger(() => undefined),
      onAuthExpired,
    });

    await expect(client.get('/api/v3/inventories/')).rejects.toThrow('La sesión venció.');

    expect(storage.access).toBeNull();
    expect(storage.refresh).toBeNull();
    expect(onAuthExpired).toHaveBeenCalledTimes(1);
  });
});

describe('ApiClient abort / timeout classification', () => {
  const config: AppConfig = {
    apiBaseUrl: 'https://api.example.test',
    apiKey: null,
    environment: 'development',
    isDevelopment: true,
    versionName: '0.3.0',
    versionCode: 30,
    gitSha: 'test',
    buildTime: '',
    flags: {
      allowMobileDataUploads: true,
      heicConvertToJpeg: true,
      workManagerScheduling: false,
      advancedReconciliation: true,
      backgroundJobPolling: true,
      aisleDeviceLock: false,
      uploadObservabilityEnabled: true,
      uploadDimensionCap: true,
      uploadAdaptiveQuality: true,
      uploadAdaptiveConcurrency: true,
      uploadAbortEnabled: true,
    },
  };

  afterEach(() => {
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  it('maps external abort to REQUEST_ABORTED', async () => {
    const controller = new AbortController();
    jest.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
      await new Promise<void>((_, reject) => {
        const signal = init?.signal;
        if (!signal) {
          reject(new Error('missing signal'));
          return;
        }
        if (signal.aborted) {
          reject(Object.assign(new Error('Aborted'), { name: 'AbortError' }));
          return;
        }
        signal.addEventListener('abort', () => {
          reject(Object.assign(new Error('Aborted'), { name: 'AbortError' }));
        });
      });
      throw new Error('unreachable');
    });
    const client = new ApiClient({
      config,
      tokenStorage: new MemoryTokenStorage(),
      logger: createLogger(() => undefined),
    });
    const pending = client.get('/api/v3/inventories/', { signal: controller.signal });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ code: REQUEST_ABORTED });
  });

  it('maps internal timeout to REQUEST_TIMEOUT', async () => {
    jest.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
      await new Promise<void>((_, reject) => {
        const signal = init?.signal;
        signal?.addEventListener('abort', () => {
          reject(Object.assign(new Error('Aborted'), { name: 'AbortError' }));
        });
      });
      throw new Error('unreachable');
    });
    const client = new ApiClient({
      config,
      tokenStorage: new MemoryTokenStorage(),
      logger: createLogger(() => undefined),
    });
    // Override list timeoutKind so the internal AbortController fires quickly.
    await expect(client.get('/api/v3/inventories/', { timeoutMs: 40 })).rejects.toMatchObject({
      code: REQUEST_TIMEOUT,
    });
  });

  it('maps transport failure to NETWORK_ERROR', async () => {
    jest.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Network request failed'));
    const client = new ApiClient({
      config,
      tokenStorage: new MemoryTokenStorage(),
      logger: createLogger(() => undefined),
    });
    await expect(client.get('/api/v3/inventories/')).rejects.toMatchObject({ code: NETWORK_ERROR });
  });

  it('cleans up linkAbortSignal listeners across multiple requests', () => {
    const external = new AbortController();
    const add = jest.spyOn(external.signal, 'addEventListener');
    const remove = jest.spyOn(external.signal, 'removeEventListener');
    const unlinkA = linkAbortSignal(new AbortController(), external.signal);
    const unlinkB = linkAbortSignal(new AbortController(), external.signal);
    expect(add).toHaveBeenCalledTimes(2);
    unlinkA();
    unlinkB();
    expect(remove).toHaveBeenCalledTimes(2);
  });
});

