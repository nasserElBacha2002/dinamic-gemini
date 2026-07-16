import { ApiClient } from '../src/services/api/apiClient';
import type { AppConfig } from '../src/app/config/resolveAppConfig';
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
});

