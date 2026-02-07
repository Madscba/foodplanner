import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/endpoints';

// =============================================================================
// Query Keys
// =============================================================================

export const storeKeys = {
  all: ['stores'] as const,
  lists: () => [...storeKeys.all, 'list'] as const,
  list: (filters: Record<string, unknown>) =>
    [...storeKeys.lists(), filters] as const,
  details: () => [...storeKeys.all, 'detail'] as const,
  detail: (storeId: string) => [...storeKeys.details(), storeId] as const,
};

// =============================================================================
// Queries
// =============================================================================

export function useStores(params?: {
  zip_code?: string;
  brand?: string;
  limit?: number;
}) {
  return useQuery({
    queryKey: storeKeys.list(params ?? {}),
    queryFn: () => api.stores.discover(params),
    staleTime: 10 * 60 * 1000, // 10 minutes - stores don't change often
  });
}

export function useStore(storeId: string) {
  return useQuery({
    queryKey: storeKeys.detail(storeId),
    queryFn: () => api.stores.get(storeId),
    enabled: !!storeId,
  });
}
