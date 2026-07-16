import type { Logger } from '../../core/logging';
import type { ApiClient } from '../../services/api/apiClient';
import type { UploadLimitsDto } from '../../services/api/types';

export const FALLBACK_UPLOAD_LIMITS: UploadLimitsDto = {
  max_files_per_request: 5,
  max_file_size_bytes: 25 * 1024 * 1024,
  max_request_size_bytes: 80 * 1024 * 1024,
  upload_batch_concurrency: 2,
  retry_attempts: 3,
  retry_base_delay_ms: 1000,
};

export class UploadLimitsService {
  private cached: UploadLimitsDto | null = null;
  private usedFallback = false;

  constructor(
    private readonly api: ApiClient,
    private readonly logger: Logger,
  ) {}

  getCached(): UploadLimitsDto {
    return this.cached ?? FALLBACK_UPLOAD_LIMITS;
  }

  didUseFallback(): boolean {
    return this.usedFallback && this.cached === null;
  }

  async refresh(): Promise<UploadLimitsDto> {
    try {
      const limits = await this.api.get<UploadLimitsDto>('/api/v3/config/upload-limits');
      this.cached = limits;
      this.usedFallback = false;
      this.logger.info('upload_limits_refreshed', {
        maxFiles: limits.max_files_per_request,
        concurrency: limits.upload_batch_concurrency,
      });
      return limits;
    } catch (e) {
      this.usedFallback = true;
      this.logger.warn('upload_limits_fallback', { message: String(e) });
      return this.getCached();
    }
  }

  async ensureLoaded(): Promise<UploadLimitsDto> {
    if (this.cached) {
      return this.cached;
    }
    return this.refresh();
  }
}
