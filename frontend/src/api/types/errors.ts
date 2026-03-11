/**
 * API error shape and error class — used by client and utils.
 */

export interface ApiErrorDetail {
  detail?: string | unknown;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly data?: ApiErrorDetail
  ) {
    super(message);
    this.name = 'ApiError';
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}
