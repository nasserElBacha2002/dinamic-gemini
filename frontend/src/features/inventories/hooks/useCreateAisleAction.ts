import { useCallback, useState } from 'react';
import { createAisle } from '../../../api/client';
import type { CreateAisleRequest } from '../../../api/types';
import { ApiError } from '../../../api/types';

export interface UseCreateAisleActionOptions {
  inventoryId: string;
  createAisleFn?: (body: CreateAisleRequest) => Promise<unknown>;
}

export function useCreateAisleAction({ inventoryId, createAisleFn }: UseCreateAisleActionOptions) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const submitCreateAisle = useCallback(
    async (body: CreateAisleRequest): Promise<unknown> => {
      setIsSubmitting(true);
      setError(null);
      try {
        const doCreate = createAisleFn ?? ((next: CreateAisleRequest) => createAisle(inventoryId, next));
        return await doCreate(body);
      } catch (e) {
        const err = e instanceof ApiError ? e : new ApiError(String(e));
        setError(err);
        throw err;
      } finally {
        setIsSubmitting(false);
      }
    },
    [createAisleFn, inventoryId]
  );

  const clearError = useCallback(() => setError(null), []);

  return {
    submitCreateAisle,
    isSubmitting,
    error,
    clearError,
  };
}
