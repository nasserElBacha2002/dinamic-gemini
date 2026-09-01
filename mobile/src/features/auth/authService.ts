import type { Logger } from '../../core/logging';
import { ApiError, NETWORK_ERROR, REQUEST_TIMEOUT } from '../../services/api/apiClient';
import type { ApiClient } from '../../services/api/apiClient';
import type { AuthUserDto, LoginResponseDto } from '../../services/api/types';
import type { TokenStorage } from '../../services/secureStorage/tokenStorage';
import type { SessionUserStorage } from '../../services/secureStorage/sessionUserStorage';

export interface AuthSession {
  readonly user: AuthUserDto;
  readonly offlineRestored?: boolean;
}

export class AuthService {
  constructor(
    private readonly api: ApiClient,
    private readonly tokenStorage: TokenStorage,
    private readonly logger: Logger,
    private readonly sessionUserStorage?: SessionUserStorage,
    private readonly onBeforeLogout?: () => Promise<void>,
    private readonly onAfterLogin?: () => Promise<void>,
  ) {}

  async login(username: string, password: string): Promise<AuthSession> {
    const payload = await this.api.post<LoginResponseDto>(
      '/auth/login',
      { username, password },
      { auth: false },
    );
    await this.tokenStorage.saveTokens({
      accessToken: payload.access_token,
      refreshToken: payload.refresh_token,
      expiresIn: payload.expires_in,
      refreshExpiresIn: payload.refresh_expires_in,
    });
    await this.sessionUserStorage?.saveUser(payload.user);
    this.logger.info('auth_login', { userId: payload.user.id, role: payload.user.role });
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { emitAuthState } = require('../../features/offlineOperations/authStateEvents') as {
        emitAuthState: (s: 'authenticated' | 'unauthenticated') => void;
      };
      emitAuthState('authenticated');
    } catch {
      /* optional */
    }
    try {
      await this.onAfterLogin?.();
    } catch (e) {
      this.logger.warn('recovery', { where: 'auth_after_login', message: String(e) });
    }
    return { user: payload.user };
  }

  async restore(connectivity: 'online' | 'offline' | 'unknown' = 'unknown'): Promise<AuthSession | null> {
    const access = await this.tokenStorage.getAccessToken();
    if (!access) {
      return null;
    }
    if (connectivity === 'offline') {
      return this.restoreFromCachedUser('offline');
    }
    try {
      const user = await this.api.get<AuthUserDto>('/auth/me');
      await this.sessionUserStorage?.saveUser(user);
      try {
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        const { emitAuthState } = require('../../features/offlineOperations/authStateEvents') as {
          emitAuthState: (s: 'authenticated' | 'unauthenticated') => void;
        };
        emitAuthState('authenticated');
      } catch {
        /* optional */
      }
      return { user };
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        this.logger.warn('recovery', { where: 'auth_restore', message: 'unauthorized' });
        return null;
      }
      if (isConnectivityFailure(e)) {
        return this.restoreFromCachedUser('network_failure');
      }
      this.logger.warn('recovery', { where: 'auth_restore', message: String(e) });
      return null;
    }
  }

  async logout(): Promise<void> {
    try {
      await this.onBeforeLogout?.();
    } catch (e) {
      this.logger.warn('recovery', { where: 'logout_cleanup', message: String(e) });
    }
    const refresh = await this.tokenStorage.getRefreshToken();
    try {
      if (refresh) {
        await this.api.post<void>('/auth/logout', { refresh_token: refresh });
      }
    } catch (e) {
      this.logger.warn('auth_refresh', { where: 'logout_remote', message: String(e) });
    } finally {
      await this.tokenStorage.clear();
      await this.sessionUserStorage?.clear();
    }
  }

  private async restoreFromCachedUser(reason: string): Promise<AuthSession | null> {
    const cached = await this.sessionUserStorage?.getUser();
    if (!cached) {
      this.logger.warn('recovery', { where: 'auth_restore_offline', reason, message: 'no_cached_user' });
      return null;
    }
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { emitAuthState } = require('../../features/offlineOperations/authStateEvents') as {
        emitAuthState: (s: 'authenticated' | 'unauthenticated') => void;
      };
      emitAuthState('authenticated');
    } catch {
      /* optional */
    }
    this.logger.info('recovery', { where: 'auth_restore_offline', userId: cached.id, reason });
    return { user: cached, offlineRestored: true };
  }
}

function isConnectivityFailure(error: unknown): boolean {
  if (!(error instanceof ApiError)) {
    return false;
  }
  if (error.status === null) {
    return error.code === NETWORK_ERROR || error.code === REQUEST_TIMEOUT;
  }
  return error.status >= 500;
}
