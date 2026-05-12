import { useCallback, useState } from 'react';
import { createInventory } from '../../../api/client';
import type { CreateInventoryRequest, Inventory } from '../../../api/types';
import { ApiError } from '../../../api/types';

export interface UseCreateInventoryFlowOptions {
  createInventoryFn?: (body: CreateInventoryRequest) => Promise<Inventory>;
}

export function useCreateInventoryFlow({ createInventoryFn }: UseCreateInventoryFlowOptions = {}) {
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const submitCreateInventory = useCallback(
    async (body: CreateInventoryRequest): Promise<Inventory> => {
      setIsCreating(true);
      setError(null);
      try {
        const doCreate = createInventoryFn ?? createInventory;
        return await doCreate(body);
      } catch (e) {
        const err = e instanceof ApiError ? e : new ApiError(String(e));
        setError(err);
        throw err;
      } finally {
        setIsCreating(false);
      }
    },
    [createInventoryFn]
  );

  const clearError = useCallback(() => setError(null), []);

  return {
    submitCreateInventory,
    isCreating,
    isSubmitting: isCreating,
    error,
    clearError,
  };
}
