import { AuthService } from '../src/features/auth/authService';
import { createLogger } from '../src/core/logging';
import type { ApiClient } from '../src/services/api/apiClient';
import type { AuthTokens, TokenStorage } from '../src/services/secureStorage/tokenStorage';

class MemoryTokenStorage implements TokenStorage {
  access: string | null = 'access';
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

describe('AuthService', () => {
  it('clears local tokens even if remote logout fails', async () => {
    const storage = new MemoryTokenStorage();
    const api = {
      post: jest.fn().mockRejectedValue(new Error('offline')),
    } as unknown as ApiClient;
    const service = new AuthService(api, storage, createLogger(() => undefined));

    await expect(service.logout()).resolves.toBeUndefined();

    expect(storage.access).toBeNull();
    expect(storage.refresh).toBeNull();
  });
});

