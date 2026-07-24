import type { AppConfig } from '../../runtime/config/resolveAppConfig';
import type { Logger } from '../../core/logging';
import { timeoutMsFor, type ApiTimeoutKind } from '../../core/apiTimeouts';
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
  readonly timeoutMs?: number;
  readonly timeoutKind?: ApiTimeoutKind;
};

export class ApiClient {
  private refreshPromise: Promise<void> | null = null;
  private authExpiredNotified = false;

  constructor(private readonly options: ApiClientOptions) {}

  async get<T>(path: string, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
    return this.request<T>(path, { timeoutKind: 'list', ...options, method: 'GET' });
  }

  async post<T>(path: string, body?: unknown, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
    const kind: ApiTimeoutKind = path.includes('/process')
      ? 'process'
      : path.includes('/auth') || path.includes('/refresh')
        ? 'auth'
        : 'default';
    return this.request<T>(path, { timeoutKind: kind, ...options, method: 'POST', body });
  }

  async put<T>(path: string, body?: unknown, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
    return this.request<T>(path, { timeoutKind: 'default', ...options, method: 'PUT', body });
  }

  async delete(path: string, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<void> {
    await this.request<unknown>(path, { ...options, method: 'DELETE' });
  }

  async postMultipart<T>(
    path: string,
    formData: FormData,
    options: Omit<RequestOptions, 'method' | 'body'> = {},
  ): Promise<T> {
    return this.requestMultipart<T>(path, formData, { timeoutKind: 'multipart', ...options }, true);
  }

  private resolveTimeout(options: RequestOptions): number {
    if (options.timeoutMs != null) {
      return options.timeoutMs;
    }
    if (options.timeoutKind) {
      return timeoutMsFor(options.timeoutKind);
    }
    return this.options.timeoutMs ?? timeoutMsFor('default');
  }

  async request<T>(path: string, options: RequestOptions = {}, retryAuth = true): Promise<T> {
    const response = await this.fetchRaw(path, options);
    if (response.status === 401 && options.auth !== false && retryAuth) {
      await this.refreshAccessToken();
      return this.request<T>(path, options, false);
    }
    return parseResponse<T>(response);
  }

  private async requestMultipart<T>(
    path: string,
    formData: FormData,
    options: Omit<RequestOptions, 'method' | 'body'>,
    retryAuth: boolean,
  ): Promise<T> {
    const response = await this.fetchMultipart(path, formData, options);
    if (response.status === 401 && options.auth !== false && retryAuth) {
      await this.refreshAccessToken();
      return this.requestMultipart<T>(path, formData, options, false);
    }
    return parseResponse<T>(response);
  }

  private async fetchRaw(path: string, options: RequestOptions): Promise<Response> {
    if (!this.options.config.apiBaseUrl) {
      throw new ApiError('La aplicación no tiene configurada la URL del backend.', null, 'CONFIG_MISSING');
    }
    const controller = new AbortController();
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this.resolveTimeout(options));
    const unlink = linkAbortSignal(controller, options.signal);
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
    try {
      const init: RequestInit = {
        method: options.method ?? 'GET',
        headers,
        signal: controller.signal,
      };
      if (options.body !== undefined) {
        init.body = JSON.stringify(options.body);
      }
      return await fetch(`${this.options.config.apiBaseUrl}${path}`, init);
    } catch (e) {
      this.options.logger.warn('error', { where: 'api_fetch', message: String(e) });
      throw mapFetchAbortError({
        timedOut,
        externalAborted: options.signal?.aborted === true,
        fallbackMessage: 'No se pudo conectar con el backend.',
      });
    } finally {
      unlink();
      clearTimeout(timeout);
    }
  }

  private async fetchMultipart(
    path: string,
    formData: FormData,
    options: Omit<RequestOptions, 'method' | 'body'>,
  ): Promise<Response> {
    if (!this.options.config.apiBaseUrl) {
      throw new ApiError('La aplicación no tiene configurada la URL del backend.', null, 'CONFIG_MISSING');
    }
    const controller = new AbortController();
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this.resolveTimeout(options));
    const unlink = linkAbortSignal(controller, options.signal);
    const headers: Record<string, string> = {
      Accept: 'application/json',
      ...options.headers,
    };
    // Do not set Content-Type — RN/fetch must add multipart boundary.
    if (this.options.config.apiKey) {
      headers['X-API-Key'] = this.options.config.apiKey;
    }
    if (options.auth !== false) {
      const token = await this.options.tokenStorage.getAccessToken();
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
    }
    try {
      return await fetch(`${this.options.config.apiBaseUrl}${path}`, {
        method: 'POST',
        headers,
        body: formData,
        signal: controller.signal,
      });
    } catch (e) {
      this.options.logger.warn('error', { where: 'api_multipart', message: String(e) });
      throw mapFetchAbortError({
        timedOut,
        externalAborted: options.signal?.aborted === true,
        fallbackMessage: 'No se pudo conectar con el backend.',
      });
    } finally {
      unlink();
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
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  const data = text ? safeJson(text) : null;
  if (!response.ok) {
    const message = extractErrorMessage(data, response.status);
    const code = extractErrorCode(data);
    throw new ApiError(message, response.status, code);
  }
  return data as T;
}

function extractErrorMessage(data: unknown, status: number): string {
  if (typeof data === 'object' && data) {
    if ('detail' in data && (data as { detail: unknown }).detail != null) {
      const detail = (data as { detail: unknown }).detail;
      return typeof detail === 'string' ? detail : JSON.stringify(detail);
    }
    if ('message' in data && typeof (data as { message: unknown }).message === 'string') {
      return (data as { message: string }).message;
    }
  }
  return `HTTP ${status}`;
}

function extractErrorCode(data: unknown): string | null {
  if (typeof data !== 'object' || !data) {
    return null;
  }
  if ('code' in data && typeof (data as { code: unknown }).code === 'string') {
    return (data as { code: string }).code;
  }
  if ('detail' in data && typeof (data as { detail: unknown }).detail === 'object') {
    const nested = (data as { detail?: { code?: string } }).detail?.code;
    if (typeof nested === 'string') {
      return nested;
    }
  }
  if ('error' in data) {
    const nested = (data as { error?: { code?: string } }).error?.code;
    return nested ?? null;
  }
  return null;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const REQUEST_ABORTED = 'REQUEST_ABORTED';
export const REQUEST_TIMEOUT = 'REQUEST_TIMEOUT';
export const NETWORK_ERROR = 'NETWORK_ERROR';

function mapFetchAbortError(input: {
  readonly timedOut: boolean;
  readonly externalAborted: boolean;
  readonly fallbackMessage: string;
}): ApiError {
  if (input.externalAborted && !input.timedOut) {
    return new ApiError('La solicitud fue cancelada.', null, REQUEST_ABORTED);
  }
  if (input.timedOut) {
    return new ApiError('La solicitud excedió el tiempo de espera.', null, REQUEST_TIMEOUT);
  }
  return new ApiError(input.fallbackMessage, null, NETWORK_ERROR);
}

/**
 * Keep timeout AbortController authoritative while honoring an optional caller signal.
 * Returns an unlink function that must run in `finally`.
 */
export function linkAbortSignal(controller: AbortController, external?: AbortSignal): () => void {
  if (!external) {
    return () => undefined;
  }
  if (external.aborted) {
    controller.abort();
    return () => undefined;
  }
  const onAbort = () => {
    controller.abort();
  };
  external.addEventListener('abort', onAbort);
  return () => {
    external.removeEventListener('abort', onAbort);
  };
}
