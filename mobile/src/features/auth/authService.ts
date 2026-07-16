import type { Logger } from '../../core/logging';
import type { ApiClient } from '../../services/api/apiClient';
import type { AuthUserDto, LoginResponseDto } from '../../services/api/types';
import type { TokenStorage } from '../../services/secureStorage/tokenStorage';

export interface AuthSession {
  readonly user: AuthUserDto;
}

export class AuthService {
  constructor(
    private readonly api: ApiClient,
    private readonly tokenStorage: TokenStorage,
    private readonly logger: Logger,
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
    this.logger.info('auth_login', { userId: payload.user.id, role: payload.user.role });
    return { user: payload.user };
  }

  async restore(): Promise<AuthSession | null> {
    const access = await this.tokenStorage.getAccessToken();
    if (!access) {
      return null;
    }
    try {
      const user = await this.api.get<AuthUserDto>('/auth/me');
      return { user };
    } catch (e) {
      this.logger.warn('recovery', { where: 'auth_restore', message: String(e) });
      return null;
    }
  }

  async logout(): Promise<void> {
    const refresh = await this.tokenStorage.getRefreshToken();
    try {
      if (refresh) {
        await this.api.post<void>('/auth/logout', { refresh_token: refresh });
      }
    } catch (e) {
      this.logger.warn('auth_refresh', { where: 'logout_remote', message: String(e) });
    } finally {
      await this.tokenStorage.clear();
    }
  }
}

