import type { AppConfig } from '../../app/config/resolveAppConfig';
import type { Logger } from '../../core/logging';
import type { AuthTokens, TokenStorage } from '../secureStorage/tokenStorage';
import type { LoginResponseDto } from './types';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
    readonly code: string | null = null,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export interface ApiClientOptions {
  readonly config: AppConfig;
  readonly tokenStorage: TokenStorage;
  readonly logger: Logger;
  readonly timeoutMs?: number;
  readonly onAuthExpired?: () => void;
}

type RequestOptions = {
  readonly method?: string;
  readonly body?: unknown;
  readonly auth?: boolean;
  readonly signal?: AbortSignal;
  readonly headers?: Record<string, string>;
};

export class ApiClient {
  private refreshPromise: Promise<void> | null = null;
  private authExpiredNotified = false;

  constructor(private readonly options: ApiClientOptions) {}

  async get<T>(path: string, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: 'GET' });
  }

  async post<T>(path: string, body?: unknown, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: 'POST', body });
  }

  async request<T>(path: string, options: RequestOptions = {}, retryAuth = true): Promise<T> {
    const response = await this.fetchRaw(path, options);
    if (response.status === 401 && options.auth !== false && retryAuth) {
      await this.refreshAccessToken();
      return this.request<T>(path, options, false);
    }
    return parseResponse<T>(response);
  }

  private async fetchRaw(path: string, options: RequestOptions): Promise<Response> {
    if (!this.options.config.apiBaseUrl) {
      throw new ApiError('La aplicación no tiene configurada la URL del backend.', null, 'CONFIG_MISSING');
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.options.timeoutMs ?? 20_000);
    const headers: Record<string, string> = {
      Accept: 'application/json',
      ...(options.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    };
    if (this.options.config.apiKey) {
      headers['X-API-Key'] = this.options.config.apiKey;
    }
    if (options.auth !== false) {
      const token = await this.options.tokenStorage.getAccessToken();
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
    }
    const signal = options.signal ?? controller.signal;
    try {
      const init: RequestInit = {
        method: options.method ?? 'GET',
        headers,
        signal,
      };
      if (options.body !== undefined) {
        init.body = JSON.stringify(options.body);
      }
      return await fetch(`${this.options.config.apiBaseUrl}${path}`, {
        ...init,
      });
    } catch (e) {
      this.options.logger.warn('error', { where: 'api_fetch', message: String(e) });
      throw new ApiError('No se pudo conectar con el backend.', null, 'NETWORK_ERROR');
    } finally {
      clearTimeout(timeout);
    }
  }

  private async refreshAccessToken(): Promise<void> {
    if (!this.refreshPromise) {
      this.refreshPromise = (async () => {
        const refreshToken = await this.options.tokenStorage.getRefreshToken();
        if (!refreshToken) {
          await this.options.tokenStorage.clear();
          this.notifyAuthExpired();
          throw new ApiError('La sesión venció.', 401, 'NO_REFRESH_TOKEN');
        }
        this.options.logger.info('auth_refresh', { reason: '401' });
        let payload: LoginResponseDto;
        try {
          const response = await this.fetchRaw('/auth/refresh', {
            method: 'POST',
            auth: false,
            body: { refresh_token: refreshToken },
          });
          payload = await parseResponse<LoginResponseDto>(response);
        } catch (e) {
          if (isDefinitiveRefreshFailure(e)) {
            await this.options.tokenStorage.clear();
            this.notifyAuthExpired();
          }
          throw e;
        }
        const tokens: AuthTokens = {
          accessToken: payload.access_token,
          refreshToken: payload.refresh_token,
          expiresIn: payload.expires_in,
          refreshExpiresIn: payload.refresh_expires_in,
        };
        await this.options.tokenStorage.saveTokens(tokens);
      })().finally(() => {
        this.refreshPromise = null;
      });
    }
    return this.refreshPromise;
  }

  private notifyAuthExpired(): void {
    if (this.authExpiredNotified) {
      return;
    }
    this.authExpiredNotified = true;
    this.options.onAuthExpired?.();
  }
}

function isDefinitiveRefreshFailure(error: unknown): boolean {
  if (!(error instanceof ApiError)) {
    return false;
  }
  return error.status === 400 || error.status === 401 || error.status === 403 || error.status === 422;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const text = await response.text();
  const data = text ? safeJson(text) : null;
  if (!response.ok) {
    const message =
      typeof data === 'object' && data && 'detail' in data
        ? String((data as { detail: unknown }).detail)
        : `HTTP ${response.status}`;
    const code =
      typeof data === 'object' && data && 'error' in data
        ? String((data as { error?: { code?: string } }).error?.code ?? '')
        : null;
    throw new ApiError(message, response.status, code);
  }
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

