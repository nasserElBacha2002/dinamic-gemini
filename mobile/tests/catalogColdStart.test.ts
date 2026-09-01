import { AuthService } from '../src/features/auth/authService';
import { InventoryService } from '../src/features/inventories/inventoryService';
import { createLogger } from '../src/core/logging';
import { ApiError, NETWORK_ERROR, REQUEST_TIMEOUT } from '../src/services/api/apiClient';
import type { AuthTokens, TokenStorage } from '../src/services/secureStorage/tokenStorage';
import type { AuthUserDto } from '../src/services/api/types';
import type { SessionUserStorage } from '../src/services/secureStorage/sessionUserStorage';
import type { LocalCatalogRepository } from '../src/database/repositories/localCatalogRepository';
import type { CatalogSyncCoordinator } from '../src/features/catalog/catalogSyncCoordinator';
import type { ConnectivityService } from '../src/services/connectivity/connectivity';

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

class MemorySessionUserStorage implements SessionUserStorage {
  user: AuthUserDto | null = null;
  async getUser() {
    return this.user;
  }
  async saveUser(user: AuthUserDto) {
    this.user = user;
  }
  async clear() {
    this.user = null;
  }
}

describe('cold start offline catalog', () => {
  it('restores auth session from cached user when offline', async () => {
    const storage = new MemoryTokenStorage();
    const sessionStorage = new MemorySessionUserStorage();
    sessionStorage.user = {
      id: 'user-1',
      username: 'operator',
      role: 'operator',
      client_id: 'client-1',
    };
    const api = {
      get: jest.fn(),
    };
    const service = new AuthService(
      api as never,
      storage,
      createLogger(() => undefined),
      sessionStorage,
    );
    const session = await service.restore('offline');
    expect(session?.user.id).toBe('user-1');
    expect(session?.offlineRestored).toBe(true);
    expect(api.get).not.toHaveBeenCalled();
  });

  it('falls back to cached user on network timeout during restore', async () => {
    const storage = new MemoryTokenStorage();
    const sessionStorage = new MemorySessionUserStorage();
    sessionStorage.user = {
      id: 'user-1',
      username: 'operator',
      role: 'operator',
      client_id: 'client-1',
    };
    const api = {
      get: jest.fn().mockRejectedValue(new ApiError('timeout', null, REQUEST_TIMEOUT)),
    };
    const service = new AuthService(
      api as never,
      storage,
      createLogger(() => undefined),
      sessionStorage,
    );
    const session = await service.restore('online');
    expect(session?.offlineRestored).toBe(true);
    expect(session?.user.username).toBe('operator');
  });

  it('returns null on real 401 even with cached user', async () => {
    const storage = new MemoryTokenStorage();
    const sessionStorage = new MemorySessionUserStorage();
    sessionStorage.user = {
      id: 'user-1',
      username: 'operator',
      role: 'operator',
      client_id: null,
    };
    const api = {
      get: jest.fn().mockRejectedValue(new ApiError('unauthorized', 401, 'UNAUTHORIZED')),
    };
    const service = new AuthService(
      api as never,
      storage,
      createLogger(() => undefined),
      sessionStorage,
    );
    await expect(service.restore('online')).resolves.toBeNull();
  });

  it('lists inventories from SQLite without waiting for network', async () => {
    const catalog = {
      listInventories: jest.fn(async () => ({
        items: [
          {
            id: 'inv-1',
            name: 'Cached inventory',
            status: 'active',
            client_id: 'client-1',
            created_at: null,
            updated_at: null,
            aisles_count: 2,
            pending_review_count: 0,
            last_activity_at: null,
            processing_mode: 'production',
          },
        ],
        page: 1,
        page_size: 25,
        total_items: 1,
        total_pages: 1,
      })),
    } as unknown as LocalCatalogRepository;
    const catalogSync = {
      requestSync: jest.fn(async () => ({ ok: true, syncedAt: null, status: 'SUCCESS' })),
    } as unknown as CatalogSyncCoordinator;
    const connectivity = {
      getState: () => 'offline' as const,
    } as ConnectivityService;
    const api = {
      get: jest.fn(),
    };
    const service = new InventoryService(api as never, catalog, catalogSync, connectivity);
    const page = await service.list({ page: 1 });
    expect(page.items[0]?.name).toBe('Cached inventory');
    expect(api.get).not.toHaveBeenCalled();
    expect(catalogSync.requestSync).not.toHaveBeenCalled();
  });

  it('uses cached catalog when backend returns 500', async () => {
    const catalog = {
      listInventories: jest.fn(async () => ({
        items: [
          {
            id: 'inv-1',
            name: 'Cached inventory',
            status: 'active',
            client_id: 'client-1',
            created_at: null,
            updated_at: null,
            aisles_count: 2,
            pending_review_count: 0,
            last_activity_at: null,
            processing_mode: 'production',
          },
        ],
        page: 1,
        page_size: 25,
        total_items: 1,
        total_pages: 1,
      })),
    } as unknown as LocalCatalogRepository;
    const catalogSync = {
      requestSync: jest.fn(async () => ({ ok: false, syncedAt: null, status: 'FAILED' })),
    } as unknown as CatalogSyncCoordinator;
    const connectivity = {
      getState: () => 'online' as const,
    } as ConnectivityService;
    const api = {
      get: jest.fn().mockRejectedValue(new ApiError('server', 500, 'SERVER_ERROR')),
    };
    const service = new InventoryService(api as never, catalog, catalogSync, connectivity);
    const page = await service.list({ page: 1 });
    expect(page.items).toHaveLength(1);
  });

  it('falls back to cached user on backend 500 during restore', async () => {
    const storage = new MemoryTokenStorage();
    const sessionStorage = new MemorySessionUserStorage();
    sessionStorage.user = {
      id: 'user-1',
      username: 'operator',
      role: 'operator',
      client_id: 'client-1',
    };
    const api = {
      get: jest.fn().mockRejectedValue(new ApiError('server', 500, 'SERVER_ERROR')),
    };
    const service = new AuthService(
      api as never,
      storage,
      createLogger(() => undefined),
      sessionStorage,
    );
    const session = await service.restore('online');
    expect(session?.offlineRestored).toBe(true);
  });

  it('does not restore offline session on unknown programming errors', async () => {
    const storage = new MemoryTokenStorage();
    const sessionStorage = new MemorySessionUserStorage();
    sessionStorage.user = {
      id: 'user-1',
      username: 'operator',
      role: 'operator',
      client_id: 'client-1',
    };
    const api = {
      get: jest.fn().mockRejectedValue(new Error('unexpected parsing bug')),
    };
    const service = new AuthService(
      api as never,
      storage,
      createLogger(() => undefined),
      sessionStorage,
    );
    await expect(service.restore('online')).resolves.toBeNull();
  });

  it('does not treat network unavailable as unauthorized', async () => {
    const storage = new MemoryTokenStorage();
    const sessionStorage = new MemorySessionUserStorage();
    sessionStorage.user = {
      id: 'user-1',
      username: 'operator',
      role: 'operator',
      client_id: 'client-1',
    };
    const api = {
      get: jest.fn().mockRejectedValue(new ApiError('offline', null, NETWORK_ERROR)),
    };
    const service = new AuthService(
      api as never,
      storage,
      createLogger(() => undefined),
      sessionStorage,
    );
    const session = await service.restore('online');
    expect(session).not.toBeNull();
    expect(storage.access).toBe('access');
  });
});
