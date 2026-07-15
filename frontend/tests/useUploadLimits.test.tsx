import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fetchUploadLimits, useUploadLimits } from '../src/features/uploads/useUploadLimits';
import { UPLOAD_LIMITS } from '../src/features/uploads/bulkUpload.config';

vi.mock('../src/api/request', () => ({
  apiRequestJson: vi.fn(),
}));

import { apiRequestJson } from '../src/api/request';

const mockedApi = vi.mocked(apiRequestJson);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('useUploadLimits', () => {
  beforeEach(() => {
    mockedApi.mockReset();
  });

  it('uses backend values when endpoint succeeds', async () => {
    mockedApi.mockResolvedValue({
      max_files_per_request: 7,
      max_file_size_bytes: 111,
      max_request_size_bytes: 222,
      upload_batch_concurrency: 3,
      retry_attempts: 4,
      retry_base_delay_ms: 500,
    });

    const { result } = renderHook(() => useUploadLimits(), { wrapper });
    await waitFor(() => expect(result.current.source).toBe('backend'));
    expect(result.current.maxFilesPerRequest).toBe(7);
    expect(result.current.maxFileSizeBytes).toBe(111);
    expect(result.current.maxBytesPerRequest).toBe(222);
    expect(result.current.uploadConcurrency).toBe(3);
  });

  it('falls back to local defaults when endpoint fails', async () => {
    mockedApi.mockRejectedValue(new Error('network'));
    const { result } = renderHook(() => useUploadLimits(), { wrapper });
    await waitFor(() => expect(mockedApi).toHaveBeenCalled());
    expect(result.current.source).toBe('fallback');
    expect(result.current.maxFilesPerRequest).toBe(UPLOAD_LIMITS.maxFilesPerRequest);
    expect(result.current.maxFileSizeBytes).toBe(UPLOAD_LIMITS.maxFileSizeBytes);
  });

  it('fetchUploadLimits hits /api/v3/config/upload-limits', async () => {
    mockedApi.mockResolvedValue({
      max_files_per_request: 10,
      max_file_size_bytes: 1,
      max_request_size_bytes: 2,
      upload_batch_concurrency: 2,
      retry_attempts: 3,
      retry_base_delay_ms: 1000,
    });
    await fetchUploadLimits();
    expect(mockedApi.mock.calls[0][0]).toContain('/api/v3/config/upload-limits');
  });
});
