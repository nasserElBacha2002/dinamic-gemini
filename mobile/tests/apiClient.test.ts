import { ApiClient } from '../src/services/api/apiClient';
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

